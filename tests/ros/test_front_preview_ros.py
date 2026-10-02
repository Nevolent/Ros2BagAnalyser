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


def test_real_ros_camera_bundle_publishes_each_stream_with_its_own_timing(tmp_path):
    from types import SimpleNamespace
    import os
    import shutil
    from rosbag_analyser.artifact_store import ArtifactStore
    from rosbag_analyser.worker import SerialWorker
    from conftest import inventory

    serialization = pytest.importorskip("rclpy.serialization")
    sensor_messages = pytest.importorskip("sensor_msgs.msg")
    source = tmp_path / "source"
    source.mkdir()
    database = source / "generated.db3"
    topics = (
        TopicFact("/anything/color", "sensor_msgs/msg/Image", "cdr", 3),
        TopicFact("/second/raw", "sensor_msgs/msg/Image", "cdr", 2),
    )
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT, type TEXT, serialization_format TEXT);"
            "CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER, timestamp INTEGER, data BLOB);"
            "CREATE INDEX timestamp_idx ON messages(timestamp);")
        for topic_id, topic in enumerate(topics, 1):
            connection.execute("INSERT INTO topics VALUES(?,?,?,?)",
                               (topic_id, topic.name, topic.message_type, topic.serialization_format))
            for frame in range(topic.message_count):
                message = sensor_messages.Image()
                message.width, message.height, message.step = 4, 2, 12
                message.encoding = "rgb8"
                message.data = bytes([20, frame, 200] * 8)
                connection.execute("INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)",
                                   (topic_id, 1_000_000_000 + topic_id * 100_000_000 + frame * 100_000_000,
                                    serialization.serialize_message(message)))
    identity = source_file_identity(database.stat())
    descriptor = FrontSourceDescriptor(
        recording_id=1, archive_relative_path="generated", metadata_path=source / "metadata.yaml",
        database_path=database, metadata_identity=identity, database_identity=identity,
        bag_start_ns=1_000_000_000, bag_duration_ns=500_000_000,
        topic=topics[0], topics=topics, cache_identity="a" * 64)
    before = inventory(source)
    derived = tmp_path / "derived"
    derived.mkdir()
    store = ArtifactStore(derived, Path(shutil.which("ffmpeg")), Path(shutil.which("ffprobe")))
    completed, failures = [], []
    repository = SimpleNamespace(
        complete_job=lambda *args: completed.append(args),
        fail_job=lambda *args: failures.append(args))
    resolver = SimpleNamespace(resolve=lambda _: SimpleNamespace(descriptor=descriptor))
    worker = SerialWorker(repository, resolver, FrontPreviewProcessor(V0_PREVIEW_PROFILE),
                          store, "", "test-encoder")
    worker._run_front_job(SimpleNamespace(id=1, recording_id=1, kind="front_preview", cache_identity="a" * 64))
    assert failures == []
    artifact = completed[0][1]
    assert [stream["timing"]["coverage_start_ns"] for stream in artifact.manifest["streams"]] == [
        "100000000", "200000000"]
    store.validate_media(artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity, artifact.manifest)
    for index, topic in enumerate(topics):
        opened = store.open_media(artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity,
                                  artifact.manifest, stream_index=index)
        try:
            with av.open(os.fdopen(os.dup(opened.descriptor), "rb")) as video:
                assert len(list(video.decode(video=0))) == topic.message_count
        finally:
            os.close(opened.descriptor)
    assert inventory(source) == before
