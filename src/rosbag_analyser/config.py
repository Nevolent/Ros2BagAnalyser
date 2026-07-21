from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


ARCHIVE_ROOT_ENV = "ROS_BAG_ANALYSER_ARCHIVE_ROOT"
DERIVED_ROOT_ENV = "ROS_BAG_ANALYSER_DERIVED_ROOT"
DATABASE_URL_ENV = "ROS_BAG_ANALYSER_DATABASE_URL"


class ConfigurationError(ValueError):
    """A safe configuration error suitable for startup diagnostics."""


@dataclass(frozen=True)
class AppConfig:
    archive_root: Path
    derived_root: Path
    database_url: str

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "AppConfig":
        values = os.environ if environment is None else environment
        archive_value = _required(values, ARCHIVE_ROOT_ENV)
        derived_value = _required(values, DERIVED_ROOT_ENV)
        database_url = _required(values, DATABASE_URL_ENV)
        return cls.create(archive_value, derived_value, database_url)

    @classmethod
    def create(
        cls,
        archive_root: str | Path,
        derived_root: str | Path,
        database_url: str,
    ) -> "AppConfig":
        archive = _validated_directory(Path(archive_root), "archive root", writable=False)
        derived = _validated_directory(Path(derived_root), "derived root", writable=True)
        _reject_overlapping_roots(archive, derived)
        _validate_database_url(database_url)
        return cls(archive_root=archive, derived_root=derived, database_url=database_url)


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
