from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from conftest import create_recording, inventory
from rosbag_analyser.catalog import paths
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.catalog.types import RootScanError, SafeDiagnostic


def test_discovery_skips_known_contents_and_leaves_sources_unchanged(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    known = create_recording(archive, "known")
    create_recording(archive, "new")
    before = inventory(archive)
    scandir = paths.os.scandir

    def guarded_scandir(directory):
        assert Path(directory) != known, "Known recording contents must not be enumerated."
        return scandir(directory)

    monkeypatch.setattr(paths.os, "scandir", guarded_scandir)
    snapshot = CatalogScanner(archive).scan(known_recordings=frozenset({"known"}))
    assert [item.archive_relative_path for item in snapshot.recordings] == ["new"]
    monkeypatch.setattr(paths.os, "scandir", scandir)
    assert inventory(archive) == before


def test_discovery_defers_incomplete_copies_and_retries_them(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    new = create_recording(archive, "new")
    database = new / "new_0.db3"
    complete_database = database.read_bytes()
    database.write_bytes(complete_database[:100])
    scanner = CatalogScanner(archive)
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    # Only a synthetic fixture is changed; automatic discovery never writes.
    database.write_bytes(complete_database)
    assert [item.display_name for item in scanner.scan(known_recordings=frozenset()).recordings] == ["new"]
    assert len(scanner.scan().recordings) == 1


def test_discovery_never_follows_new_source_symlinks(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    outside = create_recording(tmp_path, "outside")
    (archive / "linked").symlink_to(outside, target_is_directory=True)
    assert CatalogScanner(archive).scan(known_recordings=frozenset()).recordings == ()


class DiscoveryRepository:
    def __init__(self):
        self.known = frozenset({"known"})
        self.applied = []

    def source_scan(self, *, full):
        return nullcontext()

    def known_recording_paths(self):
        return self.known

    def apply_discovery(self, snapshot):
        self.applied.append(snapshot)
        self.known |= frozenset(item.archive_relative_path for item in snapshot.recordings)
        return SimpleNamespace(recording_count=len(snapshot.recordings))


def test_discovery_is_additions_only_and_idempotent(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "known")
    create_recording(archive, "new")
    repository = DiscoveryRepository()
    service = CatalogService(CatalogScanner(archive), repository)
    assert service.discover_new() == 1
    assert service.discover_new() == 0
    assert [item.display_name for item in repository.applied[0].recordings] == ["new"]


def test_discovery_preserves_saved_state_when_source_disappears(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "new")
    repository = DiscoveryRepository()
    checks = iter([None, SafeDiagnostic("source_mount_unavailable", "Source unavailable.")])
    service = CatalogService(CatalogScanner(archive), repository, source_admission_check=lambda: next(checks))
    with pytest.raises(RootScanError, match="Source unavailable"):
        service.discover_new()
    assert repository.applied == []


def test_discovery_does_not_overlap_a_full_rescan(tmp_path):
    service = CatalogService(CatalogScanner(tmp_path), DiscoveryRepository())
    assert service._rescan_lock.acquire(blocking=False)
    try:
        assert service.discover_new() == 0
        assert service.repository.applied == []
    finally:
        service._rescan_lock.release()
