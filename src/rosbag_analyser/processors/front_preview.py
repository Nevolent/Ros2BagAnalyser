from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import os
from pathlib import Path
import sqlite3
import stat
from typing import Callable, Iterator

import av
from av.video.frame import PictureType
import numpy as np

from rosbag_analyser.catalog.paths import SourceFileIdentity, source_file_identity
from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.front_preview import FrontSourceDescriptor, IMAGE_MESSAGE_TYPE
from rosbag_analyser.timeline import nanoseconds_to_media_pts


MAX_IMAGE_WIDTH = 4_096
MAX_IMAGE_HEIGHT = 4_096
MAX_IMAGE_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_SERIALIZED_IMAGE_BYTES = MAX_IMAGE_PAYLOAD_BYTES + 1024 * 1024


class FrontPreviewProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class DecodedImage:
    width: int
    height: int
    encoding: str
    step: int
    data: bytes


@dataclass(frozen=True)
class FrontPreviewResult:
    input_frame_count: int
    encoded_frame_count: int
    duplicate_timestamp_count: int
    coverage_start_ns: int
    coverage_end_ns: int
    output_width: int
    output_height: int
    measured_span_ns: int


ImageDecoder = Callable[[bytes], DecodedImage]


class FrontPreviewProcessor:
    def __init__(
        self,
        profile: PreviewProfile,
        image_decoder: ImageDecoder | None = None,
    ) -> None:
        self.profile = profile
        self.image_decoder = image_decoder or deserialize_ros_image

    def process(
        self, descriptor: FrontSourceDescriptor, output_path: Path
    ) -> FrontPreviewResult:
        messages = _iter_topic_messages(descriptor)
        pending_timestamp: int | None = None
        pending_image: DecodedImage | None = None
        first_timestamp: int | None = None
        last_timestamp: int | None = None
        input_frames = 0
        encoded_frames = 0
        duplicates = 0
        source_size: tuple[int, int] | None = None
        output_size: tuple[int, int] | None = None
        container: av.container.OutputContainer | None = None
        stream: av.video.stream.VideoStream | None = None
        time_base = Fraction(1, self.profile.media_timescale)
        keyframe_interval_ns = self.profile.keyframe_interval_seconds * 1_000_000_000
        last_keyframe_elapsed_ns: int | None = None
        processing_failure: BaseException | None = None

        try:
            for record_timestamp, serialized in messages:
                input_frames += 1
                try:
                    image = self.image_decoder(serialized)
                except FrontPreviewProcessingError:
                    raise
                except Exception as error:
                    raise FrontPreviewProcessingError(
                        "front_image_deserialization_failed",
                        "A front-camera image could not be decoded.",
                    ) from error
                _validate_image(image)
                dimensions = (image.width, image.height)
                if source_size is None:
                    source_size = dimensions
                    output_size = _output_dimensions(
                        image.width, image.height, self.profile
                    )
                elif source_size != dimensions:
                    raise FrontPreviewProcessingError(
                        "front_image_dimensions_changed",
                        "The front-camera dimensions changed during the recording.",
                    )

                if pending_timestamp is not None and record_timestamp < pending_timestamp:
                    raise FrontPreviewProcessingError(
                        "front_timestamps_invalid",
                        "Front-camera record timestamps are not ordered.",
                    )
                if pending_timestamp == record_timestamp:
                    pending_image = image
                    duplicates += 1
                    continue

                if pending_timestamp is not None and pending_image is not None:
                    if first_timestamp is None:
                        first_timestamp = pending_timestamp
                    if container is None or stream is None:
                        assert output_size is not None
                        container, stream = _open_output(
                            output_path, output_size, self.profile, time_base
                        )
                    elapsed_ns = pending_timestamp - first_timestamp
                    force_keyframe = (
                        last_keyframe_elapsed_ns is None
                        or elapsed_ns - last_keyframe_elapsed_ns >= keyframe_interval_ns
                    )
                    _encode_image(
                        container,
                        stream,
                        pending_image,
                        elapsed_ns,
                        time_base,
                        self.profile,
                        force_keyframe=force_keyframe,
                    )
                    if force_keyframe:
                        last_keyframe_elapsed_ns = elapsed_ns
                    encoded_frames += 1
                    last_timestamp = pending_timestamp

                pending_timestamp = record_timestamp
                pending_image = image

            if pending_timestamp is None or pending_image is None:
                raise FrontPreviewProcessingError(
                    "front_topic_empty", "The front-camera topic contains no frames."
                )
            if first_timestamp is None:
                first_timestamp = pending_timestamp
            if container is None or stream is None:
                assert output_size is not None
                container, stream = _open_output(
                    output_path, output_size, self.profile, time_base
                )
            elapsed_ns = pending_timestamp - first_timestamp
            force_keyframe = (
                last_keyframe_elapsed_ns is None
                or elapsed_ns - last_keyframe_elapsed_ns >= keyframe_interval_ns
            )
            _encode_image(
                container,
                stream,
                pending_image,
                elapsed_ns,
                time_base,
                self.profile,
                force_keyframe=force_keyframe,
            )
            encoded_frames += 1
            last_timestamp = pending_timestamp
            for packet in stream.encode():
                container.mux(packet)
        except FrontPreviewProcessingError as error:
            processing_failure = error
            raise
        except (av.error.FFmpegError, OSError, ValueError) as error:
            processing_failure = error
            raise FrontPreviewProcessingError(
                "front_encoding_failed", "The front-camera preview could not be encoded."
            ) from error
        except BaseException as error:
            processing_failure = error
            raise
        finally:
            if container is not None:
                try:
                    container.close()
                except (av.error.FFmpegError, OSError, ValueError) as error:
                    if processing_failure is None:
                        raise FrontPreviewProcessingError(
                            "front_encoding_failed",
                            "The front-camera preview could not be encoded.",
                        ) from error

        assert first_timestamp is not None
        assert last_timestamp is not None
        assert output_size is not None
        return FrontPreviewResult(
            input_frame_count=input_frames,
            encoded_frame_count=encoded_frames,
            duplicate_timestamp_count=duplicates,
            coverage_start_ns=first_timestamp - descriptor.bag_start_ns,
            coverage_end_ns=last_timestamp - descriptor.bag_start_ns,
            output_width=output_size[0],
            output_height=output_size[1],
            measured_span_ns=last_timestamp - first_timestamp,
        )


