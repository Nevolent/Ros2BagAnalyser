from __future__ import annotations

import os
from pathlib import Path

import pytest

from rosbag_analyser.config import (
    DEFAULT_FRONT_TOPIC,
    DEFAULT_IMU_COMPONENT,
    DEFAULT_PREVIEW_PROFILE,
    AppConfig,
    ConfigurationError,
)


DATABASE_URL = "postgresql://catalog_user:secret@example.invalid/catalog"
DEPLOYMENT_DATABASE_URL = (
    "postgresql://rosbag_analyser_runtime@/rosbag_analyser?host=/run/postgresql"
)
IMU_TOPIC = "/sensors/imu"


def test_accepts_existing_separate_roots(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    config = AppConfig.create(archive, derived, DATABASE_URL, imu_topic=IMU_TOPIC)

    assert config.archive_root == archive.resolve()
    assert config.derived_root == derived.resolve()
    assert config.front_topic == DEFAULT_FRONT_TOPIC
    assert config.imu_topic == IMU_TOPIC
    assert config.imu_component == DEFAULT_IMU_COMPONENT
    assert config.preview_profile.name == DEFAULT_PREVIEW_PROFILE
    assert config.ffmpeg_path.is_file()
    assert config.ffprobe_path.is_file()


@pytest.mark.parametrize("nested_side", ["archive", "derived"])
def test_rejects_overlapping_roots(tmp_path: Path, nested_side: str) -> None:
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    archive, derived = (parent, child) if nested_side == "archive" else (child, parent)

    with pytest.raises(ConfigurationError, match="must not overlap"):
        AppConfig.create(archive, derived, DATABASE_URL, imu_topic=IMU_TOPIC)


def test_rejects_same_root_through_symlink_alias(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="must not overlap"):
        AppConfig.create(root, alias, DATABASE_URL, imu_topic=IMU_TOPIC)


def test_deployment_environment_rejects_symlink_root(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    source_alias = tmp_path / "source-alias"
    source_alias.symlink_to(archive, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="symbolic link"):
        AppConfig.from_environment(
            {
                "ROS_BAG_ANALYSER_DEPLOYMENT_MODE": "1",
                "ROS_BAG_ANALYSER_ARCHIVE_ROOT": str(source_alias),
                "ROS_BAG_ANALYSER_DERIVED_ROOT": str(derived),
                "ROS_BAG_ANALYSER_DATABASE_URL": DATABASE_URL,
                "ROS_BAG_ANALYSER_IMU_TOPIC": IMU_TOPIC,
            }
        )


def test_deployment_allows_root_owned_style_derived_mountpoint(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir(mode=0o555)

    config = AppConfig.from_environment(
        {
            "ROS_BAG_ANALYSER_DEPLOYMENT_MODE": "1",
            "ROS_BAG_ANALYSER_ARCHIVE_ROOT": str(archive),
            "ROS_BAG_ANALYSER_DERIVED_ROOT": str(derived),
            "ROS_BAG_ANALYSER_DATABASE_URL": DEPLOYMENT_DATABASE_URL,
            "ROS_BAG_ANALYSER_IMU_TOPIC": IMU_TOPIC,
        }
    )

    assert config.derived_root == derived.resolve()


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://rosbag_analyser_runtime:secret@/rosbag_analyser?host=/run/postgresql",
        "postgresql://rosbag_analyser_runtime@database.internal/rosbag_analyser",
        "postgresql://postgres@/rosbag_analyser?host=/run/postgresql",
    ],
)
def test_deployment_rejects_password_network_or_privileged_database_url(
    tmp_path: Path, database_url: str
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="deployment") as captured:
        AppConfig.from_environment(
            {
                "ROS_BAG_ANALYSER_DEPLOYMENT_MODE": "1",
                "ROS_BAG_ANALYSER_ARCHIVE_ROOT": str(archive),
                "ROS_BAG_ANALYSER_DERIVED_ROOT": str(derived),
                "ROS_BAG_ANALYSER_DATABASE_URL": database_url,
                "ROS_BAG_ANALYSER_IMU_TOPIC": IMU_TOPIC,
            }
        )

    assert "secret" not in str(captured.value)


def test_rejects_roots_when_filesystem_identity_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    original_samefile = os.path.samefile

    def samefile_with_case_alias(left: object, right: object) -> bool:
        pair = {Path(left), Path(right)}
        if pair == {archive.resolve(), derived.resolve()}:
            return True
        return original_samefile(left, right)

    monkeypatch.setattr(os.path, "samefile", samefile_with_case_alias)

    with pytest.raises(ConfigurationError, match="must not overlap"):
        AppConfig.create(archive, derived, DATABASE_URL, imu_topic=IMU_TOPIC)


def test_rejects_non_postgresql_url_without_exposing_secret(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError) as captured:
        AppConfig.create(
            archive, derived, "sqlite:///secret-value", imu_topic=IMU_TOPIC
        )

    assert "secret-value" not in str(captured.value)


def test_environment_requires_all_settings(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="ARCHIVE_ROOT"):
        AppConfig.from_environment({})


def test_environment_requires_imu_topic(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="IMU_TOPIC"):
        AppConfig.from_environment(
            {
                "ROS_BAG_ANALYSER_ARCHIVE_ROOT": str(archive),
                "ROS_BAG_ANALYSER_DERIVED_ROOT": str(derived),
                "ROS_BAG_ANALYSER_DATABASE_URL": DATABASE_URL,
            }
        )


@pytest.mark.parametrize(
    "topic",
    [
        "camera/image",
        "/",
        "/camera/",
        "/camera//image",
        "/camera image",
        "/camera/9image",
        "/camera/image.raw",
        "/camera/../image",
        "/camera/#image",
    ],
)
def test_rejects_invalid_front_camera_topics(tmp_path: Path, topic: str) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="front-camera topic"):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            front_topic=topic,
        )


