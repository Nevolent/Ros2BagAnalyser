from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import stat
from typing import Callable

from rosbag_analyser.catalog.metadata import MetadataError, TopicFact, parse_metadata_file
from rosbag_analyser.catalog.paths import (
    UnsafeSourcePath,
    resolve_declared_source,
    source_file_identity,
)
from rosbag_analyser.front_preview import (
    CDR_SERIALIZATION,
    IMAGE_MESSAGE_TYPE,
    FrontSourceDescriptor,
)
from rosbag_analyser.processors.front_preview import (
    MAX_SERIALIZED_IMAGE_BYTES,
    _message_data,
    _open_source_database,
    _topic_id,
)


MAX_HEADER_TIMESTAMP_NS = 9_223_372_036_854_775_807
DEFAULT_MAX_MESSAGES = 1_000_000


class FrontHeaderDiagnosticError(RuntimeError):
    """A safe failure from the standalone read-only front-header tool."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class HeaderStamp:
    sec: int
    nanosec: int


@dataclass(frozen=True)
class FrontImageFacts:
    """The limited image facts needed for a read-only source diagnostic."""

    header: HeaderStamp
    encoding: str


@dataclass(frozen=True)
class HeaderObservation:
    message_index: int
    message_id: int
    record_timestamp_ns: int
    header_sec: int
    header_nanosec: int
    header_timestamp_ns: int | None
    reason: str | None

    def json_values(self) -> dict[str, int | str | None]:
        document: dict[str, int | str | None] = asdict(self)
        document["record_timestamp_ns"] = str(self.record_timestamp_ns)
        if self.header_timestamp_ns is not None:
            document["header_timestamp_ns"] = str(self.header_timestamp_ns)
        return document


@dataclass(frozen=True)
class EncodingObservation:
    message_index: int
    message_id: int
    record_timestamp_ns: int
    encoding: str

    def json_values(self) -> dict[str, int | str]:
        return {
            "message_index": self.message_index,
            "message_id": self.message_id,
            "record_timestamp_ns": str(self.record_timestamp_ns),
            "encoding": self.encoding,
        }


@dataclass(frozen=True)
class FrontHeaderReport:
    message_count: int
    invalid_header_count: int
    out_of_order_header_count: int
    first_invalid: HeaderObservation | None
    first_out_of_order: HeaderObservation | None
    first_valid_header_timestamp_ns: int | None
    last_valid_header_timestamp_ns: int | None
    encoding_counts: dict[str, int] | None
    first_unsupported_encoding: EncodingObservation | None

    @property
    def strictly_ordered(self) -> bool:
        return self.invalid_header_count == 0 and self.out_of_order_header_count == 0

    def json_values(self) -> dict[str, object]:
        return {
            "message_count": self.message_count,
            "invalid_header_count": self.invalid_header_count,
            "out_of_order_header_count": self.out_of_order_header_count,
            "strictly_ordered": self.strictly_ordered,
            "first_invalid": (
                self.first_invalid.json_values() if self.first_invalid is not None else None
            ),
            "first_out_of_order": (
                self.first_out_of_order.json_values()
                if self.first_out_of_order is not None
                else None
            ),
            "first_valid_header_timestamp_ns": (
                str(self.first_valid_header_timestamp_ns)
                if self.first_valid_header_timestamp_ns is not None
                else None
            ),
            "last_valid_header_timestamp_ns": (
                str(self.last_valid_header_timestamp_ns)
                if self.last_valid_header_timestamp_ns is not None
                else None
            ),
            "encoding_counts": self.encoding_counts,
            "first_unsupported_encoding": (
                self.first_unsupported_encoding.json_values()
                if self.first_unsupported_encoding is not None
                else None
            ),
        }


HeaderDecoder = Callable[[bytes], HeaderStamp | FrontImageFacts]


def deserialize_ros_header_stamp(serialized: bytes) -> FrontImageFacts:
    """Read Image header and encoding facts from CDR; no output is generated."""

    try:
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import Image
    except ImportError as error:
        raise FrontHeaderDiagnosticError(
            "ros_runtime_unavailable",
            "The ROS 2 Humble Python environment is unavailable to the diagnostic tool.",
        ) from error
    try:
        message = deserialize_message(serialized, Image)
    except Exception as error:
        raise FrontHeaderDiagnosticError(
            "front_image_deserialization_failed",
            "A front-camera image could not be decoded for header inspection.",
        ) from error
    return FrontImageFacts(
        header=HeaderStamp(
            sec=int(message.header.stamp.sec), nanosec=int(message.header.stamp.nanosec)
        ),
        encoding=str(message.encoding),
    )


def resolve_front_source(
    archive_root: Path,
    recording_relative_path: str,
    front_topic: str,
) -> FrontSourceDescriptor:
    """Resolve one selected recording without traversing the archive tree."""

    root = _validated_archive_root(archive_root)
    recording_root = _resolve_selected_recording(root, recording_relative_path)
    metadata_path = recording_root / "metadata.yaml"
    try:
        metadata_details = metadata_path.lstat()
    except FileNotFoundError as error:
        raise FrontHeaderDiagnosticError(
            "metadata_missing", "The recording metadata is missing."
        ) from error
    except OSError as error:
        raise FrontHeaderDiagnosticError(
            "metadata_unreadable", "The recording metadata could not be read safely."
        ) from error
    if stat.S_ISLNK(metadata_details.st_mode) or not stat.S_ISREG(metadata_details.st_mode):
        raise FrontHeaderDiagnosticError(
            "metadata_unreadable", "The recording metadata is not a regular source file."
        )

    metadata_identity = source_file_identity(metadata_details)
    try:
        metadata = parse_metadata_file(metadata_path, expected_identity=metadata_identity)
    except MetadataError as error:
        raise FrontHeaderDiagnosticError(
            error.diagnostic.code, error.diagnostic.message
        ) from error
    support_error = metadata.support_diagnostic()
    if support_error is not None:
        raise FrontHeaderDiagnosticError(support_error.code, support_error.message)
    topic = _front_topic(metadata.topics, front_topic)
    try:
        database_path = resolve_declared_source(
            root, recording_root, metadata.relative_file_paths[0]
        )
        database_details = database_path.lstat()
    except (FileNotFoundError, OSError, UnsafeSourcePath) as error:
        raise FrontHeaderDiagnosticError(
            "front_database_unavailable",
            "The front-camera ROS database could not be resolved safely.",
        ) from error
    if not stat.S_ISREG(database_details.st_mode):
        raise FrontHeaderDiagnosticError(
            "front_database_unavailable", "The front-camera ROS database is not regular."
        )
    database_identity = source_file_identity(database_details)
    return FrontSourceDescriptor(
        recording_id=0,
        archive_relative_path=recording_relative_path,
        metadata_path=metadata_path,
        database_path=database_path,
        metadata_identity=metadata_identity,
        database_identity=database_identity,
        bag_start_ns=metadata.start_time_ns,
        bag_duration_ns=metadata.duration_ns,
        topic=topic,
        cache_identity="diagnostic-only",
    )


def inspect_front_headers(
    descriptor: FrontSourceDescriptor,
    *,
    max_messages: int = DEFAULT_MAX_MESSAGES,
    decoder: HeaderDecoder = deserialize_ros_header_stamp,
) -> FrontHeaderReport:
    """Inspect one stream through the same immutable SQLite access as the worker."""

    if isinstance(max_messages, bool) or not isinstance(max_messages, int) or max_messages <= 0:
        raise ValueError("The message limit must be a positive integer.")

    message_count = 0
    invalid_count = 0
    out_of_order_count = 0
    first_invalid: HeaderObservation | None = None
    first_out_of_order: HeaderObservation | None = None
    first_valid: int | None = None
    last_valid: int | None = None
    previous_valid: int | None = None
    encoding_counts: dict[str, int] | None = {}
    first_unsupported_encoding: EncodingObservation | None = None

    with _open_source_database(descriptor) as connection:
        topic_id = _topic_id(connection, descriptor)
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
        for message_id, record_timestamp, serialized_size in cursor:
            if message_count >= max_messages:
                raise FrontHeaderDiagnosticError(
                    "front_header_diagnostic_limit_exceeded",
                    "Front-header inspection reached its message limit before completion.",
                )
            message_count += 1
            if (
                not isinstance(serialized_size, int)
                or serialized_size <= 0
                or serialized_size > MAX_SERIALIZED_IMAGE_BYTES
            ):
                raise FrontHeaderDiagnosticError(
                    "front_serialized_payload_invalid",
                    "A front-camera serialized image exceeds the supported size.",
                )
            serialized = _message_data(data_cursor, int(message_id), serialized_size)
            decoded = decoder(serialized)
            if isinstance(decoded, FrontImageFacts):
                stamp = decoded.header
                encoding_counts[decoded.encoding] = (
                    encoding_counts.get(decoded.encoding, 0) + 1
                )
                if decoded.encoding != "bgr8" and first_unsupported_encoding is None:
                    first_unsupported_encoding = EncodingObservation(
                        message_index=message_count,
                        message_id=int(message_id),
                        record_timestamp_ns=int(record_timestamp),
                        encoding=decoded.encoding,
                    )
            else:
                stamp = decoded
                # Keep the pure header-inspection test seam backwards compatible.
                encoding_counts = None
            timestamp_ns, reason = _classify_header_stamp(stamp)
            observation = HeaderObservation(
                message_index=message_count,
                message_id=int(message_id),
                record_timestamp_ns=int(record_timestamp),
                header_sec=stamp.sec,
                header_nanosec=stamp.nanosec,
                header_timestamp_ns=timestamp_ns,
                reason=reason,
            )
            if reason is not None:
                invalid_count += 1
                if first_invalid is None:
                    first_invalid = observation
                continue
            assert timestamp_ns is not None
            if first_valid is None:
                first_valid = timestamp_ns
            last_valid = timestamp_ns
            if previous_valid is not None and timestamp_ns <= previous_valid:
                out_of_order_count += 1
                if first_out_of_order is None:
                    first_out_of_order = observation
            previous_valid = timestamp_ns

    return FrontHeaderReport(
        message_count=message_count,
        invalid_header_count=invalid_count,
        out_of_order_header_count=out_of_order_count,
        first_invalid=first_invalid,
        first_out_of_order=first_out_of_order,
        first_valid_header_timestamp_ns=first_valid,
        last_valid_header_timestamp_ns=last_valid,
        encoding_counts=encoding_counts,
        first_unsupported_encoding=first_unsupported_encoding,
    )


def _validated_archive_root(path: Path) -> Path:
    if not path.is_absolute():
        raise FrontHeaderDiagnosticError(
            "archive_root_invalid", "The archive root must be an absolute directory path."
        )
    try:
        details = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise FrontHeaderDiagnosticError(
            "archive_root_unavailable", "The archive root could not be checked safely."
        ) from error
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise FrontHeaderDiagnosticError(
            "archive_root_invalid", "The archive root must be a non-symbolic-link directory."
        )
    return resolved


def _resolve_selected_recording(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
        raise FrontHeaderDiagnosticError(
            "recording_path_invalid", "A recording path must be a safe archive-relative path."
        )
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise FrontHeaderDiagnosticError(
            "recording_path_invalid", "A recording path must be a safe archive-relative path."
        )
    current = root
    try:
        for part in parts:
            current = current / part
            details = current.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise FrontHeaderDiagnosticError(
                    "source_symlink_rejected", "Source symlinks are not supported by the diagnostic tool."
                )
        resolved = current.resolve(strict=True)
    except FrontHeaderDiagnosticError:
        raise
    except OSError as error:
        raise FrontHeaderDiagnosticError(
            "recording_path_unavailable", "The selected recording could not be resolved safely."
        ) from error
    if root not in resolved.parents or not resolved.is_dir():
        raise FrontHeaderDiagnosticError(
            "recording_path_invalid", "The selected recording is not a directory below the archive root."
        )
    return resolved


def _front_topic(topics: tuple[TopicFact, ...], topic_name: str) -> TopicFact:
    matches = [topic for topic in topics if topic.name == topic_name]
    if len(matches) != 1:
        raise FrontHeaderDiagnosticError(
            "front_topic_unavailable", "The configured front-camera topic is unavailable."
        )
    topic = matches[0]
    if topic.message_type != IMAGE_MESSAGE_TYPE or topic.serialization_format != CDR_SERIALIZATION:
        raise FrontHeaderDiagnosticError(
            "front_topic_contract_changed",
            "The front-camera topic is not a standard CDR image stream.",
        )
    return topic


def _classify_header_stamp(stamp: HeaderStamp) -> tuple[int | None, str | None]:
    if isinstance(stamp.sec, bool) or isinstance(stamp.nanosec, bool):
        return None, "invalid_value"
    if not isinstance(stamp.sec, int) or not isinstance(stamp.nanosec, int):
        return None, "invalid_value"
    if stamp.nanosec < 0 or stamp.nanosec >= 1_000_000_000:
        return None, "nanosecond_out_of_range"
    value = stamp.sec * 1_000_000_000 + stamp.nanosec
    if value <= 0:
        return value, "non_positive"
    if value > MAX_HEADER_TIMESTAMP_NS:
        return value, "out_of_range"
    return value, None
