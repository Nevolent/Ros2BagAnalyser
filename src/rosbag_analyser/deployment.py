from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Callable, Mapping

from rosbag_analyser.catalog.types import SafeDiagnostic


DEPLOYMENT_MODE_ENV = "ROS_BAG_ANALYSER_DEPLOYMENT_MODE"
RELEASE_ID_ENV = "ROS_BAG_ANALYSER_RELEASE_ID"
BIND_HOST_ENV = "ROS_BAG_ANALYSER_BIND_HOST"
BIND_PORT_ENV = "ROS_BAG_ANALYSER_BIND_PORT"
SOURCE_MOUNT_FSTYPE_ENV = "ROS_BAG_ANALYSER_SOURCE_MOUNT_FSTYPE"
SOURCE_MOUNT_SOURCE_ENV = "ROS_BAG_ANALYSER_SOURCE_MOUNT_SOURCE"
SOURCE_MOUNT_ROOT_ENV = "ROS_BAG_ANALYSER_SOURCE_MOUNT_ROOT"
DERIVED_MOUNT_FSTYPE_ENV = "ROS_BAG_ANALYSER_DERIVED_MOUNT_FSTYPE"
DERIVED_MOUNT_SOURCE_ENV = "ROS_BAG_ANALYSER_DERIVED_MOUNT_SOURCE"
DERIVED_MOUNT_ROOT_ENV = "ROS_BAG_ANALYSER_DERIVED_MOUNT_ROOT"
DERIVED_MIN_FREE_BYTES_ENV = "ROS_BAG_ANALYSER_DERIVED_MIN_FREE_BYTES"
DERIVED_MIN_FREE_PERCENT_ENV = "ROS_BAG_ANALYSER_DERIVED_MIN_FREE_PERCENT"

RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FILESYSTEM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")
NFS_SOURCE_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,252}|\[[0-9A-Fa-f:]+\]):/[^,\s]+$"
)
CIFS_SHARE_PATTERN = re.compile(
    r"^//[A-Za-z0-9][A-Za-z0-9._-]{0,252}/[A-Za-z0-9][A-Za-z0-9._$-]{0,254}$"
)
CIFS_MOUNT_SOURCE_PATTERN = re.compile(
    r"^//[A-Za-z0-9][A-Za-z0-9._-]{0,252}/[A-Za-z0-9][A-Za-z0-9._$-]{0,254}(?:/[A-Za-z0-9][A-Za-z0-9._$-]{0,254})*$"
)
MOUNTINFO_ESCAPE = re.compile(r"\\([0-7]{3})")


class DeploymentConfigurationError(ValueError):
    """A sanitized deployment setting or capability error."""


@dataclass(frozen=True)
class MountExpectation:
    filesystem_type: str
    source: str
    read_only: bool
    required_options: frozenset[str] = frozenset()
    mount_root: str = "/"


@dataclass(frozen=True)
class MountInfo:
    mount_point: Path
    filesystem_type: str
    source: str
    options: frozenset[str]
    device: str
    mount_root: str = "/"