def deserialize_ros_image(serialized: bytes) -> DecodedImage:
    try:
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import Image
    except ImportError as error:
        raise FrontPreviewProcessingError(
            "ros_runtime_unavailable",
            "The ROS 2 Humble Python environment is unavailable to the worker.",
        ) from error
    try:
        message = deserialize_message(serialized, Image)
    except Exception as error:
        raise FrontPreviewProcessingError(
            "front_image_deserialization_failed",
            "A front-camera image could not be decoded.",
        ) from error
    return DecodedImage(
        width=int(message.width),
        height=int(message.height),
        encoding=str(message.encoding),
        step=int(message.step),
        data=bytes(message.data),
    )


def _iter_topic_messages(
    descriptor: FrontSourceDescriptor,
) -> Iterator[tuple[int, bytes]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(descriptor.database_path, flags)
    except OSError as error:
        raise FrontPreviewProcessingError(
            "front_database_open_failed", "The ROS database could not be opened safely."
        ) from error
    connection: sqlite3.Connection | None = None
    try:
        before = os.fstat(file_descriptor)
        before_identity = source_file_identity(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or before_identity != descriptor.database_identity
        ):
            raise FrontPreviewProcessingError(
                "front_source_changed",
                "The ROS database changed before preview generation.",
            )
        uri = f"file:/proc/self/fd/{file_descriptor}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        topic_rows = connection.execute(
            """
            SELECT id, type, serialization_format
            FROM topics
            WHERE name = ?
            LIMIT 2
            """,
            (descriptor.topic.name,),
        ).fetchall()
        if len(topic_rows) != 1:
            raise FrontPreviewProcessingError(
                "front_topic_unavailable",
                "The configured front-camera topic is unavailable in the database.",
            )
        topic_id, message_type, serialization = topic_rows[0]
        if message_type != IMAGE_MESSAGE_TYPE or serialization != "cdr":
            raise FrontPreviewProcessingError(
                "front_topic_contract_changed",
                "The front-camera topic no longer matches its catalogued type.",
            )
        cursor = connection.execute(
            """
            SELECT id, timestamp, length(data)
            FROM messages
            WHERE topic_id = ?
            ORDER BY timestamp, id
            """,
            (topic_id,),
        )
        data_cursor = connection.cursor()
        for message_id, timestamp, serialized_size in cursor:
            if (
                not isinstance(serialized_size, int)
                or serialized_size <= 0
                or serialized_size > MAX_SERIALIZED_IMAGE_BYTES
            ):
                raise FrontPreviewProcessingError(
                    "front_serialized_payload_invalid",
                    "A front-camera serialized image exceeds the supported size.",
                )
            row = data_cursor.execute(
                "SELECT data FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                raise FrontPreviewProcessingError(
                    "front_database_read_failed",
                    "The front-camera stream could not be read from the ROS database.",
                )
            data = row[0]
            if not isinstance(data, bytes):
                data = bytes(data)
            yield int(timestamp), data
        after = os.fstat(file_descriptor)
        if source_file_identity(after) != before_identity:
            raise FrontPreviewProcessingError(
                "front_source_changed",
                "The ROS database changed during preview generation.",
            )
    except sqlite3.Error as error:
        raise FrontPreviewProcessingError(
            "front_database_read_failed",
            "The front-camera stream could not be read from the ROS database.",
        ) from error
    finally:
        if connection is not None:
            connection.close()
        os.close(file_descriptor)


