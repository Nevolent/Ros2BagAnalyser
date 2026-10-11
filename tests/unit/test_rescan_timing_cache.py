import json
import os
import sqlite3

import pytest
import yaml

from conftest import create_recording, create_rosbag_database, inventory
from rosbag_analyser.catalog import sqlite_health, timing
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.sqlite_health import probe_sqlite_database
from rosbag_analyser.catalog.types import SourceCondition


def saved_cache(snapshot):
    return {component.relative_path: json.loads(json.dumps(recording.scan_details['timing_cache']))
            for recording in snapshot.recordings for component in recording.components
            if component.role.value == 'ros_database' and recording.scan_details}


def test_full_scan_reuses_saved_timing_but_reconciles_sources(tmp_path, monkeypatch):
    archive = tmp_path / 'archive'
    archive.mkdir()
    unchanged = create_recording(archive, 'unchanged')
    moved = create_recording(archive, 'moved')
    missing = create_recording(archive, 'missing')
    first = CatalogScanner(archive).scan()
    cache = saved_cache(first)
    moved.rename(archive / 'relocated')
    missing.rename(tmp_path / 'gone')
    create_recording(archive, 'new')
    # A metadata and companion change must still be discovered with cached DB timing.
    metadata_path = unchanged / 'metadata.yaml'
    document = yaml.safe_load(metadata_path.read_text())
    document['rosbag2_bagfile_information']['message_count'] = 99
    metadata_path.write_text(yaml.safe_dump(document))
    (unchanged / 'unchanged.csv').unlink()
    before = inventory(archive)
    calls = 0
    original = sqlite_health.inspect_timing
    def inspect(connection):
        nonlocal calls
        calls += 1
        return original(connection)
    monkeypatch.setattr(sqlite_health, 'inspect_timing', inspect)
    second = CatalogScanner(archive).scan(timing_cache=cache)
    assert calls == 1  # A rename preserves the physical DB identity; only the new bag is inspected.
    rows = {item.display_name: item for item in second.recordings}
    assert set(rows) == {'unchanged', 'relocated', 'new'}
    assert rows['unchanged'].message_count == 99
    assert rows['unchanged'].components[-1].condition is SourceCondition.MISSING
    assert inventory(archive) == before


@pytest.mark.parametrize('change', ['database', 'replace', 'policy', 'header', 'invalid_cache'])
def test_timing_cache_invalidates_changes_even_when_size_and_mtime_match(tmp_path, monkeypatch, change):
    database = tmp_path / 'source.db3'
    create_rosbag_database(database)
    first = probe_sqlite_database(database)
    facts = database.stat()
    if change == 'database':
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA user_version = 2')
        os.utime(database, ns=(facts.st_atime_ns, facts.st_mtime_ns))
        assert database.stat().st_size == facts.st_size
    elif change == 'replace':
        replacement = tmp_path / 'replacement.db3'
        create_rosbag_database(replacement)
        os.utime(replacement, ns=(facts.st_atime_ns, facts.st_mtime_ns))
        replacement.replace(database)
    elif change == 'policy':
        monkeypatch.setattr(timing, 'TIMING_POLICY_VERSION', timing.TIMING_POLICY_VERSION + 1)
    elif change == 'header':
        # Isolate the header check from file facts using a stale cache signature.
        first.timing_cache['key']['header'] = '0' * 64
    else:
        first.timing_cache['timing'].pop('origin_ns')
    calls = 0
    original = sqlite_health.inspect_timing
    def inspect(connection):
        nonlocal calls
        calls += 1
        return original(connection)
    monkeypatch.setattr(sqlite_health, 'inspect_timing', inspect)
    second = probe_sqlite_database(database, timing_cache=first.timing_cache)
    assert second.condition is SourceCondition.READABLE
    assert calls == 1


def test_cached_timing_is_raw_and_does_not_accumulate_metadata_offsets(tmp_path, monkeypatch):
    recording = create_recording(tmp_path, 'run')
    origin = 1_700_000_000_000_000_000
    with sqlite3.connect(recording / 'run_0.db3') as connection:
        connection.executemany('INSERT INTO messages VALUES (?, 1, ?, ?)',
                               [(i + 1, origin + i * 100_000_000, b'') for i in range(30)] +
                               [(31, origin + 20_000_000_000, b'')])
    first = CatalogScanner(tmp_path).scan()
    cache = saved_cache(first)
    monkeypatch.setattr(sqlite_health, 'inspect_timing', lambda _: pytest.fail('Repeated timing query'))
    metadata_path = recording / 'metadata.yaml'
    document = yaml.safe_load(metadata_path.read_text())
    document['rosbag2_bagfile_information']['starting_time']['nanoseconds_since_epoch'] -= 1_000_000_000
    metadata_path.write_text(yaml.safe_dump(document))
    second = CatalogScanner(tmp_path).scan(timing_cache=cache)
    third = CatalogScanner(tmp_path).scan(timing_cache=saved_cache(second))
    assert second.recordings[0].scan_details['timing']['gaps'][0]['start_ns'] == '3900000000'
    assert third.recordings == second.recordings
    assert cache == saved_cache(second)


def test_cached_probe_still_verifies_schema_and_changes_during_read(tmp_path, monkeypatch):
    database = tmp_path / 'source.db3'
    create_rosbag_database(database)
    first = probe_sqlite_database(database)
    original = sqlite_health._probe_open_database
    def changing_probe(*args):
        result = original(*args)
        with sqlite3.connect(database) as connection:
            connection.execute('PRAGMA user_version = 3')
        return result
    monkeypatch.setattr(sqlite_health, '_probe_open_database', changing_probe)
    second = probe_sqlite_database(database, timing_cache=first.timing_cache)
    assert second.condition is SourceCondition.UNINSPECTABLE
    assert second.diagnostic.code == 'sqlite_changed_during_scan'
    assert second.timing_cache is None
