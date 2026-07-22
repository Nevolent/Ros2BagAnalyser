from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.imu_series import ImuSourceDescriptor
from rosbag_analyser.processors.imu_series import ImuSeriesProcessor


pytestmark = pytest.mark.ros


def test_generated_imu_messages_use_record_time_and_angular_velocity_z(
    tmp_path: Path,
) -> None:
    serialization = pytest.importorskip("rclpy.serialization")
    sensor_messages = pytest.importorskip("sensor_msgs.msg")
    database = tmp_path / "generated.db3"
    connection = sqlite3.connect(database)
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
            "INSERT INTO topics VALUES (1, '/sensors/imu', "
            "'sensor_msgs/msg/Imu', 'cdr', '')"
        )
        values = (1.25, float("nan"), -2.5)
        record_times = (1_100_000_000, 1_250_000_000, 1_400_000_000)
        for index, (record_time, value) in enumerate(
            zip(record_times, values, strict=True), start=1
        ):
            message = sensor_messages.Imu()
            message.header.stamp.sec = 99 + index
            message.angular_velocity.x = 50.0 + index
            message.angular_velocity.y = 60.0 + index
            message.angular_velocity.z = value
            connection.execute(
                "INSERT INTO messages VALUES (?, 1, ?, ?)",
                (index, record_time, serialization.serialize_message(message)),
            )
        connection.commit()
    finally:
        connection.close()

    identity = source_file_identity(database.stat())
    descriptor = ImuSourceDescriptor(
        recording_id=1,
        archive_relative_path="generated",
        metadata_path=tmp_path / "metadata.yaml",
        database_path=database,
        metadata_identity=identity,
        database_identity=identity,
        bag_start_ns=1_000_000_000,
        bag_duration_ns=500_000_000,
        topic=TopicFact(
            name="/sensors/imu",
            message_type="sensor_msgs/msg/Imu",
            serialization_format="cdr",
            message_count=3,
        ),
        component="angular_velocity.z",
        cache_identity="a" * 64,
    )

    result = ImuSeriesProcessor().process(descriptor, tmp_path / "series.json")

    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 400_000_000
    assert result.finite_count == 2
    assert result.non_finite_count == 1
    assert json.loads((tmp_path / "series.json").read_text())["samples"] == [
        ["100000000", 1.25],
        ["250000000", None],
        ["400000000", -2.5],
    ]
