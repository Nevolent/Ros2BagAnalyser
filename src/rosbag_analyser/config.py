from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Mapping
from urllib.parse import urlsplit


ARCHIVE_ROOT_ENV = "ROS_BAG_ANALYSER_ARCHIVE_ROOT"
DERIVED_ROOT_ENV = "ROS_BAG_ANALYSER_DERIVED_ROOT"
DATABASE_URL_ENV = "ROS_BAG_ANALYSER_DATABASE_URL"
FRONT_TOPIC_ENV = "ROS_BAG_ANALYSER_FRONT_TOPIC"
PREVIEW_PROFILE_ENV = "ROS_BAG_ANALYSER_PREVIEW_PROFILE"
FFMPEG_ENV = "ROS_BAG_ANALYSER_FFMPEG"
FFPROBE_ENV = "ROS_BAG_ANALYSER_FFPROBE"

DEFAULT_FRONT_TOPIC = "/kuupkulgur_v1/sensors/front_camera/image_raw"
DEFAULT_PREVIEW_PROFILE = "h264-720p-v1"
ROS_TOPIC_PATTERN = re.compile(
    r"^/(?:[A-Za-z_][A-Za-z0-9_]*)(?:/[A-Za-z_][A-Za-z0-9_]*)*$"
)


@dataclass(frozen=True)
class PreviewProfile:
    name: str
    container: str
    codec: str
    pixel_format: str
    mime_type: str
    max_width: int
    max_height: int
    crf: int
    preset: str
    keyframe_interval_seconds: int
    media_timescale: int

    def identity_values(self) -> dict[str, int | str]:
        return {
            "name": self.name,
            "container": self.container,
            "codec": self.codec,
            "pixel_format": self.pixel_format,
            "mime_type": self.mime_type,
            "max_width": self.max_width,
            "max_height": self.max_height,
            "crf": self.crf,
            "preset": self.preset,
            "keyframe_interval_seconds": self.keyframe_interval_seconds,
            "media_timescale": self.media_timescale,
        }


V0_PREVIEW_PROFILE = PreviewProfile(
    name=DEFAULT_PREVIEW_PROFILE,
    container="mp4",
    codec="libx264",
    pixel_format="yuv420p",
    mime_type="video/mp4",
    max_width=1280,
    max_height=720,
    crf=23,
    preset="veryfast",
    keyframe_interval_seconds=2,
    media_timescale=1_000_000,
)


class ConfigurationError(ValueError):
    """A safe configuration error suitable for startup diagnostics."""


@dataclass(frozen=True)
class AppConfig:
    archive_root: Path
    derived_root: Path
    database_url: str
    front_topic: str
    preview_profile: PreviewProfile
    ffmpeg_path: Path
    ffprobe_path: Path

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "AppConfig":
        values = os.environ if environment is None else environment
        archive_value = _required(values, ARCHIVE_ROOT_ENV)
        derived_value = _required(values, DERIVED_ROOT_ENV)
        database_url = _required(values, DATABASE_URL_ENV)
        return cls.create(
            archive_value,
            derived_value,
            database_url,
            front_topic=values.get(FRONT_TOPIC_ENV, DEFAULT_FRONT_TOPIC),
            preview_profile=values.get(
                PREVIEW_PROFILE_ENV, DEFAULT_PREVIEW_PROFILE
            ),
            ffmpeg_path=values.get(FFMPEG_ENV, "ffmpeg"),
            ffprobe_path=values.get(FFPROBE_ENV, "ffprobe"),
        )

    @classmethod
    def create(
        cls,
        archive_root: str | Path,
        derived_root: str | Path,
        database_url: str,
        *,
        front_topic: str = DEFAULT_FRONT_TOPIC,
        preview_profile: str = DEFAULT_PREVIEW_PROFILE,
        ffmpeg_path: str | Path = "ffmpeg",
        ffprobe_path: str | Path = "ffprobe",
    ) -> "AppConfig":
        archive = _validated_directory(Path(archive_root), "archive root", writable=False)
        derived = _validated_directory(Path(derived_root), "derived root", writable=True)
        _reject_overlapping_roots(archive, derived)
        _validate_database_url(database_url)
        topic = _validated_topic(front_topic)
        profile = _validated_preview_profile(preview_profile)
        ffmpeg = _validated_executable(
            ffmpeg_path, "FFmpeg", expected_version_prefix="ffmpeg version"
        )
        ffprobe = _validated_executable(
            ffprobe_path, "ffprobe", expected_version_prefix="ffprobe version"
        )
        return cls(
            archive_root=archive,
            derived_root=derived,
            database_url=database_url,
            front_topic=topic,
            preview_profile=profile,
            ffmpeg_path=ffmpeg,
            ffprobe_path=ffprobe,
        )


