from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from conftest import create_rosbag_database, inventory
from rosbag_analyser.catalog import sqlite_health
from rosbag_analyser.catalog.sqlite_health import probe_sqlite_database
from rosbag_analyser.catalog.types import SourceCondition


def test_reads_valid_database_without_sidecars(tmp_path: Path) -> None:
    database = tmp_path / "valid.db3"
    create_rosbag_database(database)
    before = inventory(tmp_path)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.READABLE
    assert result.diagnostic is None
    assert inventory(tmp_path) == before


def test_probe_enforces_stable_readonly_connection_and_instruction_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "valid.db3"
    create_rosbag_database(database)
    original_connect = sqlite3.connect
    captured: dict[str, object] = {}
    statements: list[str] = []

    class ConnectionProxy:
        def __init__(self, connection: sqlite3.Connection) -> None:
            self.connection = connection

        def execute(self, statement: str):
            statements.append(statement)
            return self.connection.execute(statement)

        def set_progress_handler(self, handler, interval: int) -> None:
            captured["progress_handler"] = handler
            captured["progress_interval"] = interval
            self.connection.set_progress_handler(handler, interval)

        def close(self) -> None:
            self.connection.close()

    def recording_connect(database_uri: str, **options: object) -> ConnectionProxy:
        captured["database_uri"] = database_uri
        captured["options"] = options
        return ConnectionProxy(original_connect(database_uri, **options))

    monkeypatch.setattr(sqlite_health.sqlite3, "connect", recording_connect)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.READABLE
    assert str(captured["database_uri"]).startswith("file:///proc/self/fd/")
    assert str(captured["database_uri"]).endswith("?mode=ro&immutable=1")
    assert captured["options"] == {
        "uri": True,
        "timeout": 0.0,
        "isolation_level": None,
    }
    assert statements[0] == "PRAGMA query_only = ON"
    assert captured["progress_interval"] == sqlite_health.SQLITE_PROGRESS_INTERVAL
    progress_handler = captured["progress_handler"]
    outcomes = [
        progress_handler()  # type: ignore[operator]
        for _ in range(
            sqlite_health.SQLITE_VM_INSTRUCTION_BUDGET
            // sqlite_health.SQLITE_PROGRESS_INTERVAL
            + 2
        )
    ]
    assert 1 in outcomes


def test_path_swap_cannot_redirect_schema_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recording = tmp_path / "recording"
    recording.mkdir()
    database = recording / "source.db3"
    create_rosbag_database(database)
    outside_database = tmp_path / "outside.db3"
    create_rosbag_database(outside_database, include_ros_tables=False)
    original_connect = sqlite3.connect
    captured_uri: list[str] = []

    def swap_then_connect(database_uri: str, **options: object):
        captured_uri.append(database_uri)
        database.unlink()
        database.symlink_to(outside_database)
        return original_connect(database_uri, **options)

    monkeypatch.setattr(sqlite_health.sqlite3, "connect", swap_then_connect)

    result = probe_sqlite_database(database)

    assert captured_uri[0].startswith("file:///proc/self/fd/")
    assert result.condition is SourceCondition.UNINSPECTABLE
    assert result.diagnostic is not None
    assert result.diagnostic.code == "sqlite_changed_during_scan"


def test_detects_header_file_size_truncation(tmp_path: Path) -> None:
    database = tmp_path / "truncated.db3"
    create_rosbag_database(database)
    data = database.read_bytes()
    database.write_bytes(data[:-4_096])

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.DAMAGED
    assert result.diagnostic.code == "sqlite_size_mismatch"


def test_rejects_non_sqlite_header(tmp_path: Path) -> None:
    database = tmp_path / "invalid.db3"
    database.write_bytes(b"not sqlite" + b"\0" * 200)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.INVALID
    assert result.diagnostic.code == "sqlite_header_invalid"


def test_rejects_sqlite_without_ros_schema(tmp_path: Path) -> None:
    database = tmp_path / "other.db3"
    create_rosbag_database(database, include_ros_tables=False)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.INVALID
    assert result.diagnostic.code == "sqlite_ros_schema_missing"


def test_rejects_ros_table_names_with_wrong_columns(tmp_path: Path) -> None:
    database = tmp_path / "wrong-columns.db3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE topics (x INTEGER)")
        connection.execute("CREATE TABLE messages (y INTEGER)")
        connection.commit()
    finally:
        connection.close()

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.INVALID
    assert result.diagnostic.code == "sqlite_ros_schema_invalid"


def test_reports_malformed_schema_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "malformed.db3"
    create_rosbag_database(database)

    class MalformedConnection:
        def execute(self, statement: str):
            if statement == "PRAGMA query_only = ON":
                return None
            raise sqlite3.DatabaseError("database disk image is malformed")

        def set_progress_handler(self, handler, interval: int) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        sqlite_health.sqlite3,
        "connect",
        lambda database_uri, **options: MalformedConnection(),
    )

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.DAMAGED
    assert result.diagnostic is not None
    assert result.diagnostic.code == "sqlite_malformed"


def test_ignores_non_authoritative_header_page_count(tmp_path: Path) -> None:
    database = tmp_path / "stale-page-count.db3"
    create_rosbag_database(database)
    header = bytearray(database.read_bytes())
    page_count = int.from_bytes(header[28:32], "big")
    change_counter = int.from_bytes(header[24:28], "big")
    header[28:32] = (page_count + 1).to_bytes(4, "big")
    header[92:96] = (change_counter ^ 1).to_bytes(4, "big")
    database.write_bytes(header)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.READABLE
    assert result.diagnostic is None


def test_zero_header_page_count_is_non_authoritative(tmp_path: Path) -> None:
    database = tmp_path / "legacy-page-count.db3"
    create_rosbag_database(database)
    contents = bytearray(database.read_bytes())
    contents[24:32] = bytes(8)
    contents[92:96] = bytes(4)
    database.write_bytes(contents)

    result = probe_sqlite_database(database)

    assert result.condition is SourceCondition.READABLE
    assert result.diagnostic is None
