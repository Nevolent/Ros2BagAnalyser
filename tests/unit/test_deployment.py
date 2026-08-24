from __future__ import annotations

import os
from pathlib import Path

import pytest

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.deployment import (
    DeploymentConfigurationError,
    DeploymentSettings,
    DerivedStorageGuard,
    MountExpectation,
    MountInfo,
    ProcessingAdmissionGuard,
    parse_mountinfo,
)


def _deployment_environment() -> dict[str, str]:
    return {
        "ROS_BAG_ANALYSER_DEPLOYMENT_MODE": "1",
        "ROS_BAG_ANALYSER_RELEASE_ID": "v1-20260816.1",
        "ROS_BAG_ANALYSER_BIND_HOST": "127.0.0.1",
        "ROS_BAG_ANALYSER_BIND_PORT": "8000",
        "ROS_BAG_ANALYSER_SOURCE_MOUNT_FSTYPE": "nfs4",
        "ROS_BAG_ANALYSER_SOURCE_MOUNT_SOURCE": "nas.invalid:/fixed-recordings",
        "ROS_BAG_ANALYSER_DERIVED_MOUNT_FSTYPE": "ext4",
        "ROS_BAG_ANALYSER_DERIVED_MOUNT_SOURCE": "/dev/disk/by-uuid/example",
        "ROS_BAG_ANALYSER_DERIVED_MIN_FREE_BYTES": "1073741824",
        "ROS_BAG_ANALYSER_DERIVED_MIN_FREE_PERCENT": "10",
    }


def test_local_settings_preserve_loopback_defaults() -> None:
    settings = DeploymentSettings.from_environment({})

    assert not settings.enabled
    assert settings.release_id == "development"
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8000
    assert settings.source_mount is None
    assert settings.derived_mount is None


def test_deployment_settings_require_exact_fail_closed_values() -> None:
    environment = _deployment_environment()

    settings = DeploymentSettings.from_environment(environment)

    assert settings.enabled
    assert settings.release_id == "v1-20260816.1"
    assert settings.source_mount == MountExpectation(
        "nfs4",
        "nas.invalid:/fixed-recordings",
        read_only=True,
        required_options=frozenset({"ro", "nosuid", "nodev", "noexec"}),
    )
    assert settings.derived_mount == MountExpectation(
        "ext4",
        "/dev/disk/by-uuid/example",
        read_only=False,
        required_options=frozenset({"rw", "nosuid", "nodev"}),
    )
    assert settings.minimum_free_bytes == 1_073_741_824
    assert settings.minimum_free_percent == 10


def test_deployment_settings_accept_exact_cifs_source_share() -> None:
    environment = _deployment_environment()
    environment["ROS_BAG_ANALYSER_SOURCE_MOUNT_FSTYPE"] = "cifs"
    environment["ROS_BAG_ANALYSER_SOURCE_MOUNT_SOURCE"] = (
        "//nas.invalid/TO_Rosbag_databank"
    )

    settings = DeploymentSettings.from_environment(environment)

    assert settings.source_mount == MountExpectation(
        "cifs",
        "//nas.invalid/TO_Rosbag_databank",
        read_only=True,
        required_options=frozenset({"ro", "nosuid", "nodev", "noexec"}),
    )


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ROS_BAG_ANALYSER_RELEASE_ID", "", "RELEASE_ID"),
        ("ROS_BAG_ANALYSER_RELEASE_ID", "../../escape", "release identity"),
        ("ROS_BAG_ANALYSER_BIND_HOST", "0.0.0.0", "loopback"),
        ("ROS_BAG_ANALYSER_BIND_HOST", "::", "loopback"),
        ("ROS_BAG_ANALYSER_BIND_HOST", "::1", "127.0.0.1"),
        ("ROS_BAG_ANALYSER_BIND_PORT", "0", "port"),
        ("ROS_BAG_ANALYSER_BIND_PORT", "9000", "port 8000"),
        ("ROS_BAG_ANALYSER_SOURCE_MOUNT_FSTYPE", "ext4", "NFS or CIFS"),
        ("ROS_BAG_ANALYSER_SOURCE_MOUNT_SOURCE", "broad-relative", "share identity"),
        ("ROS_BAG_ANALYSER_DERIVED_MOUNT_SOURCE", "relative-device", "device identity"),
        ("ROS_BAG_ANALYSER_DERIVED_MIN_FREE_BYTES", "0", "positive"),
        ("ROS_BAG_ANALYSER_DERIVED_MIN_FREE_PERCENT", "101", "percentage"),
    ],
)
def test_deployment_settings_reject_unsafe_values(
    name: str, value: str, message: str
) -> None:
    environment = _deployment_environment()
    environment[name] = value

    with pytest.raises(DeploymentConfigurationError, match=message):
        DeploymentSettings.from_environment(environment)


