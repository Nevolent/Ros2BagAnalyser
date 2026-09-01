from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.front_header_diagnostic import (
    FrontHeaderDiagnosticError,
    HeaderStamp,
    inspect_front_headers,
)
from rosbag_analyser.front_preview import FrontSourceDescriptor


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT, type TEXT, "
            "serialization_format TEXT)"
        )
        connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, topic_id INTEGER, "
            "timestamp INTEGER, data BLOB)"
        )
        connection.execute(
            "INSERT INTO topics VALUES (1, '/front', 'sensor_msgs/msg/Image', 'cdr')"
        )
        for index in range(1, 5):
            connection.execute(
                "INSERT INTO messages VALUES (?, 1, ?, ?)",
                (index, index * 100, bytes([index])),
            )
        connection.commit()
    finally:
        connection.close()


def _descriptor(database: Path) -> FrontSourceDescriptor:
    identity = source_file_identity(database.stat())
    return FrontSourceDescriptor(
        recording_id=1,
        archive_relative_path="recording",
        metadata_path=database.parent / "metadata.yaml",
        database_path=database,
        metadata_identity=identity,
        database_identity=identity,
        bag_start_ns=0,
        bag_duration_ns=400,
        topic=TopicFact("/front", "sensor_msgs/msg/Image", "cdr", 4),
        cache_identity="a" * 64,
    )


def test_report_identifies_non_positive_headers_and_preserves_source(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _database(database)
    before = (database.stat().st_size, database.stat().st_mtime_ns)

    report = inspect_front_headers(
        _descriptor(database),
        decoder=lambda data: HeaderStamp(0, 0) if data == b"\x02" else HeaderStamp(10, data[0]),
    )

    assert report.message_count == 4
    assert report.invalid_header_count == 1
    assert report.first_invalid is not None
    assert report.first_invalid.message_index == 2
    assert report.first_invalid.message_id == 2
    assert report.first_invalid.record_timestamp_ns == 200
    assert report.first_invalid.reason == "non_positive"
    assert report.strictly_ordered is False
    assert (database.stat().st_size, database.stat().st_mtime_ns) == before
    assert not (tmp_path / "recording.db3-journal").exists()
    assert not (tmp_path / "recording.db3-wal").exists()
    assert not (tmp_path / "recording.db3-shm").exists()


def test_report_identifies_out_of_order_valid_headers(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _database(database)

    report = inspect_front_headers(
        _descriptor(database),
        decoder=lambda data: HeaderStamp(10, {1: 100, 2: 200, 3: 150, 4: 300}[data[0]]),
    )

    assert report.invalid_header_count == 0
    assert report.out_of_order_header_count == 1
    assert report.first_out_of_order is not None
    assert report.first_out_of_order.message_index == 3
    assert report.first_out_of_order.header_timestamp_ns == 10_000_000_150
    assert report.strictly_ordered is False


def test_message_limit_fails_instead_of_returning_an_incomplete_report(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _database(database)

    with pytest.raises(FrontHeaderDiagnosticError) as captured:
        inspect_front_headers(
            _descriptor(database), max_messages=2, decoder=lambda _: HeaderStamp(1, 0)
        )

    assert captured.value.code == "front_header_diagnostic_limit_exceeded"
