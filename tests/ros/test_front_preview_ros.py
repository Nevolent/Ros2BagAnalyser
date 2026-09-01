from __future__ import annotations

from pathlib import Path
import sqlite3

import av
import pytest

from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import (
    FRONT_ALL_ZERO_HEADER_TIMING_POLICY,
    FRONT_HEADER_TIMING_POLICY,
    FrontSourceDescriptor,
)
from rosbag_analyser.processors.front_preview import FrontPreviewProcessor


pytestmark = pytest.mark.ros


@pytest.mark.parametrize(
    ("encoding", "header_stamps", "expected_times", "expected_policy"),
    [
        (
            "bgr8",
            ((10, 0), (10, 100_000_000), (10, 200_000_000)),
            (0.0, 0.125, 0.25),
            FRONT_HEADER_TIMING_POLICY,
        ),
        (
            "bgr8",
            ((0, 0), (0, 0), (0, 0)),
            (0.0, 0.05, 0.25),
            FRONT_ALL_ZERO_HEADER_TIMING_POLICY,
        ),
        (
            "rgb8",
            ((10, 0), (10, 100_000_000), (10, 200_000_000)),
            (0.0, 0.125, 0.25),
            FRONT_HEADER_TIMING_POLICY,
        ),
    ],
)
def test_generated_ros_images_select_the_exact_v3_timing_mode(
    tmp_path: Path,
    encoding: str,
    header_stamps: tuple[tuple[int, int], ...],
    expected_times: tuple[float, ...],
    expected_policy: str,
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
        for index, (timestamp, header_stamp) in enumerate(
            zip(
                (1_000_000_000, 1_050_000_000, 1_250_000_000),
                header_stamps,
                strict=True,
            ),
            start=1,
        ):
            message = sensor_messages.Image()
            message.header.stamp.sec = header_stamp[0]
            message.header.stamp.nanosec = header_stamp[1]
            message.width = 4
            message.height = 2
            message.encoding = encoding
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
            message_count=3,
        ),
        cache_identity="a" * 64,
    )

    output = tmp_path / "preview.mp4"
    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE).process(descriptor, output)

    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 350_000_000
    assert result.encoded_frame_count == 3
    assert result.header_span_ns == (
        0 if expected_policy == FRONT_ALL_ZERO_HEADER_TIMING_POLICY else 200_000_000
    )
    assert result.timing_policy == expected_policy
    with av.open(output) as container:
        times = [
            float(frame.pts * frame.time_base)
            for frame in container.decode(video=0)
        ]
    assert times == pytest.approx(expected_times, abs=0.000_002)
