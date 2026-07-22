from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any

from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.timeline import media_pts_digest_chunk


logger = logging.getLogger(__name__)
MAX_MANIFEST_BYTES = 1024 * 1024
SUPPORTED_ARTIFACT_KINDS = frozenset({"front_preview", "topdown_preview"})


class ArtifactStoreError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class MediaValidation:
    size_bytes: int
    device_id: int
    inode: int
    mtime_ns: int
    width: int
    height: int
    codec: str
    pixel_format: str
    duration_seconds: float
    frame_count: int


@dataclass(frozen=True)
class PublishedArtifact:
    output_relative_path: str
    size_bytes: int


@dataclass(frozen=True)
class OpenedMedia:
    descriptor: int
    stat_result: os.stat_result


class ArtifactStore:
    def __init__(
        self,
        derived_root: Path,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        artifact_kind: str = "front_preview",
    ) -> None:
        if artifact_kind not in SUPPORTED_ARTIFACT_KINDS:
            raise ArtifactStoreError(
                "artifact_kind_invalid", "The artifact kind is unsupported."
            )
        self.derived_root = derived_root.resolve(strict=True)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.artifact_kind = artifact_kind
        self.owned_root = self.derived_root / "rosbag-analyser"
        self.work_root = self.owned_root / "work"
        self.artifacts_root = self.owned_root / "artifacts" / artifact_kind
        self._ensure_directory(self.work_root)
        self._ensure_directory(self.artifacts_root)

    def create_workspace(self, job_id: int) -> Path:
        workspace = Path(
            tempfile.mkdtemp(prefix=f"job-{job_id}-", dir=self.work_root)
        )
        self._assert_owned_workspace(workspace, job_id)
        return workspace

    def clean_workspace(self, workspace: Path, job_id: int) -> None:
        self._assert_owned_workspace(workspace, job_id)
        if workspace.exists():
            if not workspace.is_dir():
                raise ArtifactStoreError(
                    "workspace_ownership_invalid",
                    "The temporary preview workspace is not owned by this job.",
                )
            shutil.rmtree(workspace)

    def clean_interrupted_workspaces(self, job_ids: tuple[int, ...]) -> None:
        for job_id in job_ids:
            for candidate in self.work_root.glob(f"job-{job_id}-*"):
                self.clean_workspace(candidate, job_id)

    def validate_preview(
        self,
        media_path: Path,
        profile: PreviewProfile,
        *,
        expected_width: int,
        expected_height: int,
        expected_frame_count: int,
        measured_span_ns: int,
        expected_media_pts_sha256: str | None = None,
    ) -> MediaValidation:
        self._assert_contained(media_path)
        try:
            details = media_path.stat(follow_symlinks=False)
        except OSError as error:
            raise ArtifactStoreError(
                "preview_output_missing", "The generated preview is missing."
            ) from error
        if not media_path.is_file() or media_path.is_symlink() or details.st_size <= 0:
            raise ArtifactStoreError(
                "preview_output_invalid", "The generated preview is invalid."
            )

        stream_entries = "codec_name,pix_fmt,width,height,nb_read_packets"
        show_entries = f"stream={stream_entries}:format=duration,size"
        if expected_media_pts_sha256 is not None:
            show_entries = (
                f"stream={stream_entries},time_base:format=duration,size:packet=pts"
            )
        command = [
            os.fspath(self.ffprobe_path),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            show_entries,
            "-of",
            "json",
            os.fspath(media_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            document = json.loads(completed.stdout)
            stream = document["streams"][0]
            format_facts = document["format"]
            validation = MediaValidation(
                size_bytes=int(format_facts["size"]),
                device_id=details.st_dev,
                inode=details.st_ino,
                mtime_ns=details.st_mtime_ns,
                width=int(stream["width"]),
                height=int(stream["height"]),
                codec=str(stream["codec_name"]),
                pixel_format=str(stream["pix_fmt"]),
                duration_seconds=float(format_facts["duration"]),
                frame_count=int(stream["nb_read_packets"]),
            )
        except (
            OSError,
            subprocess.SubprocessError,
            ValueError,
            KeyError,
            IndexError,
            json.JSONDecodeError,
        ) as error:
            raise ArtifactStoreError(
                "preview_validation_failed",
                "The generated preview could not be validated.",
            ) from error

        expected_codec = "h264" if profile.codec == "libx264" else profile.codec
        maximum_tail_seconds = max(0.5, 2 / profile.media_timescale)
        measured_seconds = measured_span_ns / 1_000_000_000
        if (
            validation.size_bytes != details.st_size
            or validation.codec != expected_codec
            or validation.pixel_format != profile.pixel_format
            or validation.width != expected_width
            or validation.height != expected_height
            or validation.frame_count != expected_frame_count
            or validation.duration_seconds + 0.001 < measured_seconds
            or validation.duration_seconds - measured_seconds > maximum_tail_seconds
        ):
            raise ArtifactStoreError(
                "preview_validation_mismatch",
                "The generated preview does not match the requested profile.",
            )

        if expected_media_pts_sha256 is not None:
            _validate_media_pts(
                document,
                expected_frame_count,
                profile.media_timescale,
                expected_media_pts_sha256,
            )

        if profile.container == "mp4":
            self._validate_mp4_faststart(media_path, details.st_size)
        self._validate_representative_seeks(media_path, validation.duration_seconds)
        try:
            final_details = media_path.stat(follow_symlinks=False)
        except OSError as error:
            raise ArtifactStoreError(
                "preview_output_changed",
                "The generated preview changed during validation.",
            ) from error
        if (
            not stat.S_ISREG(final_details.st_mode)
            or final_details.st_dev != validation.device_id
            or final_details.st_ino != validation.inode
            or final_details.st_size != validation.size_bytes
            or final_details.st_mtime_ns != validation.mtime_ns
        ):
            raise ArtifactStoreError(
                "preview_output_changed",
                "The generated preview changed during validation.",
            )
        return validation

    def publish(
        self,
        workspace: Path,
        job_id: int,
        cache_identity: str,
        manifest: dict[str, object],
        *,
        replace_conflicting: bool = False,
    ) -> PublishedArtifact:
        self._assert_owned_workspace(workspace, job_id)
        if len(cache_identity) != 64 or any(
            character not in "0123456789abcdef" for character in cache_identity
        ):
            raise ArtifactStoreError(
                "artifact_identity_invalid", "The artifact identity is invalid."
            )
        media_path = workspace / "preview.mp4"
        if not media_path.is_file() or media_path.is_symlink():
            raise ArtifactStoreError(
                "preview_output_missing", "The generated preview is missing."
            )
        media_details = media_path.stat(follow_symlinks=False)
        _validate_publish_manifest(
            manifest, self.artifact_kind, cache_identity, media_details
        )
        manifest_path = workspace / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

        final_directory = (
            self.artifacts_root / cache_identity[:2] / cache_identity
        )
        self._assert_contained(final_directory)
        self._ensure_directory(final_directory.parent)
        if final_directory.exists():
            try:
                return self._reuse_published(final_directory, cache_identity, manifest)
            except ArtifactStoreError:
                if not replace_conflicting:
                    raise
                return self._replace_published(
                    workspace, final_directory, job_id, cache_identity
                )
        try:
            os.rename(workspace, final_directory)
        except FileExistsError:
            return self._reuse_published(final_directory, cache_identity, manifest)
        except OSError as error:
            raise ArtifactStoreError(
                "artifact_publish_failed", "The preview could not be published."
            ) from error

        published_media = final_directory / "preview.mp4"
        details = published_media.stat(follow_symlinks=False)
        return PublishedArtifact(
            output_relative_path=published_media.relative_to(
                self.derived_root
            ).as_posix(),
            size_bytes=details.st_size,
        )

    def _replace_published(
        self,
        workspace: Path,
        final_directory: Path,
        job_id: int,
        cache_identity: str,
    ) -> PublishedArtifact:
        self._assert_owned_workspace(workspace, job_id)
        self._assert_contained(final_directory)
        if final_directory.is_symlink():
            raise ArtifactStoreError(
                "artifact_collision", "A conflicting derived artifact already exists."
            )
        backup = workspace.with_name(f"{workspace.name}-replaced")
        self._assert_contained(backup)
        if backup.exists() or backup.is_symlink():
            raise ArtifactStoreError(
                "artifact_publish_failed", "The preview could not be published."
            )
        try:
            os.rename(final_directory, backup)
            try:
                os.rename(workspace, final_directory)
            except BaseException:
                os.rename(backup, final_directory)
                raise
        except OSError as error:
            raise ArtifactStoreError(
                "artifact_publish_failed", "The preview could not be published."
            ) from error

        try:
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup)
            else:
                backup.unlink()
        except OSError:
            logger.warning(
                "Could not remove replaced derived artifact for job %s.",
                job_id,
                exc_info=True,
            )
        published_media = final_directory / "preview.mp4"
        details = published_media.stat(follow_symlinks=False)
        return PublishedArtifact(
            output_relative_path=published_media.relative_to(
                self.derived_root
            ).as_posix(),
            size_bytes=details.st_size,
        )

    def validate_media(
        self,
        relative_path: str,
        expected_size: int,
        cache_identity: str,
        expected_manifest: dict[str, object],
    ) -> None:
        opened = self.open_media(
            relative_path,
            expected_size,
            cache_identity,
            expected_manifest,
        )
        os.close(opened.descriptor)

    def open_media(
        self,
        relative_path: str,
        expected_size: int,
        cache_identity: str,
        expected_manifest: dict[str, object],
    ) -> OpenedMedia:
        expected_relative = PurePosixPath(
            "rosbag-analyser",
            "artifacts",
            self.artifact_kind,
            cache_identity[:2],
            cache_identity,
            "preview.mp4",
        )
        relative = PurePosixPath(relative_path)
        if (
            len(cache_identity) != 64
            or any(character not in "0123456789abcdef" for character in cache_identity)
            or relative != expected_relative
        ):
            raise ArtifactStoreError(
                "artifact_path_invalid", "The ready preview path is invalid."
            )

        directory_descriptor = self._open_anchored_directory(
            expected_relative.parent.parts
        )
        try:
            manifest = self._read_manifest_at(directory_descriptor)
            if (
                manifest != expected_manifest
                or manifest.get("artifact_kind") != self.artifact_kind
                or manifest.get("cache_identity") != cache_identity
                or _manifest_output_size(manifest) != expected_size
            ):
                raise ArtifactStoreError(
                    "artifact_manifest_mismatch", "The ready preview is invalid."
                )

            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
                os, "O_NOFOLLOW", 0
            )
            try:
                media_descriptor = os.open(
                    expected_relative.name,
                    flags,
                    dir_fd=directory_descriptor,
                )
            except OSError as error:
                raise ArtifactStoreError(
                    "artifact_file_missing",
                    "The ready preview file is unavailable.",
                ) from error
            try:
                details = os.fstat(media_descriptor)
                if (
                    not stat.S_ISREG(details.st_mode)
                    or details.st_size != expected_size
                    or _manifest_output_identity(manifest)
                    != (details.st_dev, details.st_ino, details.st_mtime_ns)
                ):
                    raise ArtifactStoreError(
                        "artifact_file_changed",
                        "The ready preview file is invalid.",
                    )
                return OpenedMedia(media_descriptor, details)
            except BaseException:
                os.close(media_descriptor)
                raise
        finally:
            os.close(directory_descriptor)

    def _reuse_published(
        self,
        directory: Path,
        cache_identity: str,
        expected_manifest: dict[str, object],
    ) -> PublishedArtifact:
        self._assert_contained(directory)
        manifest = self._read_manifest(directory / "manifest.json")
        media_path = directory / "preview.mp4"
        if (
            manifest != expected_manifest
            or media_path.is_symlink()
            or not media_path.is_file()
        ):
            raise ArtifactStoreError(
                "artifact_collision", "A conflicting derived artifact already exists."
            )
        details = media_path.stat(follow_symlinks=False)
        if _manifest_output_size(manifest) != details.st_size:
            raise ArtifactStoreError(
                "artifact_collision", "A conflicting derived artifact already exists."
            )
        return PublishedArtifact(
            output_relative_path=media_path.relative_to(
                self.derived_root
            ).as_posix(),
            size_bytes=details.st_size,
        )

    def _read_manifest(self, path: Path) -> dict[str, Any]:
        self._assert_contained(path)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            descriptor = os.open(path, flags)
            return self._read_manifest_descriptor(descriptor)
        except (OSError, UnicodeError, RecursionError, json.JSONDecodeError) as error:
            raise ArtifactStoreError(
                "artifact_manifest_invalid", "The ready preview manifest is invalid."
            ) from error

    def _read_manifest_at(self, directory_descriptor: int) -> dict[str, Any]:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            descriptor = os.open(
                "manifest.json",
                flags,
                dir_fd=directory_descriptor,
            )
            return self._read_manifest_descriptor(descriptor)
        except (OSError, UnicodeError, RecursionError, json.JSONDecodeError) as error:
            raise ArtifactStoreError(
                "artifact_manifest_invalid", "The ready preview manifest is invalid."
            ) from error

    @staticmethod
    def _read_manifest_descriptor(descriptor: int) -> dict[str, Any]:
        with os.fdopen(descriptor, "rb", closefd=True) as file:
            details = os.fstat(file.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise OSError("manifest is not a regular file")
            payload = file.read(MAX_MANIFEST_BYTES + 1)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise OSError("manifest exceeds the size limit")
        if not payload:
            raise OSError("manifest is not a regular file")
        document = json.loads(payload.decode("utf-8"))
        if not isinstance(document, dict):
            raise OSError("manifest is not an object")
        return document

    def _open_anchored_directory(self, relative_parts: tuple[str, ...]) -> int:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(self.derived_root, flags)
        except OSError as error:
            raise ArtifactStoreError(
                "derived_path_unavailable", "The derived artifact root is unavailable."
            ) from error
        try:
            for part in relative_parts:
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except OSError as error:
            os.close(descriptor)
            raise ArtifactStoreError(
                "artifact_path_invalid", "The ready preview path is invalid."
            ) from error

    def _assert_owned_workspace(self, workspace: Path, job_id: int) -> None:
        self._assert_contained(workspace)
        if workspace.parent != self.work_root or not workspace.name.startswith(
            f"job-{job_id}-"
        ):
            raise ArtifactStoreError(
                "workspace_ownership_invalid",
                "The temporary preview workspace is not owned by this job.",
            )

    def _assert_contained(self, path: Path) -> None:
        try:
            relative = path.absolute().relative_to(self.derived_root)
        except ValueError as error:
            raise ArtifactStoreError(
                "derived_path_escape", "A derived path escaped its configured root."
            ) from error
        current = self.derived_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ArtifactStoreError(
                    "derived_symlink_rejected",
                    "A derived path contains an unsupported symbolic link.",
                )

    def _ensure_directory(self, path: Path) -> None:
        try:
            relative = path.absolute().relative_to(self.derived_root)
        except ValueError as error:
            raise ArtifactStoreError(
                "derived_path_escape", "A derived path escaped its configured root."
            ) from error
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(self.derived_root, flags)
        except OSError as error:
            raise ArtifactStoreError(
                "derived_path_unavailable", "The derived artifact root is unavailable."
            ) from error
        try:
            for part in relative.parts:
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                except FileExistsError:
                    pass
                next_descriptor = os.open(part, flags, dir_fd=descriptor)
                details = os.fstat(next_descriptor)
                if not stat.S_ISDIR(details.st_mode):
                    os.close(next_descriptor)
                    raise OSError("derived path component is not a directory")
                os.close(descriptor)
                descriptor = next_descriptor
        except OSError as error:
            raise ArtifactStoreError(
                "derived_path_invalid",
                "A derived artifact directory could not be created safely.",
            ) from error
        finally:
            os.close(descriptor)
        self._assert_contained(path)

    def _validate_representative_seeks(
        self, media_path: Path, duration_seconds: float
    ) -> None:
        points = {0.0}
        if duration_seconds > 0.05:
            points.add(duration_seconds / 2)
            points.add(max(0.0, duration_seconds - 0.05))
        for point in sorted(points):
            command = [
                os.fspath(self.ffmpeg_path),
                "-v",
                "error",
                "-ss",
                f"{point:.6f}",
                "-i",
                os.fspath(media_path),
                "-frames:v",
                "1",
                "-f",
                "framehash",
                "-",
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                produced_frame = any(
                    line.strip() and not line.lstrip().startswith("#")
                    for line in completed.stdout.splitlines()
                )
                if not produced_frame:
                    raise ArtifactStoreError(
                        "preview_seek_validation_failed",
                        "The generated preview is not seekable.",
                    )
            except (OSError, subprocess.SubprocessError) as error:
                raise ArtifactStoreError(
                    "preview_seek_validation_failed",
                    "The generated preview is not seekable.",
                ) from error

    def _validate_mp4_faststart(self, media_path: Path, file_size: int) -> None:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            descriptor = os.open(media_path, flags)
            with os.fdopen(descriptor, "rb", closefd=True) as file:
                offset = 0
                for _ in range(100):
                    if offset >= file_size:
                        break
                    file.seek(offset)
                    header = file.read(8)
                    if len(header) != 8:
                        break
                    box_size = int.from_bytes(header[:4], "big")
                    box_type = header[4:]
                    header_size = 8
                    if box_size == 1:
                        extended_size = file.read(8)
                        if len(extended_size) != 8:
                            break
                        box_size = int.from_bytes(extended_size, "big")
                        header_size = 16
                    elif box_size == 0:
                        box_size = file_size - offset
                    if box_size < header_size or offset + box_size > file_size:
                        break
                    if box_type == b"moov":
                        return
                    if box_type == b"mdat":
                        break
                    offset += box_size
        except OSError as error:
            raise ArtifactStoreError(
                "preview_faststart_validation_failed",
                "The generated preview layout could not be validated.",
            ) from error
        raise ArtifactStoreError(
            "preview_faststart_validation_failed",
            "The generated preview is not arranged for browser streaming.",
        )


def _validate_publish_manifest(
    manifest: dict[str, object],
    artifact_kind: str,
    cache_identity: str,
    media_details: os.stat_result,
) -> None:
    if (
        manifest.get("artifact_kind") != artifact_kind
        or manifest.get("cache_identity") != cache_identity
        or _manifest_output_size(manifest) != media_details.st_size
        or _manifest_output_identity(manifest)
        != (media_details.st_dev, media_details.st_ino, media_details.st_mtime_ns)
    ):
        raise ArtifactStoreError(
            "artifact_manifest_invalid",
            "The generated preview manifest is invalid.",
        )


def _validate_media_pts(
    document: dict[str, Any],
    expected_frame_count: int,
    media_timescale: int,
    expected_sha256: str,
) -> None:
    if len(expected_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_sha256
    ):
        raise ArtifactStoreError(
            "preview_timestamp_validation_failed",
            "The expected preview timing is invalid.",
        )
    try:
        streams = document["streams"]
        packets = document["packets"]
        if (
            not isinstance(streams, list)
            or len(streams) != 1
            or not isinstance(packets, list)
            or len(packets) != expected_frame_count
        ):
            raise ValueError("Unexpected ffprobe timestamp result.")
        stream = streams[0]
        if not isinstance(stream, dict):
            raise ValueError("Unexpected ffprobe stream result.")
        time_base = Fraction(str(stream["time_base"]))
        if time_base <= 0:
            raise ValueError("Invalid media time base.")
        digest = hashlib.sha256()
        previous_pts: int | None = None
        for packet in packets:
            if not isinstance(packet, dict):
                raise ValueError("Unexpected ffprobe packet result.")
            scaled_pts = Fraction(int(packet["pts"])) * time_base * media_timescale
            if scaled_pts.denominator != 1:
                raise ValueError("Media timestamp cannot be represented exactly.")
            media_pts = scaled_pts.numerator
            if previous_pts is not None and media_pts <= previous_pts:
                raise ValueError("Media timestamps are not strictly increasing.")
            digest.update(media_pts_digest_chunk(media_pts))
            previous_pts = media_pts
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as error:
        raise ArtifactStoreError(
            "preview_timestamp_validation_failed",
            "The generated preview timestamps could not be validated.",
        ) from error
    if digest.hexdigest() != expected_sha256:
        raise ArtifactStoreError(
            "preview_timestamp_mismatch",
            "The generated preview timestamps do not match the source timing.",
        )


def _manifest_output_size(manifest: dict[str, Any]) -> int | None:
    output = manifest.get("output")
    if not isinstance(output, dict):
        return None
    value = output.get("size_bytes")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _manifest_output_identity(
    manifest: dict[str, Any],
) -> tuple[int, int, int] | None:
    output = manifest.get("output")
    if not isinstance(output, dict):
        return None
    identity = output.get("file_identity")
    if not isinstance(identity, dict):
        return None
    values = (
        identity.get("device_id"),
        identity.get("inode"),
        identity.get("mtime_ns"),
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    return values  # type: ignore[return-value]
