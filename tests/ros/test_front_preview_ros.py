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
from rosbag_analyser.topic_selection import usable_topics


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
        (
            "rgba8",
            ((10, 0), (10, 100_000_000), (10, 200_000_000)),
            (0.0, 0.125, 0.25),
            FRONT_HEADER_TIMING_POLICY,
        ),
        (
            "bgra8",
            ((0, 0), (0, 0), (0, 0)),
            (0.0, 0.05, 0.25),
            FRONT_ALL_ZERO_HEADER_TIMING_POLICY,
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
            channels = 4 if encoding in {"rgba8", "bgra8"} else 3
            message.step = 4 * channels
            pixel = [index, 20, 200] + ([127] if channels == 4 else [])
            message.data = bytes(pixel * 8)
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


@pytest.mark.parametrize("front_name", ["/robot/camera_front/raw", "/alternative/image"])
def test_ros_colour_bundle_excludes_ouster_images_and_selects_default(tmp_path, front_name):
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
        TopicFact(front_name, "sensor_msgs/msg/Image", "cdr", 2),
        TopicFact("/side/rgba", "sensor_msgs/msg/Image", "cdr", 2),
        TopicFact("/rear/bgra", "sensor_msgs/msg/Image", "cdr", 2),
        TopicFact("/ouster/range_image", "sensor_msgs/msg/Image", "cdr", 4),
        TopicFact("/ouster/nearir_image", "sensor_msgs/msg/Image", "cdr", 5),
    )
    encodings = ("rgb8", "bgr8", "rgba8", "bgra8", "mono16", "mono8")
    with sqlite3.connect(database) as connection:
        connection.executescript(
            "CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT, type TEXT, serialization_format TEXT);"
            "CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER, timestamp INTEGER, data BLOB);"
            "CREATE INDEX timestamp_idx ON messages(timestamp);")
        for topic_id, (topic, encoding) in enumerate(zip(topics, encodings), 1):
            connection.execute("INSERT INTO topics VALUES(?,?,?,?)",
                               (topic_id, topic.name, topic.message_type, topic.serialization_format))
            for frame in range(topic.message_count):
                message = sensor_messages.Image()
                channels = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4,
                            "mono8": 1, "mono16": 2}[encoding]
                message.width, message.height, message.step = 4, 2, 4 * channels + 2
                message.encoding = encoding
                message.data = bytes([20] * (message.step * message.height))
                if encoding.startswith("mono"):
                    # Excluded LiDAR image timing must never become a camera failure.
                    message.header.stamp.sec = -1
                connection.execute("INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)",
                                   (topic_id, 1_000_000_000 + topic_id * 100_000_000 + frame * 100_000_000,
                                    serialization.serialize_message(message)))
    identity = source_file_identity(database.stat())
    descriptor = FrontSourceDescriptor(
        recording_id=1, archive_relative_path="generated", metadata_path=source / "metadata.yaml",
        database_path=database, metadata_identity=identity, database_identity=identity,
        bag_start_ns=1_000_000_000, bag_duration_ns=500_000_000,
        topic=usable_topics(topics, "sensor_msgs/msg/Image")[0],
        topics=usable_topics(topics, "sensor_msgs/msg/Image"), cache_identity="a" * 64)
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
    expected_topics = [topics[1], topics[0], topics[3], topics[2]] if "front" in front_name else [
        topics[0], topics[1], topics[3], topics[2]]
    assert artifact.manifest["source"]["topic"] == expected_topics[0].name
    assert [stream["topic"] for stream in artifact.manifest["streams"]] == [
        topic.name for topic in expected_topics]
    assert artifact.manifest.get("skipped_streams", []) == []
    assert [stream["timing"]["coverage_start_ns"] for stream in artifact.manifest["streams"]] == [
        str((topics.index(topic) + 1) * 100_000_000) for topic in expected_topics]
    store.validate_media(artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity, artifact.manifest)
    for index, topic in enumerate(expected_topics):
        opened = store.open_media(artifact.output_relative_path, artifact.size_bytes, artifact.cache_identity,
                                  artifact.manifest, stream_index=index)
        try:
            with av.open(os.fdopen(os.dup(opened.descriptor), "rb")) as video:
                assert len(list(video.decode(video=0))) == topic.message_count
        finally:
            os.close(opened.descriptor)
    assert inventory(source) == before
