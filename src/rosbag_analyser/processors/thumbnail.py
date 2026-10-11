"""Read a few bounded image payloads, never transcode the recording."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
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
        def checkpoint():
            if control is not None:
                control.checkpoint("processing")

        checkpoint()
        with _open_source_database(descriptor) as connection:
            topics = (descriptor.topics or (descriptor.topic,))[:256]
            topic_ids = {
                topic.name: _topic_id(connection, replace(descriptor, topic=topic))
                for topic in topics
            }
            first, last = {}, {}
            wanted = set(topic_ids.values())
            # ROS's timestamp-only index requires a random table lookup for every
            # topic filter. On CIFS that is much slower than reading table headers
            # sequentially. Never select blobs during these bounded-memory scans.
            for message_id, topic_id, timestamp in _metadata_rows(connection, checkpoint):
                if topic_id not in wanted:
                    continue
                previous = first.get(topic_id)
                if previous is None or (timestamp, -message_id) < (previous[1], -previous[0]):
                    first[topic_id] = (message_id, timestamp)
                last[topic_id] = max(last.get(topic_id, timestamp), timestamp)
            for topic in topics:
                checkpoint()
                topic_id = topic_ids[topic.name]
                first_message = first.get(topic_id)
                if first_message is None:
                    continue
                image = _read_image(connection, first_message[0], self.image_decoder)
                if image.encoding not in COLOUR_IMAGE_CHANNELS:
                    continue
                _validate_image(image)
                midpoint = first_message[1] + (last[topic_id] - first_message[1]) // 2
                chosen = first_message if midpoint == first_message[1] else None
                if chosen is None:
                    for message_id, candidate_id, timestamp in _metadata_rows(connection, checkpoint):
                        if candidate_id == topic_id and timestamp >= midpoint:
                            if chosen is None or (timestamp, -message_id) < (chosen[1], -chosen[0]):
                                chosen = (message_id, timestamp)
                if chosen[0] != first_message[0]:
                    image = _read_image(connection, chosen[0], self.image_decoder)
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


def _metadata_rows(connection, checkpoint):
    deadline = time.monotonic() + 30
    expired = False

    def progress():
        nonlocal expired
        expired = time.monotonic() > deadline
        return int(expired)

    connection.set_progress_handler(progress, 10000)
    try:
        for index, row in enumerate(connection.execute(
            "SELECT id, topic_id, timestamp FROM messages NOT INDEXED"
        )):
            if index % 1024 == 0:
                checkpoint()
                deadline = time.monotonic() + 30
            yield row
    except sqlite3.Error as error:
        if expired:
            raise FrontPreviewProcessingError(
                "thumbnail_query_timeout",
                "Thumbnail timestamp inspection exceeded its query time limit.",
            ) from error
        raise
    finally:
        connection.set_progress_handler(None, 0)


def _read_image(connection, message_id, decoder):
    size = connection.execute("SELECT length(data) FROM messages WHERE id = ?", (message_id,)).fetchone()[0]
    return _decode_image(decoder, _message_data(connection.cursor(), message_id, size))
