"""Read a few bounded image payloads, never transcode the recording."""
from __future__ import annotations

from dataclasses import replace
import time

import av
import numpy as np

from rosbag_analyser.front_preview import COLOUR_IMAGE_CHANNELS
from rosbag_analyser.thumbnail import MAX_THUMBNAIL_SIDE
from .front_preview import (
    FrontPreviewProcessingError, _open_source_database, _topic_id, _message_data,
    _decode_image, _validate_image, deserialize_ros_image,
)


class ThumbnailProcessor:
    def __init__(self, image_decoder=None):
        self.image_decoder = image_decoder or deserialize_ros_image

    def process(self, descriptor, output_path, *, control=None):
        started = time.monotonic()

        def checkpoint():
            if control is not None:
                control.checkpoint("processing", force=True)

        checkpoint()
        with _open_source_database(descriptor) as connection:
            # Timestamp-only queries use the existing ROS timestamp index. SQLite
            # reads at most one first-frame payload per candidate and one chosen
            # payload; no OFFSET through image blobs or video encoding is needed.
            connection.set_progress_handler(lambda: int(time.monotonic() - started > 30), 10000)
            for topic in (descriptor.topics or (descriptor.topic,))[:256]:
                checkpoint()
                started = time.monotonic()
                selected = replace(descriptor, topic=topic)
                topic_id = _topic_id(connection, selected)
                first = connection.execute(
                    "SELECT id, timestamp, length(data) FROM messages WHERE topic_id = ? "
                    "ORDER BY timestamp, id DESC LIMIT 1", (topic_id,),
                ).fetchone()
                if first is None:
                    continue
                image = _decode_image(self.image_decoder, _message_data(connection.cursor(), first[0], first[2]))
                if image.encoding not in COLOUR_IMAGE_CHANNELS:
                    continue
                _validate_image(image)
                last = connection.execute(
                    "SELECT timestamp FROM messages WHERE topic_id = ? ORDER BY timestamp DESC LIMIT 1",
                    (topic_id,),
                ).fetchone()
                midpoint = first[1] + (last[0] - first[1]) // 2
                chosen = connection.execute(
                    "SELECT id, timestamp, length(data) FROM messages WHERE topic_id = ? AND timestamp >= ? "
                    "ORDER BY timestamp, id DESC LIMIT 1", (topic_id, midpoint),
                ).fetchone()
                if chosen[0] != first[0]:
                    image = _decode_image(self.image_decoder, _message_data(connection.cursor(), chosen[0], chosen[2]))
                    _validate_image(image)
                break
            else:
                raise FrontPreviewProcessingError("thumbnail_camera_unavailable", "No supported colour camera is available for a thumbnail.")
        checkpoint()
        channels = COLOUR_IMAGE_CHANNELS[image.encoding]
        pixels = np.frombuffer(image.data, dtype=np.uint8).reshape(image.height, image.step)
        pixels = pixels[:, :image.width * channels].reshape(image.height, image.width, channels)
        pixel_format = {"rgb8": "rgb24", "bgr8": "bgr24", "rgba8": "rgba", "bgra8": "bgra"}[image.encoding]
        frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(pixels), format=pixel_format)
        scale = min(1, MAX_THUMBNAIL_SIDE / max(image.width, image.height))
        width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
        frame = frame.reformat(width=width, height=height, format="rgb24")
        codec = av.CodecContext.create("png", "w")
        codec.width, codec.height, codec.pix_fmt = width, height, "rgb24"
        data = b"".join(bytes(packet) for packet in codec.encode(frame) + codec.encode(None))
        output_path.write_bytes(data)
        checkpoint()
        timestamp = chosen[1] - descriptor.bag_start_ns
        return {"topic": topic.name, "record_timestamp_ns": str(chosen[1]),
                "coverage_ns": timestamp, "width": width, "height": height}