@pytest.mark.parametrize("topic", ["imu", "/imu/", "/imu data"])
def test_rejects_invalid_imu_topics(tmp_path: Path, topic: str) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="IMU topic"):
        AppConfig.create(archive, derived, DATABASE_URL, imu_topic=topic)


def test_rejects_unknown_imu_component(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="supported raw angular-velocity"):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            imu_component="orientation.x",
        )


def test_accepts_supported_imu_component(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    config = AppConfig.create(
        archive,
        derived,
        DATABASE_URL,
        imu_topic=IMU_TOPIC,
        imu_component="linear_acceleration.x",
    )

    assert config.imu_component == "linear_acceleration.x"


def test_catalog_and_preparation_bounds_have_conservative_defaults(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    config = AppConfig.create(
        archive,
        derived,
        DATABASE_URL,
        imu_topic=IMU_TOPIC,
    )

    assert config.catalog_scan_limits.max_depth == 8
    assert config.catalog_scan_limits.max_entries == 100_000
    assert config.prepare_max_recordings == 100


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("catalog_max_depth", 0),
        ("catalog_max_entries", -1),
        ("catalog_max_directories", 0),
        ("catalog_max_recordings", 0),
        ("catalog_max_directory_entries", 0),
        ("catalog_max_recording_entries", 0),
        ("prepare_max_recordings", 0),
    ],
)
def test_rejects_nonpositive_operational_bounds(
    tmp_path: Path,
    argument: str,
    value: int,
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="positive integer"):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            **{argument: value},
        )


def test_rejects_unknown_preview_profile(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match=DEFAULT_PREVIEW_PROFILE):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            preview_profile="future-profile",
        )


def test_rejects_missing_media_executable(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="FFmpeg executable"):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            ffmpeg_path="definitely-not-a-real-ffmpeg-command",
        )


def test_rejects_executable_with_wrong_media_identity(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError, match="wrong identity"):
        AppConfig.create(
            archive,
            derived,
            DATABASE_URL,
            imu_topic=IMU_TOPIC,
            ffmpeg_path="/bin/true",
        )