def database_url_from_environment(
    environment: Mapping[str, str] | None = None,
) -> str:
    values = os.environ if environment is None else environment
    database_url = _required(values, DATABASE_URL_ENV)
    _validate_database_url(database_url)
    return database_url


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required setting {name} is missing.")
    return value


def _validated_directory(path: Path, label: str, *, writable: bool) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ConfigurationError(f"The configured {label} is unavailable.") from error

    if not resolved.is_dir():
        raise ConfigurationError(f"The configured {label} is not a directory.")

    required_access = os.R_OK | os.X_OK
    if writable:
        required_access |= os.W_OK
    if not os.access(resolved, required_access):
        raise ConfigurationError(f"The configured {label} has insufficient permissions.")
    return resolved


def _reject_overlapping_roots(archive: Path, derived: Path) -> None:
    try:
        overlap = (
            archive == derived
            or archive in derived.parents
            or derived in archive.parents
            or os.path.samefile(archive, derived)
            or any(os.path.samefile(archive, parent) for parent in derived.parents)
            or any(os.path.samefile(derived, parent) for parent in archive.parents)
        )
    except OSError as error:
        raise ConfigurationError(
            "Archive and derived roots could not be compared safely."
        ) from error
    if overlap:
        raise ConfigurationError("Archive and derived roots must not overlap.")


def _validate_database_url(database_url: str) -> None:
    try:
        parsed = urlsplit(database_url)
    except ValueError as error:
        raise ConfigurationError("The PostgreSQL URL is invalid.") from error
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.path:
        raise ConfigurationError("The database setting must be a PostgreSQL URL.")


def _validated_topic(value: str) -> str:
    topic = value.strip()
    if ROS_TOPIC_PATTERN.fullmatch(topic) is None:
        raise ConfigurationError("The configured front-camera topic is invalid.")
    return topic


def _validated_preview_profile(value: str) -> PreviewProfile:
    name = value.strip()
    if name != DEFAULT_PREVIEW_PROFILE:
        raise ConfigurationError(
            f"The configured preview profile must be {DEFAULT_PREVIEW_PROFILE}."
        )
    return V0_PREVIEW_PROFILE


def _validated_executable(
    value: str | Path, label: str, *, expected_version_prefix: str
) -> Path:
    raw = os.fspath(value).strip()
    candidate = shutil.which(raw)
    if candidate is None:
        raise ConfigurationError(f"The configured {label} executable is unavailable.")
    try:
        resolved = Path(candidate).resolve(strict=True)
    except OSError as error:
        raise ConfigurationError(
            f"The configured {label} executable is unavailable."
        ) from error
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ConfigurationError(
            f"The configured {label} executable is not executable."
        )
    try:
        completed = subprocess.run(
            [os.fspath(resolved), "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ConfigurationError(
            f"The configured {label} executable could not be verified."
        ) from error
    version_output = f"{completed.stdout}\n{completed.stderr}".lstrip().lower()
    if not version_output.startswith(expected_version_prefix.lower()):
        raise ConfigurationError(
            f"The configured {label} executable has the wrong identity."
        )
    return resolved
