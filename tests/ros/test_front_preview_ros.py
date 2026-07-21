from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import FrontSourceDescriptor
from rosbag_analyser.processors.front_preview import FrontPreviewProcessor


pytestmark = pytest.mark.ros


def test_generated_ros_images_deserialize_and_encode_with_record_time(
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
            "INSERT INTO topics VALUES (1, '/camera/image_raw', "
            "'sensor_msgs/msg/Image', 'cdr', '')"
        )
        for index, timestamp in enumerate((1_000_000_000, 1_250_000_000), start=1):
            message = sensor_messages.Image()
            message.width = 4
            message.height = 2
            message.encoding = "bgr8"
            message.step = 12
            message.data = bytes([index, 20, 200] * 8)
            connection.execute(
                "INSERT INTO messages VALUES (?, 1, ?, ?)",
                (index, timestamp, serialization.serialize_message(message)),
            )
        connection.commit()
    finally:
        connection.close()
    details = database.stat()
    identity = source_file_identity(details)
    descriptor = FrontSourceDescriptor(
        recording_id=1,
        archive_relative_path="generated",
        metadata_path=tmp_path / "metadata.yaml",
        database_path=database,
        metadata_identity=identity,
        database_identity=identity,
        bag_start_ns=900_000_000,
        bag_duration_ns=500_000_000,
        topic=TopicFact(
            name="/camera/image_raw",
            message_type="sensor_msgs/msg/Image",
            serialization_format="cdr",
            message_count=2,
        ),
        cache_identity="a" * 64,
    )

    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE).process(
        descriptor, tmp_path / "preview.mp4"
    )

    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 350_000_000
    assert result.encoded_frame_count == 2
