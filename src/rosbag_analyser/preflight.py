from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Sequence

from rosbag_analyser.config import AppConfig, ConfigurationError
from rosbag_analyser.deployment import (
    DeploymentConfigurationError,
    DeploymentSettings,
    build_admission_guard,
)
from rosbag_analyser.persistence.database import (
    CatalogSchemaError,
    validate_catalog_schema,
)


HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_BUILD_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,127}$")
UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RELEASE_MANIFEST_FIELDS = {
    "schema_version",
    "release_id",
    "application_version",
    "source_revision",
    "source_archive_sha256",
    "dependency_manifest_sha256",
    "release_contract_sha256",
    "worktree_clean",
    "built_at",
    "build_operator",
}


def validate_private_file(
    path: Path,
    *,
    required_owner_uid: int = 0,
    allowed_modes: tuple[int, ...] = (0o400, 0o600, 0o640),
) -> None:
    try:
        details = path.lstat()
    except OSError as error:
        raise DeploymentConfigurationError(
            "A required private configuration file is unavailable."
        ) from error
    if stat.S_ISLNK(details.st_mode):
        raise DeploymentConfigurationError(
            "A private configuration file must not be a symbolic link."
        )
    if not stat.S_ISREG(details.st_mode):
        raise DeploymentConfigurationError(
            "A private configuration path is not a regular file."
        )
    if details.st_uid != required_owner_uid:
        raise DeploymentConfigurationError(
            "A private configuration file has the wrong owner."
        )
    mode = stat.S_IMODE(details.st_mode)
    if mode not in allowed_modes:
        raise DeploymentConfigurationError(
            "A private configuration file has an unsafe mode."
        )


