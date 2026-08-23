from __future__ import annotations

import os
from pathlib import Path

import pytest

from rosbag_analyser.catalog import paths as catalog_paths
from rosbag_analyser.catalog.paths import (
    CatalogScanLimits,
    UnsafeSourcePath,
    archive_relative_path,
    discover_recording_directories,
    filesystem_text_from_safe,
    inventory_direct_entries,
    resolve_declared_source,
    safe_filesystem_text,
)
from rosbag_analyser.catalog.types import RootScanError


class _ScandirEntryStub:
    def __init__(self, number: int) -> None:
        self.name = f"entry-{number}"
        self.path = f"/fixture/{self.name}"

    def is_dir(self, *, follow_symlinks: bool) -> bool:
        return False


class _ScandirPastLimit:
    def __enter__(self) -> "_ScandirPastLimit":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        yield _ScandirEntryStub(1)
        yield _ScandirEntryStub(2)
        yield _ScandirEntryStub(3)
        raise AssertionError("Enumeration continued past limit + 1")


def test_discovers_recording_candidate_and_does_not_follow_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording = archive / "recording"
    recording.mkdir()
    (recording / "metadata.yaml").write_text("invalid but a candidate", encoding="utf-8")
    (recording / "nested").mkdir()
    (archive / "file.txt").write_text("not a recording", encoding="utf-8")
    (archive / "linked").symlink_to(recording, target_is_directory=True)

    discovered = discover_recording_directories(archive)

    assert tuple(item.path for item in discovered) == (recording,)


@pytest.mark.parametrize(
    "declared",
    ["../outside.db3", "/absolute.db3", "folder\\database.db3", "./database.db3"],
)
def test_rejects_unsafe_declared_paths(tmp_path: Path, declared: str) -> None:
    archive = tmp_path / "archive"
    recording = archive / "recording"
    recording.mkdir(parents=True)

    with pytest.raises(UnsafeSourcePath):
        resolve_declared_source(archive, recording, declared)


def test_rejects_source_symlink(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    recording = archive / "recording"
    recording.mkdir(parents=True)
    target = archive / "target.db3"
    target.write_bytes(b"not relevant")
    (recording / "linked.db3").symlink_to(target)

    with pytest.raises(UnsafeSourcePath, match="symlink"):
        resolve_declared_source(archive, recording, "linked.db3")


def test_archive_entry_limit_stops_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    monkeypatch.setattr(catalog_paths.os, "scandir", lambda path: _ScandirPastLimit())

    with pytest.raises(RootScanError) as captured:
        discover_recording_directories(archive, CatalogScanLimits(max_entries=2))

    assert captured.value.diagnostic.code == "archive_entry_limit_exceeded"


def test_recording_entry_limit_stops_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = tmp_path / "recording"
    recording.mkdir()
    monkeypatch.setattr(catalog_paths.os, "scandir", lambda path: _ScandirPastLimit())

    with pytest.raises(UnsafeSourcePath) as captured:
        inventory_direct_entries(recording, max_entries=2)

    assert captured.value.code == "recording_entry_limit_exceeded"


def test_archive_relative_path_escapes_percent_and_non_utf8_without_collision(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    raw_name = os.fsdecode(b"bad_\xff")

    assert archive_relative_path(archive, archive / raw_name) == "bad_%FF"
    assert archive_relative_path(archive, archive / "bad_%FF") == "bad_%25FF"


def test_safe_filesystem_text_round_trips_percent_and_non_utf8() -> None:
    raw_name = os.fsdecode(b"literal_%_and_\xff")

    assert filesystem_text_from_safe(safe_filesystem_text(raw_name)) == raw_name


@pytest.mark.parametrize("value", ["bad_%", "bad_%7F", "bad_%u0041"])
def test_invalid_stored_filesystem_escaping_is_rejected(value: str) -> None:
    with pytest.raises(UnsafeSourcePath) as captured:
        filesystem_text_from_safe(value)

    assert captured.value.code == "stored_source_path_invalid"
