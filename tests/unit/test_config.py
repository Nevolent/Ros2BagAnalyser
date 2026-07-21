from __future__ import annotations

import os
from pathlib import Path

import pytest

from rosbag_analyser.config import (
    DEFAULT_FRONT_TOPIC,
    DEFAULT_PREVIEW_PROFILE,
    AppConfig,
    ConfigurationError,
)


DATABASE_URL = "postgresql://catalog_user:secret@example.invalid/catalog"


def test_accepts_existing_separate_roots(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    config = AppConfig.create(archive, derived, DATABASE_URL)

    assert config.archive_root == archive.resolve()
    assert config.derived_root == derived.resolve()
    assert config.front_topic == DEFAULT_FRONT_TOPIC
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
        AppConfig.create(archive, derived, DATABASE_URL)


def test_rejects_same_root_through_symlink_alias(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="must not overlap"):
        AppConfig.create(root, alias, DATABASE_URL)


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
        AppConfig.create(archive, derived, DATABASE_URL)


def test_rejects_non_postgresql_url_without_exposing_secret(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()

    with pytest.raises(ConfigurationError) as captured:
        AppConfig.create(archive, derived, "sqlite:///secret-value")

    assert "secret-value" not in str(captured.value)


def test_environment_requires_all_settings(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="ARCHIVE_ROOT"):
        AppConfig.from_environment({})


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
        AppConfig.create(archive, derived, DATABASE_URL, front_topic=topic)


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
            ffmpeg_path="/bin/true",
        )