@dataclass(frozen=True)
class DeploymentSettings:
    enabled: bool
    release_id: str
    bind_host: str
    bind_port: int
    source_mount: MountExpectation | None
    derived_mount: MountExpectation | None
    minimum_free_bytes: int
    minimum_free_percent: int

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "DeploymentSettings":
        values = os.environ if environment is None else environment
        mode = values.get(DEPLOYMENT_MODE_ENV, "0").strip()
        if mode not in {"0", "1"}:
            raise DeploymentConfigurationError(
                f"Setting {DEPLOYMENT_MODE_ENV} must be 0 or 1."
            )
        enabled = mode == "1"
        release_id = values.get(RELEASE_ID_ENV, "development").strip()
        bind_host = values.get(BIND_HOST_ENV, "127.0.0.1").strip()
        try:
            bind_port = _integer_setting(values, BIND_PORT_ENV, 8000, minimum=1)
        except DeploymentConfigurationError as error:
            raise DeploymentConfigurationError(
                "The application listener port must be a positive integer."
            ) from error
        if bind_port > 65535:
            raise DeploymentConfigurationError(
                f"Setting {BIND_PORT_ENV} must be a valid TCP port."
            )
        if bind_host not in {"127.0.0.1", "::1", "localhost"}:
            raise DeploymentConfigurationError(
                "The application listener must use an approved loopback address."
            )
        if not enabled:
            return cls(
                False,
                release_id or "development",
                bind_host,
                bind_port,
                None,
                None,
                0,
                0,
            )

        if bind_host != "127.0.0.1":
            raise DeploymentConfigurationError(
                "The deployment application listener must use 127.0.0.1."
            )
        if bind_port != 8000:
            raise DeploymentConfigurationError(
                "The deployment application listener must use port 8000."
            )
        if not release_id:
            raise DeploymentConfigurationError(
                f"Required setting {RELEASE_ID_ENV} is missing."
            )
        if RELEASE_ID_PATTERN.fullmatch(release_id) is None:
            raise DeploymentConfigurationError(
                "The configured release identity is invalid."
            )
        source_type = _required(values, SOURCE_MOUNT_FSTYPE_ENV)
        if source_type not in {"nfs", "nfs4", "cifs"}:
            raise DeploymentConfigurationError(
                "The deployment source filesystem must be NFS or CIFS."
            )
        source_identity = _required(values, SOURCE_MOUNT_SOURCE_ENV)
        source_pattern = (
            CIFS_SHARE_PATTERN if source_type == "cifs" else NFS_SOURCE_PATTERN
        )
        if source_pattern.fullmatch(source_identity) is None:
            raise DeploymentConfigurationError(
                "The deployment source share identity is invalid."
            )
        source_mount_root = _validated_mount_root(
            _required(values, SOURCE_MOUNT_ROOT_ENV)
        )
        derived_type = _validated_filesystem(
            _required(values, DERIVED_MOUNT_FSTYPE_ENV)
        )
        derived_identity = _required(values, DERIVED_MOUNT_SOURCE_ENV)
        if derived_type == "cifs":
            if CIFS_MOUNT_SOURCE_PATTERN.fullmatch(derived_identity) is None:
                raise DeploymentConfigurationError(
                    "The deployment derived share identity is invalid."
                )
        else:
            derived_device = Path(derived_identity)
            if (
                not derived_device.is_absolute()
                or derived_device.parts[:2] != ("/", "dev")
                or ".." in derived_device.parts
            ):
                raise DeploymentConfigurationError(
                    "The deployment derived device identity is invalid."
                )
        derived_mount_root = _validated_mount_root(
            _required(values, DERIVED_MOUNT_ROOT_ENV)
        )
        minimum_free_bytes = _integer_setting(
            values,
            DERIVED_MIN_FREE_BYTES_ENV,
            None,
            minimum=1,
        )
        minimum_free_percent = _integer_setting(
            values,
            DERIVED_MIN_FREE_PERCENT_ENV,
            None,
            minimum=1,
        )
        if minimum_free_percent > 100:
            raise DeploymentConfigurationError(
                f"Setting {DERIVED_MIN_FREE_PERCENT_ENV} must be a percentage from 0 to 100."
            )
        return cls(
            True,
            release_id,
            bind_host,
            bind_port,
            MountExpectation(
                source_type,
                source_identity,
                True,
                frozenset({"ro", "nosuid", "nodev", "noexec"}),
                source_mount_root,
            ),
            MountExpectation(
                derived_type,
                derived_identity,
                False,
                frozenset({"rw", "nosuid", "nodev"}),
                derived_mount_root,
            ),
            minimum_free_bytes,
            minimum_free_percent,
        )


def parse_mountinfo(document: str) -> tuple[MountInfo, ...]:
    mounts: list[MountInfo] = []
    for raw_line in document.splitlines():
        fields = raw_line.split()
        try:
            separator = fields.index("-")
            if separator < 6 or len(fields) < separator + 4:
                raise ValueError
            mount_options = fields[5].split(",")
            mounts.append(
                MountInfo(
                    mount_point=Path(_decode_mountinfo(fields[4])),
                    filesystem_type=fields[separator + 1],
                    source=_decode_mountinfo(fields[separator + 2]),
                    # Per-mount VFS options govern this exact path. A read-only
                    # bind may legitimately sit above a read-write CIFS
                    # superblock, whose separate options must not override it.
                    options=frozenset(mount_options),
                    device=fields[2],
                    mount_root=_decode_mountinfo(fields[3]),
                )
            )
        except (IndexError, ValueError) as error:
            raise DeploymentConfigurationError(
                "The operating-system mount table is malformed."
            ) from error
    return tuple(mounts)


