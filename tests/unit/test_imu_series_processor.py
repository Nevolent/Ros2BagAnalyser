from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3

import pytest

from conftest import inventory
from rosbag_analyser.processors import imu_series as imu_processor_module
from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.imu_series import ImuSourceDescriptor
from rosbag_analyser.processors.imu_series import (
    MAX_SERIALIZED_IMU_BYTES,
    ImuSeriesProcessingError,
    ImuSeriesProcessor,
)


def _create_imu_database(
    path: Path,
    timestamps: list[int],
    *,
    message_type: str = "sensor_msgs/msg/Imu",
    payloads: list[bytes] | None = None,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT, type TEXT, "
            "serialization_format TEXT, offered_qos_profiles TEXT)"
        )
        connection.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, topic_id INTEGER, "
            "timestamp INTEGER, data BLOB)"
        )
        connection.execute(
            "INSERT INTO topics VALUES (1, '/sensors/imu', ?, 'cdr', '')",
            (message_type,),
        )
        values = payloads or [bytes([index]) for index in range(1, len(timestamps) + 1)]
        for index, (timestamp, payload) in enumerate(
            zip(timestamps, values, strict=True), start=1
        ):
            connection.execute(
                "INSERT INTO messages VALUES (?, 1, ?, ?)",
                (index, timestamp, payload),
            )
        connection.commit()
    finally:
        connection.close()


def _descriptor(database: Path, bag_start_ns: int, count: int) -> ImuSourceDescriptor:
    identity = source_file_identity(database.stat())
    return ImuSourceDescriptor(
        recording_id=1,
        archive_relative_path="run",
        metadata_path=database.parent / "metadata.yaml",
        database_path=database,
        metadata_identity=identity,
        database_identity=identity,
        bag_start_ns=bag_start_ns,
        bag_duration_ns=500,
        topic=TopicFact(
            name="/sensors/imu",
            message_type="sensor_msgs/msg/Imu",
            serialization_format="cdr",
            message_count=count,
        ),
        component="angular_velocity.z",
        cache_identity="a" * 64,
    )


def _all_components(value: float) -> tuple[float, ...]:
    return (value, value, value, value, value, value)


def test_extracts_record_time_values_nulls_and_duplicates_without_source_writes(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    database = archive / "recording.db3"
    _create_imu_database(database, [1_100, 1_100, 1_300])
    before = inventory(archive)
    decoded = {1: 1.25, 2: math.nan, 3: -2.0}

    result = ImuSeriesProcessor(
        lambda payload: _all_components(decoded[payload[0]])
    ).process(
        _descriptor(database, 1_000, 3), derived / "series.json"
    )

    assert result.sample_count == 3
    assert result.duplicate_timestamp_count == 1
    assert result.coverage_start_ns == 100
    assert result.coverage_end_ns == 300
    assert len(result.series) == 6
    assert all(series.finite_count == 2 for series in result.series)
    assert all(series.non_finite_count == 1 for series in result.series)
    assert all(series.minimum_value == -2.0 for series in result.series)
    assert all(series.maximum_value == 1.25 for series in result.series)
    assert result.warnings == (
        "coverage_starts_after_recording",
        "coverage_ends_before_recording",
        "non_finite_values_present",
    )
    assert json.loads((derived / "series.json").read_text()) == {
        "schema_version": 2,
        "samples": [
            ["100", 1.25, 1.25, 1.25, 1.25, 1.25, 1.25],
            ["100", None, None, None, None, None, None],
            ["300", -2.0, -2.0, -2.0, -2.0, -2.0, -2.0],
        ],
    }
    assert inventory(archive) == before
    assert not (archive / "recording.db3-journal").exists()
    assert not (archive / "recording.db3-wal").exists()
    assert not (archive / "recording.db3-shm").exists()


def test_coverage_can_extend_beyond_declared_recording(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [900, 1_700])

    result = ImuSeriesProcessor(
        lambda payload: _all_components(float(payload[0]))
    ).process(
        _descriptor(database, 1_000, 2), tmp_path / "series.json"
    )

    assert result.coverage_start_ns == -100
    assert result.coverage_end_ns == 700
    assert result.warnings == (
        "coverage_starts_before_recording",
        "coverage_ends_after_recording",
    )


def test_all_non_finite_values_fail_instead_of_publishing_empty_graph(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [1_000])

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(lambda payload: _all_components(math.inf)).process(
            _descriptor(database, 1_000, 1), tmp_path / "series.json"
        )

    assert captured.value.code == "imu_values_unavailable"


def test_wrong_database_topic_contract_fails_safely(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [1_000], message_type="geometry_msgs/msg/Twist")

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(lambda payload: 1.0).process(
            _descriptor(database, 1_000, 1), tmp_path / "series.json"
        )

    assert captured.value.code == "imu_topic_contract_changed"


def test_unsupported_component_fails_before_database_read(tmp_path: Path) -> None:
    missing_database = tmp_path / "missing.db3"
    missing_database.write_bytes(b"not a SQLite database")
    descriptor = _descriptor(missing_database, 1_000, 1)

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(lambda payload: _all_components(1.0)).process(
            ImuSourceDescriptor(
                **{**descriptor.__dict__, "component": "orientation.x"}
            ),
            tmp_path / "series.json",
        )

    assert captured.value.code == "imu_component_unsupported"


def test_oversized_serialized_message_is_rejected_before_decoder(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(
        database,
        [1_000],
        payloads=[b"x" * (MAX_SERIALIZED_IMU_BYTES + 1)],
    )
    decoder_called = False

    def decoder(payload: bytes) -> tuple[float, ...]:
        nonlocal decoder_called
        decoder_called = True
        return _all_components(1.0)

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(decoder).process(
            _descriptor(database, 1_000, 1), tmp_path / "series.json"
        )

    assert captured.value.code == "imu_serialized_payload_invalid"
    assert not decoder_called


def test_derived_series_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [1_000, 1_100])
    monkeypatch.setattr(imu_processor_module, "MAX_SERIES_BYTES", 40)

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(lambda payload: _all_components(123.456)).process(
            _descriptor(database, 1_000, 2), tmp_path / "series.json"
        )

    assert captured.value.code == "imu_series_too_large"


def test_decoder_failure_is_sanitized(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [1_000])

    def decoder(payload: bytes) -> tuple[float, ...]:
        del payload
        raise ValueError("private decoder detail")

    with pytest.raises(ImuSeriesProcessingError) as captured:
        ImuSeriesProcessor(decoder).process(
            _descriptor(database, 1_000, 1), tmp_path / "series.json"
        )

    assert captured.value.code == "imu_deserialization_failed"
    assert "private" not in captured.value.safe_message


def test_one_all_null_component_does_not_hide_other_series(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_imu_database(database, [1_000, 1_100])

    result = ImuSeriesProcessor(
        lambda payload: (
            math.nan,
            float(payload[0]),
            float(payload[0]),
            float(payload[0]),
            float(payload[0]),
            float(payload[0]),
        )
    ).process(_descriptor(database, 1_000, 2), tmp_path / "series.json")

    unavailable, available = result.series[0], result.series[1]
    assert unavailable.finite_count == 0
    assert unavailable.non_finite_count == 2
    assert unavailable.minimum_value is None
    assert unavailable.maximum_value is None
    assert available.finite_count == 2
