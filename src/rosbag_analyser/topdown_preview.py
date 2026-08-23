from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat

from rosbag_analyser.artifact_store import (
    ArtifactStore,
    ArtifactStoreError,
    OpenedMedia,
)
from rosbag_analyser.catalog.metadata import MetadataError, parse_metadata_file
from rosbag_analyser.catalog.paths import (
    SourceFileIdentity,
    UnsafeSourcePath,
    filesystem_text_from_safe,
    source_file_identity,
)
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    JobRecord,
    ProcessingComponent,
    ProcessingRepository,
    ProcessingSourceRecord,
    TOPDOWN_PREVIEW_KIND,
)


PROCESSOR_VERSION = "topdown-preview-v2"


@dataclass(frozen=True)
class TopdownSourceDescriptor:
    recording_id: int
    archive_relative_path: str
    metadata_path: Path
    video_path: Path
    timestamps_path: Path
    metadata_identity: SourceFileIdentity
    video_identity: SourceFileIdentity
    timestamps_identity: SourceFileIdentity
    bag_start_ns: int
    bag_duration_ns: int
    cache_identity: str


@dataclass(frozen=True)
class TopdownSourceResolution:
    recording_exists: bool
    descriptor: TopdownSourceDescriptor | None = None
    diagnostic: SafeDiagnostic | None = None
    duration_ns: int | None = None


@dataclass(frozen=True)
class TopdownPreviewDisplay:
    recording_exists: bool
    state: str
    duration_ns: int | None
    diagnostic: SafeDiagnostic | None = None
    artifact: ArtifactRecord | None = None


class TopdownSourceResolver:
    def __init__(
        self,
        archive_root: Path,
        repository: ProcessingRepository,
        profile: PreviewProfile,
        encoder_identity: str,
    ) -> None:
        self.archive_root = archive_root
        self.repository = repository
        self.profile = profile
        self.encoder_identity = encoder_identity

    def resolve(self, recording_id: int) -> TopdownSourceResolution:
        record = self.repository.get_source(recording_id)
        if record is None:
            return TopdownSourceResolution(recording_exists=False)
        if record.start_time_ns is None or record.duration_ns is None:
            return self._unavailable(
                record,
                "bag_timing_unavailable",
                "The recording has no trustworthy bag timing for synchronization.",
            )
        if record.ros_health != "readable":
            return self._unavailable(
                record,
                "bag_origin_unavailable",
                "A trustworthy ROS bag origin is unavailable for synchronization.",
            )
        if record.metadata is None or record.metadata.condition != "readable":
            return self._unavailable(
                record,
                "metadata_unavailable",
                "The recording metadata is unavailable for synchronization.",
            )
        if record.topdown_video is None or record.topdown_video.condition != "present":
            return self._unavailable(
                record,
                "topdown_video_unavailable",
                "The top-down video companion is unavailable.",
            )
        if (
            record.topdown_timestamps is None
            or record.topdown_timestamps.condition != "present"
        ):
            return self._unavailable(
                record,
                "topdown_timestamps_unavailable",
                "The top-down timestamp companion is unavailable.",
            )

        try:
            metadata_path, metadata_identity = self._resolve_component(record.metadata)
            video_path, video_identity = self._resolve_component(record.topdown_video)
            timestamps_path, timestamps_identity = self._resolve_component(
                record.topdown_timestamps
            )
            metadata = parse_metadata_file(
                metadata_path, expected_identity=metadata_identity
            )
            if (
                metadata.start_time_ns != record.start_time_ns
                or metadata.duration_ns != record.duration_ns
            ):
                return self._unavailable(
                    record,
                    "catalog_source_changed",
                    "The recording changed after its last scan. "
                    "Rescan before processing.",
                )
        except (OSError, MetadataError, UnsafeSourcePath, ValueError):
            return self._unavailable(
                record,
                "topdown_source_uninspectable",
                "The top-down sources could not be resolved safely.",
            )

        identity = _cache_identity(
            record,
            metadata_identity,
            video_identity,
            timestamps_identity,
            self.profile,
            self.encoder_identity,
        )
        return TopdownSourceResolution(
            recording_exists=True,
            descriptor=TopdownSourceDescriptor(
                recording_id=record.id,
                archive_relative_path=record.archive_relative_path,
                metadata_path=metadata_path,
                video_path=video_path,
                timestamps_path=timestamps_path,
                metadata_identity=metadata_identity,
                video_identity=video_identity,
                timestamps_identity=timestamps_identity,
                bag_start_ns=record.start_time_ns,
                bag_duration_ns=record.duration_ns,
                cache_identity=identity,
            ),
            duration_ns=record.duration_ns,
        )

    def _resolve_component(
        self, component: ProcessingComponent
    ) -> tuple[Path, SourceFileIdentity]:
        if (
            component.relative_path is None
            or component.size_bytes is None
            or component.mtime_ns is None
        ):
            raise ValueError("Component facts are incomplete.")
        path = _resolve_catalog_path(self.archive_root, component.relative_path)
        details = path.stat(follow_symlinks=False)
        identity = source_file_identity(details)
        if (
            not stat.S_ISREG(identity.mode)
            or identity.size_bytes != component.size_bytes
            or identity.mtime_ns != component.mtime_ns
        ):
            raise ValueError("Component changed after the catalog scan.")
        return path, identity

    @staticmethod
    def _unavailable(
        record: ProcessingSourceRecord, code: str, message: str
    ) -> TopdownSourceResolution:
        return TopdownSourceResolution(
            recording_exists=True,
            diagnostic=SafeDiagnostic(code, message),
            duration_ns=record.duration_ns,
        )