def read_mountinfo(path: Path = Path("/proc/self/mountinfo")) -> tuple[MountInfo, ...]:
    try:
        return parse_mountinfo(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise DeploymentConfigurationError(
            "The operating-system mount table is unavailable."
        ) from error


class DerivedStorageGuard:
    def __init__(
        self,
        derived_root: Path,
        expectation: MountExpectation | None,
        *,
        minimum_free_bytes: int,
        minimum_free_percent: int,
        mount_reader: Callable[[], tuple[MountInfo, ...]] = read_mountinfo,
        statvfs: Callable[[Path], os.statvfs_result] = os.statvfs,
        marker_owner_uid: int = 0,
    ) -> None:
        self.derived_root = derived_root
        self.expectation = expectation
        self.minimum_free_bytes = minimum_free_bytes
        self.minimum_free_percent = minimum_free_percent
        self.mount_reader = mount_reader
        self.statvfs = statvfs
        self.marker_owner_uid = marker_owner_uid

    def diagnostic(self) -> SafeDiagnostic | None:
        availability = self.availability_diagnostic()
        if availability is not None:
            return availability
        try:
            facts = self.statvfs(self.derived_root)
            fragment_size = facts.f_frsize or facts.f_bsize
            free_bytes = facts.f_bavail * fragment_size
            free_percent = (
                0 if facts.f_blocks <= 0 else (facts.f_bavail * 100) // facts.f_blocks
            )
        except (OSError, ValueError):
            return SafeDiagnostic(
                "derived_storage_unavailable",
                "The trusted derived storage is unavailable.",
            )
        if (
            free_bytes < self.minimum_free_bytes
            or free_percent < self.minimum_free_percent
        ):
            return SafeDiagnostic(
                "derived_space_low",
                "New preparation is paused because derived storage is low on space.",
            )
        return None

    def availability_diagnostic(self) -> SafeDiagnostic | None:
        mount_diagnostic = self.mount_diagnostic()
        if mount_diagnostic is not None:
            return mount_diagnostic
        owned_root = self.derived_root / "rosbag-analyser"
        try:
            if (
                not self.derived_root.is_dir()
                or self.derived_root.is_symlink()
                or not os.access(self.derived_root, os.R_OK | os.X_OK)
                or not owned_root.is_dir()
                or owned_root.is_symlink()
                or not os.access(owned_root, os.R_OK | os.W_OK | os.X_OK)
            ):
                raise OSError("derived root permissions are invalid")
            if self.expectation is not None:
                marker = self.derived_root / ".rosbag-analyser-derived-v1"
                marker_details = marker.stat(follow_symlinks=False)
                if (
                    marker.is_symlink()
                    or not stat.S_ISREG(marker_details.st_mode)
                    or (
                        self.expectation.filesystem_type != "cifs"
                        and (
                            marker_details.st_uid != self.marker_owner_uid
                            or stat.S_IMODE(marker_details.st_mode)
                            not in {0o400, 0o440, 0o444}
                        )
                    )
                    or marker.read_bytes() != b"rosbag-analyser-derived-v1\n"
                ):
                    raise OSError("derived ownership marker is invalid")
            self.statvfs(self.derived_root)
        except (OSError, ValueError):
            return SafeDiagnostic(
                "derived_storage_unavailable",
                "The trusted derived storage is unavailable.",
            )
        return None

    def mount_diagnostic(self) -> SafeDiagnostic | None:
        if self.expectation is None:
            return None
        return _mount_diagnostic(
            self.derived_root,
            self.expectation,
            self.mount_reader,
            missing_code="derived_mount_unavailable",
            invalid_code="derived_mount_identity_invalid",
            message="The trusted derived storage mount is unavailable.",
        )

    def verify_atomic_rename(self) -> None:
        diagnostic = self.diagnostic()
        if diagnostic is not None:
            raise DeploymentConfigurationError(diagnostic.message)
        owned = self.derived_root / "rosbag-analyser" / "preflight"
        owned.mkdir(mode=0o750, parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="atomic-", dir=owned) as temporary:
            source = Path(temporary) / "source"
            destination = Path(temporary) / "destination"
            source.write_bytes(b"preflight")
            os.rename(source, destination)
            if destination.read_bytes() != b"preflight":
                raise DeploymentConfigurationError(
                    "The derived filesystem failed its atomic publication check."
                )


class ProcessingAdmissionGuard:
    def __init__(
        self,
        source_root: Path,
        source_expectation: MountExpectation | None,
        derived_guard: DerivedStorageGuard | None,
        *,
        mount_reader: Callable[[], tuple[MountInfo, ...]] = read_mountinfo,
    ) -> None:
        self.source_root = source_root
        self.source_expectation = source_expectation
        self.derived_guard = derived_guard
        self.mount_reader = mount_reader

    def source_diagnostic(self) -> SafeDiagnostic | None:
        if self.source_expectation is not None:
            diagnostic = _mount_diagnostic(
                self.source_root,
                self.source_expectation,
                self.mount_reader,
                missing_code="source_mount_unavailable",
                invalid_code="source_mount_identity_invalid",
                message="The trusted read-only source mount is unavailable.",
            )
            if diagnostic is not None:
                return diagnostic
        try:
            if (
                not self.source_root.is_dir()
                or self.source_root.is_symlink()
                or not os.access(self.source_root, os.R_OK | os.X_OK)
            ):
                raise OSError("source root permissions are invalid")
        except OSError:
            return SafeDiagnostic(
                "source_access_unavailable",
                "The trusted read-only source is unavailable.",
            )
        return None

    def diagnostic(self) -> SafeDiagnostic | None:
        source = self.source_diagnostic()
        if source is not None:
            return source
        if self.derived_guard is None:
            return None
        return self.derived_guard.diagnostic()


def build_admission_guard(
    source_root: Path,
    derived_root: Path,
    settings: DeploymentSettings,
) -> ProcessingAdmissionGuard:
    derived = DerivedStorageGuard(
        derived_root,
        settings.derived_mount,
        minimum_free_bytes=settings.minimum_free_bytes,
        minimum_free_percent=settings.minimum_free_percent,
    )
    return ProcessingAdmissionGuard(
        source_root,
        settings.source_mount,
        derived,
    )


def validate_startup_mounts(
    settings: DeploymentSettings,
    guard: ProcessingAdmissionGuard,
) -> None:
    if not settings.enabled:
        return
    source = guard.source_diagnostic()
    derived = (
        None
        if guard.derived_guard is None
        else guard.derived_guard.mount_diagnostic()
    )
    diagnostic = source or derived
    if diagnostic is not None:
        raise DeploymentConfigurationError(diagnostic.message)


def _mount_diagnostic(
    root: Path,
    expectation: MountExpectation,
    mount_reader: Callable[[], tuple[MountInfo, ...]],
    *,
    missing_code: str,
    invalid_code: str,
    message: str,
) -> SafeDiagnostic | None:
    try:
        mounts = mount_reader()
    except DeploymentConfigurationError:
        return SafeDiagnostic(missing_code, message)
    exact = next((mount for mount in mounts if mount.mount_point == root), None)
    if exact is None:
        return SafeDiagnostic(missing_code, message)
    expected_option = "ro" if expectation.read_only else "rw"
    forbidden_option = "rw" if expectation.read_only else "ro"
    if (
        exact.filesystem_type != expectation.filesystem_type
        or not _mount_source_matches(exact.source, expectation.source)
        or exact.mount_root != expectation.mount_root
        or expected_option not in exact.options
        or forbidden_option in exact.options
        or not expectation.required_options.issubset(exact.options)
    ):
        return SafeDiagnostic(invalid_code, message)
    return None


def _mount_source_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if not actual.startswith("/") or not expected.startswith("/"):
        return False
    try:
        return Path(actual).resolve(strict=True) == Path(expected).resolve(strict=True)
    except OSError:
        return False


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise DeploymentConfigurationError(f"Required setting {name} is missing.")
    if any(ord(character) < 32 for character in value):
        raise DeploymentConfigurationError(f"Setting {name} is invalid.")
    return value


def _integer_setting(
    values: Mapping[str, str],
    name: str,
    default: int | None,
    *,
    minimum: int,
) -> int:
    raw = values.get(name)
    if raw is None:
        if default is None:
            raise DeploymentConfigurationError(f"Required setting {name} is missing.")
        return default
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError) as error:
        raise DeploymentConfigurationError(
            f"Setting {name} must be a non-negative integer."
        ) from error
    if value < minimum:
        description = "positive" if minimum > 0 else "non-negative"
        raise DeploymentConfigurationError(
            f"Setting {name} must be a {description} integer."
        )
    return value


def _validated_filesystem(value: str) -> str:
    if FILESYSTEM_PATTERN.fullmatch(value) is None:
        raise DeploymentConfigurationError(
            "The configured derived filesystem type is invalid."
        )
    return value


def _validated_mount_root(value: str) -> str:
    candidate = PurePosixPath(value)
    if (
        not value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in candidate.parts[1:])
        or candidate.as_posix() != value
    ):
        raise DeploymentConfigurationError(
            "The configured mount root is invalid."
        )
    return value


def _decode_mountinfo(value: str) -> str:
    return MOUNTINFO_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


__all__ = [
    "DeploymentConfigurationError",
    "DeploymentSettings",
    "DerivedStorageGuard",
    "MountExpectation",
    "MountInfo",
    "ProcessingAdmissionGuard",
    "build_admission_guard",
    "parse_mountinfo",
    "read_mountinfo",
    "validate_startup_mounts",
]