def validate_release_manifest(
    manifest_path: Path,
    dependency_manifest_path: Path,
    release_contract_path: Path,
    *,
    expected_release_id: str,
) -> dict[str, Any]:
    try:
        before = manifest_path.stat(follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or manifest_path.is_symlink():
            raise OSError("manifest is not a regular file")
        payload = manifest_path.read_bytes()
        if len(payload) > 64 * 1024:
            raise OSError("manifest is too large")
        document = json.loads(payload.decode("utf-8"))
        after = manifest_path.stat(follow_symlinks=False)
        dependency_payload = dependency_manifest_path.read_bytes()
        release_contract_payload = release_contract_path.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DeploymentConfigurationError(
            "The installed release identity is unavailable."
        ) from error
    if before != after or not isinstance(document, dict):
        raise DeploymentConfigurationError(
            "The installed release identity changed during validation."
        )
    if set(document) != RELEASE_MANIFEST_FIELDS:
        raise DeploymentConfigurationError(
            "The installed release identity has an unsupported format."
        )
    if (
        document["schema_version"] != 1
        or document["release_id"] != expected_release_id
        or not isinstance(document["application_version"], str)
        or not document["application_version"]
        or not isinstance(document["source_revision"], str)
        or HEX_40.fullmatch(document["source_revision"]) is None
        or not isinstance(document["source_archive_sha256"], str)
        or HEX_64.fullmatch(document["source_archive_sha256"]) is None
        or document["worktree_clean"] is not True
        or not isinstance(document["built_at"], str)
        or UTC_TIMESTAMP.fullmatch(document["built_at"]) is None
        or not isinstance(document["build_operator"], str)
        or SAFE_BUILD_OPERATOR.fullmatch(document["build_operator"]) is None
    ):
        raise DeploymentConfigurationError(
            "The installed release source identity is invalid."
        )
    dependency_checksum = hashlib.sha256(dependency_payload).hexdigest()
    if (
        not isinstance(document["dependency_manifest_sha256"], str)
        or document["dependency_manifest_sha256"] != dependency_checksum
    ):
        raise DeploymentConfigurationError(
            "The installed release dependency identity is invalid."
        )
    release_contract_checksum = hashlib.sha256(release_contract_payload).hexdigest()
    if (
        not isinstance(document["release_contract_sha256"], str)
        or document["release_contract_sha256"] != release_contract_checksum
    ):
        raise DeploymentConfigurationError(
            "The installed release contract identity is invalid."
        )
    return document


def verify_ros_runtime() -> None:
    try:
        importlib.import_module("rclpy.serialization")
        importlib.import_module("sensor_msgs.msg")
    except ImportError as error:
        raise DeploymentConfigurationError(
            "The required ROS 2 Humble Python runtime is unavailable."
        ) from error


def verify_encoder_capability(ffmpeg_path: Path) -> None:
    try:
        completed = subprocess.run(
            [os.fspath(ffmpeg_path), "-hide_banner", "-encoders"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeploymentConfigurationError(
            "FFmpeg encoder capabilities could not be verified."
        ) from error
    if "libx264" not in completed.stdout:
        raise DeploymentConfigurationError(
            "The required H.264 encoder capability is unavailable."
        )


def verify_probe_capability(ffprobe_path: Path) -> None:
    try:
        completed = subprocess.run(
            [os.fspath(ffprobe_path), "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeploymentConfigurationError(
            "The required ffprobe capability is unavailable."
        ) from error
    if not completed.stdout.startswith("ffprobe version"):
        raise DeploymentConfigurationError(
            "The required ffprobe capability is unavailable."
        )


def run_preflight(
    config: AppConfig,
    settings: DeploymentSettings,
    *,
    activation: bool,
    release_root: Path | None = None,
) -> tuple[str, ...]:
    if not settings.enabled:
        raise DeploymentConfigurationError(
            "Deployment preflight requires deployment mode."
        )
    checks: list[str] = []
    if release_root is not None:
        validate_release_manifest(
            release_root / "release-manifest.json",
            release_root / "wheelhouse" / "SHA256SUMS",
            release_root / "deploy" / "release-contract.json",
            expected_release_id=settings.release_id,
        )
        checks.append("release_identity")
    validate_catalog_schema(config.database_url)
    admission = build_admission_guard(
        config.archive_root,
        config.derived_root,
        settings,
    )
    diagnostic = admission.diagnostic()
    if diagnostic is not None:
        raise DeploymentConfigurationError(diagnostic.message)
    verify_ros_runtime()
    verify_encoder_capability(config.ffmpeg_path)
    verify_probe_capability(config.ffprobe_path)
    if activation:
        assert admission.derived_guard is not None
        admission.derived_guard.verify_atomic_rename()
    checks.extend(
        (
            "release_configuration",
            "database_schema",
            "source_mount",
            "derived_mount_and_capacity",
            "ros_runtime",
            "ffmpeg_h264",
            "ffprobe",
        )
    )
    if activation:
        checks.append("derived_atomic_rename")
    return tuple(checks)


def main(arguments: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate the ROS Bag Analyser deployment without scanning source data."
    )
    parser.add_argument(
        "--activation",
        action="store_true",
        help="also run a contained derived-filesystem atomic rename check",
    )
    parsed = parser.parse_args(arguments)
    try:
        config = AppConfig.from_environment()
        settings = DeploymentSettings.from_environment()
        release_root_setting = os.environ.get("ROS_BAG_ANALYSER_RELEASE_ROOT")
        release_root = (
            Path(release_root_setting)
            if release_root_setting
            else Path(sys.prefix).parent
        )
        checks = run_preflight(
            config,
            settings,
            activation=parsed.activation,
            release_root=release_root,
        )
    except (
        CatalogSchemaError,
        ConfigurationError,
        DeploymentConfigurationError,
    ) as error:
        raise SystemExit(str(error)) from error
    print("Deployment preflight passed: " + ", ".join(checks))


if __name__ == "__main__":
    main()


__all__ = [
    "run_preflight",
    "validate_private_file",
    "validate_release_manifest",
    "verify_encoder_capability",
    "verify_probe_capability",
    "verify_ros_runtime",
]
