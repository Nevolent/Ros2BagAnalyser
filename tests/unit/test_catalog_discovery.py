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
    assert len(repository.applied) == 1, "Idle discovery must not acquire the catalog/queue write locks."


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


def test_new_complete_copy_waits_for_a_quiet_inventory_and_changes_reset_timer(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    archive.mkdir()
    recording = create_recording(archive, 'new')
    scanner = CatalogScanner(archive, settle_seconds=30)
    now = [0.0]
    monkeypatch.setattr('rosbag_analyser.catalog.scanner.time.monotonic', lambda: now[0])
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    now[0] = 29
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    (recording / 'still-copying.part').write_bytes(b'a')
    now[0] = 30
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    now[0] = 59
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    now[0] = 60
    assert len(scanner.scan(known_recordings=frozenset()).recordings) == 1


def test_new_source_changing_during_inspection_is_not_admitted(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    archive.mkdir()
    recording = create_recording(archive, 'new')
    scanner = CatalogScanner(archive, settle_seconds=30)
    now = [0.0]
    monkeypatch.setattr('rosbag_analyser.catalog.scanner.time.monotonic', lambda: now[0])
    scanner.scan(known_recordings=frozenset())
    original = scanner._scan_recording
    def changed(*args):
        result = original(*args)
        (recording / 'late-arrival.part').write_bytes(b'copy')
        return result
    monkeypatch.setattr(scanner, '_scan_recording', changed)
    now[0] = 30
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    monkeypatch.setattr(scanner, '_scan_recording', original)
    now[0] = 59
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    now[0] = 60
    assert len(scanner.scan(known_recordings=frozenset()).recordings) == 1


def test_live_sqlite_wal_prevents_admission_even_after_quiet_period(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    archive.mkdir()
    recording = create_recording(archive, 'new')
    (recording / 'new_0.db3-wal').write_bytes(b'live')
    scanner = CatalogScanner(archive, settle_seconds=30)
    now = [0.0]
    monkeypatch.setattr('rosbag_analyser.catalog.scanner.time.monotonic', lambda: now[0])
    scanner.scan(known_recordings=frozenset())
    now[0] = 60
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    (recording / 'new_0.db3-wal').unlink()
    assert scanner.scan(known_recordings=frozenset()).recordings == ()
    now[0] = 90
    assert len(scanner.scan(known_recordings=frozenset()).recordings) == 1


def test_full_scan_retains_known_recordings_while_deferring_new_copy(tmp_path):
    archive = tmp_path / 'archive'
    archive.mkdir()
    create_recording(archive, 'known')
    create_recording(archive, 'new')
    snapshot = CatalogScanner(archive, settle_seconds=30).scan(existing_paths=frozenset({'known'}))
    assert [item.display_name for item in snapshot.recordings] == ['known']


def test_slow_known_bag_does_not_delay_observing_new_copy(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "a-known")
    create_recording(archive, "b-new")
    scanner = CatalogScanner(archive, settle_seconds=30)
    now = [0.0]
    monkeypatch.setattr("rosbag_analyser.catalog.scanner.time.monotonic", lambda: now[0])
    inspect = scanner._scan_recording
    def slow_inspection(*args):
        now[0] += 30
        return inspect(*args)
    monkeypatch.setattr(scanner, "_scan_recording", slow_inspection)
    known = frozenset({"a-known"})
    assert [r.display_name for r in scanner.scan(existing_paths=known).recordings] == ["a-known"]
    monkeypatch.setattr(scanner, "_scan_recording", inspect)
    assert [r.display_name for r in scanner.scan(known_recordings=known).recordings] == ["b-new"]