def _validate_image(image: DecodedImage) -> None:
    if image.encoding != "bgr8":
        raise FrontPreviewProcessingError(
            "front_encoding_unsupported",
            "The front-camera image encoding is unsupported.",
        )
    if (
        image.width <= 0
        or image.height <= 0
        or image.width > MAX_IMAGE_WIDTH
        or image.height > MAX_IMAGE_HEIGHT
    ):
        raise FrontPreviewProcessingError(
            "front_dimensions_invalid", "A front-camera image has invalid dimensions."
        )
    packed_step = image.width * 3
    if image.step < packed_step:
        raise FrontPreviewProcessingError(
            "front_step_invalid", "A front-camera image has an invalid row step."
        )
    expected_payload = image.step * image.height
    if (
        expected_payload > MAX_IMAGE_PAYLOAD_BYTES
        or len(image.data) != expected_payload
    ):
        raise FrontPreviewProcessingError(
            "front_payload_invalid", "A front-camera image has an invalid payload."
        )


def _output_dimensions(
    width: int, height: int, profile: PreviewProfile
) -> tuple[int, int]:
    scale = min(1.0, profile.max_width / width, profile.max_height / height)
    output_width = max(2, int(width * scale))
    output_height = max(2, int(height * scale))
    output_width -= output_width % 2
    output_height -= output_height % 2
    return output_width, output_height


def _open_output(
    output_path: Path,
    output_size: tuple[int, int],
    profile: PreviewProfile,
    time_base: Fraction,
) -> tuple[av.container.OutputContainer, av.video.stream.VideoStream]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(
        os.fspath(output_path),
        mode="w",
        format=profile.container,
        options={"movflags": "+faststart"},
    )
    stream = container.add_stream(profile.codec)
    stream.width = output_size[0]
    stream.height = output_size[1]
    stream.pix_fmt = profile.pixel_format
    stream.time_base = time_base
    stream.codec_context.time_base = time_base
    stream.codec_context.max_b_frames = 0
    stream.options = {
        "crf": str(profile.crf),
        "preset": profile.preset,
        "sc_threshold": "0",
    }
    return container, stream


def _encode_image(
    container: av.container.OutputContainer,
    stream: av.video.stream.VideoStream,
    image: DecodedImage,
    elapsed_ns: int,
    time_base: Fraction,
    profile: PreviewProfile,
    *,
    force_keyframe: bool,
) -> None:
    rows = np.frombuffer(image.data, dtype=np.uint8).reshape(image.height, image.step)
    pixels = np.ascontiguousarray(rows[:, : image.width * 3]).reshape(
        image.height, image.width, 3
    )
    frame = av.VideoFrame.from_ndarray(pixels, format="bgr24")
    if frame.width != stream.width or frame.height != stream.height:
        frame = frame.reformat(
            width=stream.width,
            height=stream.height,
            format=profile.pixel_format,
        )
    frame.pts = nanoseconds_to_media_pts(elapsed_ns, profile.media_timescale)
    frame.time_base = time_base
    if force_keyframe:
        frame.pict_type = PictureType.I
    for packet in stream.encode(frame):
        container.mux(packet)
