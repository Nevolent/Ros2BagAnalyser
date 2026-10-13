from array import array
from pathlib import Path
import sqlite3

import av
import pytest

from conftest import inventory
from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import (
    FRONT_ARRAY_TIMING_POLICY, FRONT_ARRAY_TIMESTAMP_PROVENANCE, FrontSourceDescriptor,
    FRONT_ALL_ZERO_HEADER_TIMING_POLICY, FRONT_ALL_ZERO_HEADER_TIMESTAMP_PROVENANCE,
)
from rosbag_analyser.processors.front_preview import FrontPreviewProcessor
from rosbag_analyser.processors.thumbnail import ThumbnailProcessor

pytestmark = pytest.mark.ros


@pytest.mark.parametrize("kind", ["array", "mono8"])
def test_serialized_grayscale_camera_creates_preview_and_thumbnail_with_record_timing(tmp_path, kind):
    serialization = pytest.importorskip("rclpy.serialization")
    messages = pytest.importorskip("std_msgs.msg")
    sensor_messages = pytest.importorskip("sensor_msgs.msg")
    source = tmp_path / "source"
    source.mkdir()
    database = source / "recording.db3"
    topic = (TopicFact("/robot/front_camera/actually_raw_image", "std_msgs/msg/UInt16MultiArray", "cdr", 4)
             if kind == "array" else TopicFact("/robot/front_camera/image_raw", "sensor_msgs/msg/Image", "cdr", 4))
    stamps = (1_000_000_000, 1_050_000_000, 1_050_000_000, 1_250_000_000)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE topics (id INTEGER PRIMARY KEY,name TEXT,type TEXT,serialization_format TEXT)")
        db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB)")
        db.execute("INSERT INTO topics VALUES (1,?,?,?)", (topic.name, topic.message_type, "cdr"))
        for i, stamp in enumerate(stamps, 1):
            if kind == "array":
                message = messages.UInt16MultiArray()
                message.layout.dim = [
                    messages.MultiArrayDimension(label="height", size=4, stride=32),
                    messages.MultiArrayDimension(label="width", size=8, stride=8),
                ]
                message.data = array("H", [i * 8192] * 32)
            else:
                message = sensor_messages.Image(width=8, height=4, step=8,
                                                encoding="mono8", data=bytes([i * 32] * 32))
            db.execute("INSERT INTO messages VALUES (?,1,?,?)",
                       (i, stamp, serialization.serialize_message(message)))
    identity = source_file_identity(database.stat())
    descriptor = FrontSourceDescriptor(1, "source", source / "metadata.yaml", database,
                                      identity, identity, stamps[0], 250_000_000, topic, "a" * 64)
    before = inventory(source)
    preview = tmp_path / "preview.mp4"
    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE).process(descriptor, preview)
    assert result.timing_policy == (FRONT_ARRAY_TIMING_POLICY if kind == "array"
                                   else FRONT_ALL_ZERO_HEADER_TIMING_POLICY)
    assert result.timestamp_provenance == (FRONT_ARRAY_TIMESTAMP_PROVENANCE if kind == "array"
                                          else FRONT_ALL_ZERO_HEADER_TIMESTAMP_PROVENANCE)
    assert (result.input_frame_count, result.encoded_frame_count, result.duplicate_timestamp_count) == (4, 3, 1)
    assert (result.coverage_start_ns, result.coverage_end_ns, result.header_span_ns) == (0, 250_000_000, 0)
    with av.open(str(preview)) as container:
        frames = list(container.decode(video=0))
    assert [float(f.pts * f.time_base) for f in frames] == pytest.approx([0, .05, .25])
    assert [round(float(f.to_ndarray(format="gray").mean())) for f in frames] == pytest.approx([32, 96, 128], abs=3)
    thumbnail = tmp_path / "thumbnail.png"
    facts = ThumbnailProcessor().process(descriptor, thumbnail)
    assert facts["topic"] == topic.name and facts["frame_count"] == 6
    assert facts["record_timestamps_ns"] == ["1050000000"] + ["1250000000"] * 5
    assert facts["frame_times_seconds"] == [.05] + [.25] * 5
    with av.open(str(thumbnail)) as container:
        frame = next(container.decode(video=0)).to_ndarray(format="rgb24")
    assert frame.shape == (4, 48, 3)
    assert [frame[0, index * 8].tolist() for index in range(6)] == [[96] * 3] + [[128] * 3] * 5
    assert inventory(source) == before
