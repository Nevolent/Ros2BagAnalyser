"""Read a few bounded image payloads, never transcode the recording."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
import time
import io
from pathlib import Path

import av
import numpy as np

from rosbag_analyser.thumbnail import MAX_THUMBNAIL_SIDE, THUMBNAIL_FRAME_COUNT, png_bytes
from .video_frames import sample_video_frames
from .front_preview import (
    FrontPreviewProcessingError, _open_source_database, _topic_id, _message_data,
    _decode_image, _validate_image, deserialize_ros_image, decoder_for_topic,
    eligible_camera_image, _bgr_pixels,
)


class ThumbnailProcessor:
    def __init__(self, image_decoder=None, *, ffmpeg="ffmpeg", ffprobe="ffprobe"):
        self.image_decoder = image_decoder or deserialize_ros_image
        self.ffmpeg, self.ffprobe = str(ffmpeg), str(ffprobe)

    def process_video(self, descriptor, output_path, *, bag_start_ns, coverage_start_ns=0, topic="front-preview", control=None):
        images, times = sample_video_frames(Path(f"/proc/self/fd/{descriptor}"), video_fd=descriptor,
            count=THUMBNAIL_FRAME_COUNT, max_side=MAX_THUMBNAIL_SIDE,
            ffmpeg=self.ffmpeg, ffprobe=self.ffprobe, control=control, allow_partial=True)
        tiles = []
        for image in images:
            with av.open(io.BytesIO(image), format="image2pipe") as container:
                tiles.append(next(container.decode(video=0)).to_ndarray(format="rgb24"))
        stamps = [bag_start_ns + coverage_start_ns + round(t * 1e9) for t in times]
        return _write_strip(tiles, stamps, output_path, topic, bag_start_ns,
                            [coverage_start_ns / 1e9 + t for t in times])

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
            first, last, first_candidates = {}, {}, {}
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
                candidates = first_candidates.setdefault(topic_id, [])
                candidates.append((message_id, timestamp))
                candidates.sort(key=lambda row: (row[1], -row[0]))
                del candidates[4:]
            for topic in topics:
                checkpoint()
                topic_id = topic_ids[topic.name]
                first_message = first.get(topic_id)
                if first_message is None:
                    continue
                decoder = decoder_for_topic(topic, self.image_decoder)
                for candidate in first_candidates[topic_id]:
                    try:
                        image = _read_image(connection, candidate[0], decoder)
                        if not eligible_camera_image(image, topic):
                            continue
                        _validate_image(image)
                    except FrontPreviewProcessingError:
                        continue
                    first_message = candidate
                    break
                else:
                    continue
                targets = [first_message[1] + (last[topic_id] - first_message[1]) * n // (THUMBNAIL_FRAME_COUNT + 1)
                           for n in range(1, THUMBNAIL_FRAME_COUNT + 1)]
                chosen = [None] * THUMBNAIL_FRAME_COUNT
                # Select all six in the same pass. Approximate sevenths are enough;
                # no video decode, timestamp index creation or scan per frame.
                for message_id, candidate_id, timestamp in _metadata_rows(connection, checkpoint):
                    if candidate_id != topic_id:
                        continue
                    for index, target in enumerate(targets):
                        previous = chosen[index]
                        if timestamp >= target and (previous is None or
                                (timestamp, -message_id) < (previous[1], -previous[0])):
                            chosen[index] = (message_id, timestamp)
                scale = min(1, MAX_THUMBNAIL_SIDE / max(image.width, image.height))
                width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
                decoded = {first_message[0]: _pixels(image, width, height)}
                image_encoding = image.encoding
                del image
                tiles = []
                accepted = []
                for message_id, timestamp in chosen:
                    checkpoint()
                    tile = decoded.get(message_id)
                    if tile is None:
                        try:
                            frame_image = _read_image(connection, message_id, decoder)
                            _validate_image(frame_image)
                        except FrontPreviewProcessingError:
                            continue
                        if frame_image.encoding != image_encoding:
                            continue
                        tile = _pixels(frame_image, width, height)
                        decoded[message_id] = tile
                        del frame_image
                    tiles.append(tile)
                    accepted.append(timestamp)
                if not tiles:
                    # Preserve even one decodable source image on a broken stream.
                    tiles = [decoded[first_message[0]]]
                    accepted = [first_message[1]]
                break
            else:
                raise FrontPreviewProcessingError("thumbnail_camera_unavailable", "No supported camera frame is available for a thumbnail.")
        checkpoint()
        result = _write_strip(tiles, accepted, output_path, topic.name, descriptor.bag_start_ns)
        checkpoint()
        return result


def _write_strip(tiles, stamps, output_path, topic, bag_start_ns, times=None):
    height, width = tiles[0].shape[:2]
    if any(tile.shape != tiles[0].shape for tile in tiles):
        raise ValueError("Thumbnail tile dimensions changed")
    output_path.write_bytes(png_bytes(np.concatenate(tiles, axis=1)))
    middle = len(tiles) // 2
    return {"topic": topic, "record_timestamp_ns": str(stamps[middle]),
            "record_timestamps_ns": [str(stamp) for stamp in stamps],
            "frame_times_seconds": times if times is not None else [(stamp - bag_start_ns) / 1e9 for stamp in stamps],
            "coverage_ns": stamps[middle] - bag_start_ns, "width": width * len(tiles),
            "frame_width": width, "frame_count": len(tiles), "height": height}


def _pixels(image, width, height):
    frame = av.VideoFrame.from_ndarray(_bgr_pixels(image), format="bgr24")
    scale = min(width / image.width, height / image.height)
    resized = frame.reformat(width=max(1, round(image.width * scale)),
                             height=max(1, round(image.height * scale)), format="rgb24").to_ndarray()
    tile = np.zeros((height, width, 3), dtype=np.uint8)
    y, x = (height - resized.shape[0]) // 2, (width - resized.shape[1]) // 2
    tile[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return tile


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