class TopdownPreviewService:
    def __init__(
        self,
        resolver: TopdownSourceResolver,
        repository: ProcessingRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self.resolver = resolver
        self.repository = repository
        self.artifact_store = artifact_store

    def get_state(self, recording_id: int) -> TopdownPreviewDisplay:
        return self._display_for_resolution(
            self.resolver.resolve(recording_id), request_if_needed=False
        )

    def request(self, recording_id: int) -> TopdownPreviewDisplay:
        return self._display_for_resolution(
            self.resolver.resolve(recording_id), request_if_needed=True
        )

    def _display_for_resolution(
        self,
        resolution: TopdownSourceResolution,
        *,
        request_if_needed: bool,
    ) -> TopdownPreviewDisplay:
        if not resolution.recording_exists:
            return TopdownPreviewDisplay(False, "not_found", None)
        if resolution.descriptor is None:
            return TopdownPreviewDisplay(
                True,
                "unavailable",
                resolution.duration_ns,
                diagnostic=resolution.diagnostic,
            )
        descriptor = resolution.descriptor
        current = self.repository.get_current_state(
            descriptor.recording_id,
            TOPDOWN_PREVIEW_KIND,
            descriptor.cache_identity,
        )
        artifact = current.artifact
        invalid_artifact_id: int | None = None
        if artifact is not None:
            try:
                self.artifact_store.validate_media(
                    artifact.output_relative_path,
                    artifact.size_bytes,
                    artifact.cache_identity,
                    artifact.manifest,
                )
            except ArtifactStoreError as error:
                if not request_if_needed:
                    return TopdownPreviewDisplay(
                        True,
                        "failed",
                        descriptor.bag_duration_ns,
                        diagnostic=SafeDiagnostic(error.code, error.safe_message),
                    )
                invalid_artifact_id = artifact.id
            else:
                return TopdownPreviewDisplay(
                    True, "ready", descriptor.bag_duration_ns, artifact=artifact
                )
        if current.active_job is not None:
            return _display_for_job(current.active_job, descriptor.bag_duration_ns)
        if not request_if_needed and current.latest_failed_job is not None:
            failed = current.latest_failed_job
            return TopdownPreviewDisplay(
                True,
                "failed",
                descriptor.bag_duration_ns,
                diagnostic=SafeDiagnostic(
                    failed.error_code or "topdown_preview_failed",
                    failed.error_message or "Top-down preview generation failed.",
                ),
            )
        if not request_if_needed:
            return TopdownPreviewDisplay(
                True, "not_requested", descriptor.bag_duration_ns
            )
        outcome = self.repository.request_job(
            descriptor.recording_id,
            TOPDOWN_PREVIEW_KIND,
            descriptor.cache_identity,
            invalid_artifact_id=invalid_artifact_id,
        )
        if outcome.artifact is not None:
            try:
                self.artifact_store.validate_media(
                    outcome.artifact.output_relative_path,
                    outcome.artifact.size_bytes,
                    outcome.artifact.cache_identity,
                    outcome.artifact.manifest,
                )
            except ArtifactStoreError as error:
                return TopdownPreviewDisplay(
                    True,
                    "failed",
                    descriptor.bag_duration_ns,
                    diagnostic=SafeDiagnostic(error.code, error.safe_message),
                )
            return TopdownPreviewDisplay(
                True,
                "ready",
                descriptor.bag_duration_ns,
                artifact=outcome.artifact,
            )
        if outcome.job is None:
            raise RuntimeError("The top-down request returned no job or artifact.")
        return _display_for_job(outcome.job, descriptor.bag_duration_ns)

    def resolve_media(
        self, recording_id: int, artifact_id: int
    ) -> tuple[OpenedMedia, ArtifactRecord] | None:
        state = self.get_state(recording_id)
        if (
            state.state != "ready"
            or state.artifact is None
            or state.artifact.id != artifact_id
        ):
            return None
        try:
            opened = self.artifact_store.open_media(
                state.artifact.output_relative_path,
                state.artifact.size_bytes,
                state.artifact.cache_identity,
                state.artifact.manifest,
            )
        except ArtifactStoreError:
            return None
        return opened, state.artifact


def _display_for_job(job: JobRecord, duration_ns: int) -> TopdownPreviewDisplay:
    return TopdownPreviewDisplay(
        True,
        "queued" if job.state == "queued" else "processing",
        duration_ns,
    )


def _cache_identity(
    record: ProcessingSourceRecord,
    metadata_identity: SourceFileIdentity,
    video_identity: SourceFileIdentity,
    timestamps_identity: SourceFileIdentity,
    profile: PreviewProfile,
    media_encoder_identity: str,
) -> str:
    document = {
        "artifact_kind": TOPDOWN_PREVIEW_KIND,
        "processor_version": PROCESSOR_VERSION,
        "recording": {
            "id": record.identity_recording_id,
            "archive_relative_path": record.identity_relative_path,
            "bag_start_ns": record.start_time_ns,
            "bag_duration_ns": record.duration_ns,
        },
        "metadata": _identity_values(metadata_identity),
        "video": _identity_values(video_identity),
        "timestamps": _identity_values(timestamps_identity),
        "profile": profile.identity_values(),
        "encoder": media_encoder_identity,
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _identity_values(identity: SourceFileIdentity) -> dict[str, int]:
    return {
        "device_id": identity.device_id,
        "inode": identity.inode,
        "mode": identity.mode,
        "size_bytes": identity.size_bytes,
        "mtime_ns": identity.mtime_ns,
    }


def _resolve_catalog_path(archive_root: Path, relative_path: str) -> Path:
    decoded_relative_path = filesystem_text_from_safe(relative_path)
    relative = PurePosixPath(decoded_relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or "\\" in decoded_relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("Catalog source path is unsafe.")
    current = archive_root
    for part in relative.parts:
        current = current / part
        details = current.lstat()
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("Source symlinks are unsupported.")
    resolved = current.resolve(strict=True)
    if archive_root not in resolved.parents:
        raise ValueError("Catalog source escaped the archive root.")
    return resolved