def test_mountinfo_parser_decodes_paths_and_keeps_exact_identity() -> None:
    document = (
        "36 25 0:32 / /srv/rosbag\\040source ro,nosuid,nodev,noexec - "
        "nfs4 nas.invalid:/fixed\\040recordings ro,vers=4.2\n"
        "37 25 8:16 / /var/lib/rosbag-analyser/derived rw,nodev - "
        "ext4 /dev/vdb1 rw,errors=remount-ro\n"
    )

    mounts = parse_mountinfo(document)

    assert mounts[0] == MountInfo(
        mount_point=Path("/srv/rosbag source"),
        filesystem_type="nfs4",
        source="nas.invalid:/fixed recordings",
        options=frozenset({"ro", "nosuid", "nodev", "noexec"}),
        device="0:32",
    )
    assert mounts[1].mount_point == Path("/var/lib/rosbag-analyser/derived")
    assert "rw" in mounts[1].options


def test_mountinfo_parser_uses_read_only_bind_options_not_rw_cifs_superblock() -> None:
    document = (
        "41 25 0:47 / /srv/rosbag-analyser/source "
        "ro,nosuid,nodev,noexec,relatime - cifs //nas.invalid/recordings "
        "rw,vers=3.1.1,cache=strict\n"
    )

    mount = parse_mountinfo(document)[0]

    assert mount.options == frozenset({"ro", "nosuid", "nodev", "noexec", "relatime"})
    assert "rw" not in mount.options


def test_source_mount_validation_never_write_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    mount = MountInfo(
        source,
        "nfs4",
        "nas.invalid:/fixed-recordings",
        frozenset({"ro", "nosuid", "nodev", "noexec"}),
        "0:32",
    )

    def reject_write_probe(*args: object, **kwargs: object) -> None:
        raise AssertionError("source validation must not open or create a file")

    monkeypatch.setattr(Path, "touch", reject_write_probe)
    monkeypatch.setattr(Path, "write_text", reject_write_probe)

    guard = ProcessingAdmissionGuard(
        source_root=source,
        source_expectation=MountExpectation(
            "nfs4", "nas.invalid:/fixed-recordings", read_only=True
        ),
        derived_guard=None,
        mount_reader=lambda: (mount,),
    )

    assert guard.source_diagnostic() is None


def test_cifs_source_mount_validation_requires_exact_read_only_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    mount = MountInfo(
        source,
        "cifs",
        "//nas.invalid/TO_Rosbag_databank",
        frozenset({"ro", "nosuid", "nodev", "noexec", "vers=3.0"}),
        "0:47",
    )
    guard = ProcessingAdmissionGuard(
        source_root=source,
        source_expectation=MountExpectation(
            "cifs",
            "//nas.invalid/TO_Rosbag_databank",
            read_only=True,
            required_options=frozenset({"ro", "nosuid", "nodev", "noexec"}),
        ),
        derived_guard=None,
        mount_reader=lambda: (mount,),
    )

    assert guard.source_diagnostic() is None

    writable = MountInfo(
        source,
        "cifs",
        "//nas.invalid/TO_Rosbag_databank",
        frozenset({"rw", "nosuid", "nodev", "noexec", "vers=3.0"}),
        "0:47",
    )
    guard.mount_reader = lambda: (writable,)

    assert guard.source_diagnostic() == SafeDiagnostic(
        "source_mount_identity_invalid",
        "The trusted read-only source mount is unavailable.",
    )


def test_wrong_or_writable_source_mount_fails_with_sanitized_diagnostic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    wrong = MountInfo(
        source,
        "nfs4",
        "unexpected.invalid:/broad-export",
        frozenset({"rw"}),
        "0:33",
    )
    guard = ProcessingAdmissionGuard(
        source_root=source,
        source_expectation=MountExpectation(
            "nfs4", "nas.invalid:/fixed-recordings", read_only=True
        ),
        derived_guard=None,
        mount_reader=lambda: (wrong,),
    )

    diagnostic = guard.source_diagnostic()

    assert diagnostic is not None
    assert diagnostic.code == "source_mount_identity_invalid"
    assert "unexpected.invalid" not in diagnostic.message
    assert str(source) not in diagnostic.message


def test_derived_guard_rejects_low_space_and_wrong_mount(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    (derived / "rosbag-analyser").mkdir()
    marker = derived / ".rosbag-analyser-derived-v1"
    marker.write_text("rosbag-analyser-derived-v1\n", encoding="ascii")
    marker.chmod(0o444)
    expected = MountExpectation(
        "ext4",
        "/dev/vdb1",
        read_only=False,
        required_options=frozenset({"rw", "nosuid", "nodev"}),
    )
    mount = MountInfo(
        derived,
        "ext4",
        "/dev/vdb1",
        frozenset({"rw", "nosuid", "nodev"}),
        "8:17",
    )
    low = DerivedStorageGuard(
        derived,
        expected,
        minimum_free_bytes=5_000,
        minimum_free_percent=10,
        mount_reader=lambda: (mount,),
        statvfs=lambda _: os.statvfs_result((4096, 4096, 10, 1, 1, 0, 0, 255, 255, 255)),
        marker_owner_uid=os.getuid(),
    )

    diagnostic = low.diagnostic()

    assert diagnostic == SafeDiagnostic(
        "derived_space_low",
        "New preparation is paused because derived storage is low on space.",
    )

    wrong_mount = MountInfo(
        derived,
        "tmpfs",
        "tmpfs",
        frozenset({"rw"}),
        "0:55",
    )
    wrong = DerivedStorageGuard(
        derived,
        expected,
        minimum_free_bytes=0,
        minimum_free_percent=0,
        mount_reader=lambda: (wrong_mount,),
    )
    assert wrong.diagnostic() == SafeDiagnostic(
        "derived_mount_identity_invalid",
        "The trusted derived storage mount is unavailable.",
    )


def test_admission_guard_checks_source_then_derived(tmp_path: Path) -> None:
    source = tmp_path / "source"
    derived = tmp_path / "derived"
    source.mkdir()
    derived.mkdir()
    (derived / "rosbag-analyser").mkdir()
    marker = derived / ".rosbag-analyser-derived-v1"
    marker.write_text("rosbag-analyser-derived-v1\n", encoding="ascii")
    marker.chmod(0o444)
    source_mount = MountInfo(
        source,
        "nfs4",
        "nas.invalid:/fixed-recordings",
        frozenset({"ro", "nosuid", "nodev", "noexec"}),
        "0:32",
    )
    derived_mount = MountInfo(
        derived,
        "ext4",
        "/dev/vdb1",
        frozenset({"rw", "nosuid", "nodev"}),
        "8:17",
    )
    derived_guard = DerivedStorageGuard(
        derived,
        MountExpectation(
            "ext4",
            "/dev/vdb1",
            read_only=False,
            required_options=frozenset({"rw", "nosuid", "nodev"}),
        ),
        minimum_free_bytes=0,
        minimum_free_percent=0,
        mount_reader=lambda: (source_mount, derived_mount),
        marker_owner_uid=os.getuid(),
    )
    guard = ProcessingAdmissionGuard(
        source,
        MountExpectation(
            "nfs4",
            "nas.invalid:/fixed-recordings",
            read_only=True,
            required_options=frozenset({"ro", "nosuid", "nodev", "noexec"}),
        ),
        derived_guard,
        mount_reader=lambda: (source_mount, derived_mount),
    )

    assert guard.diagnostic() is None


def test_atomic_preflight_uses_only_owned_derived_subdirectory(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    owned = derived / "rosbag-analyser"
    owned.mkdir(parents=True)
    ready = owned / "artifacts" / "ready.mp4"
    ready.parent.mkdir()
    ready.write_bytes(b"ready-output")
    marker = derived / ".rosbag-analyser-derived-v1"
    marker.write_text("rosbag-analyser-derived-v1\n", encoding="ascii")
    marker.chmod(0o444)
    mount = MountInfo(
        derived,
        "ext4",
        "/dev/vdb1",
        frozenset({"rw", "nosuid", "nodev"}),
        "8:17",
    )
    guard = DerivedStorageGuard(
        derived,
        MountExpectation(
            "ext4",
            "/dev/vdb1",
            read_only=False,
            required_options=frozenset({"rw", "nosuid", "nodev"}),
        ),
        minimum_free_bytes=1,
        minimum_free_percent=1,
        mount_reader=lambda: (mount,),
        marker_owner_uid=os.getuid(),
    )

    guard.verify_atomic_rename()

    assert ready.read_bytes() == b"ready-output"
    assert list((owned / "preflight").iterdir()) == []
