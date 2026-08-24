from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
from typing import BinaryIO, Callable, Iterator, Sequence

from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.imu_series import (
    IMU_MESSAGE_TYPE,
    IMU_SERIES_BY_COMPONENT,
    IMU_SERIES_DEFINITIONS,
    SERIES_SCHEMA_VERSION,
    ImuSourceDescriptor,
)
from rosbag_analyser.job_control import JobControlToken


MAX_SERIALIZED_IMU_BYTES = 1024 * 1024
MAX_SERIES_BYTES = 32 * 1024 * 1024


class ImuSeriesProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class ImuComponentResult:
    id: str
    component: str
    finite_count: int
    non_finite_count: int
    minimum_value: float | None
    maximum_value: float | None


@dataclass(frozen=True)
class ImuSeriesResult:
    sample_count: int
    duplicate_timestamp_count: int
    coverage_start_ns: int
    coverage_end_ns: int
    series: tuple[ImuComponentResult, ...]
    warnings: tuple[str, ...]


ImuValueDecoder = Callable[[bytes], Sequence[float]]


class ImuSeriesProcessor:
    def __init__(self, value_decoder: ImuValueDecoder | None = None) -> None:
        self.value_decoder = value_decoder or deserialize_imu_values

    def process(
        self,
        descriptor: ImuSourceDescriptor,
        output_path: Path,
        *,
        control: JobControlToken | None = None,
    ) -> ImuSeriesResult:
        if descriptor.component not in IMU_SERIES_BY_COMPONENT:
            raise ImuSeriesProcessingError(
                "imu_component_unsupported",
                "The configured IMU component is unsupported.",
            )
        sample_count = 0
        duplicate_count = 0
        first_timestamp: int | None = None
        last_timestamp: int | None = None
        previous_timestamp: int | None = None
        finite_counts = [0] * len(IMU_SERIES_DEFINITIONS)
        non_finite_counts = [0] * len(IMU_SERIES_DEFINITIONS)
        minimum_values: list[float | None] = [None] * len(IMU_SERIES_DEFINITIONS)
        maximum_values: list[float | None] = [None] * len(IMU_SERIES_DEFINITIONS)

        try:
            with output_path.open("xb") as output:
                written = _write_bounded(
                    output,
                    b'{"schema_version":'
                    + str(SERIES_SCHEMA_VERSION).encode("ascii")
                    + b',"samples":[',
                    0,
                )
                first_sample = True
                for record_timestamp, serialized in _iter_topic_messages(descriptor):
                    if control is not None:
                        control.checkpoint("processing")
                    try:
                        values = tuple(
                            float(value) for value in self.value_decoder(serialized)
                        )
                        if len(values) != len(IMU_SERIES_DEFINITIONS):
                            raise ValueError("unexpected IMU value count")
                    except ImuSeriesProcessingError:
                        raise
                    except Exception as error:
                        raise ImuSeriesProcessingError(
                            "imu_deserialization_failed",
                            "An IMU message could not be decoded.",
                        ) from error

                    if previous_timestamp is not None:
                        if record_timestamp < previous_timestamp:
                            raise ImuSeriesProcessingError(
                                "imu_timestamps_invalid",
                                "IMU record timestamps are not ordered.",
                            )
                        if record_timestamp == previous_timestamp:
                            duplicate_count += 1
                    previous_timestamp = record_timestamp
                    if first_timestamp is None:
                        first_timestamp = record_timestamp
                    last_timestamp = record_timestamp

                    encoded_values: list[str] = []
                    for index, value in enumerate(values):
                        if math.isfinite(value):
                            encoded_values.append(
                                json.dumps(
                                    value,
                                    allow_nan=False,
                                    separators=(",", ":"),
                                )
                            )
                            finite_counts[index] += 1
                            minimum_values[index] = (
                                value
                                if minimum_values[index] is None
                                else min(minimum_values[index], value)
                            )
                            maximum_values[index] = (
                                value
                                if maximum_values[index] is None
                                else max(maximum_values[index], value)
                            )
                        else:
                            encoded_values.append("null")
                            non_finite_counts[index] += 1

                    bag_time_ns = record_timestamp - descriptor.bag_start_ns
                    sample = (
                        "["
                        + json.dumps(str(bag_time_ns))
                        + ","
                        + ",".join(encoded_values)
                        + "]"
                    )
                    prefix = "" if first_sample else ","
                    written = _write_bounded(
                        output,
                        (prefix + sample).encode("utf-8"),
                        written,
                    )
                    first_sample = False
                    sample_count += 1
                if control is not None:
                    control.checkpoint("processing", force=True)
                _write_bounded(output, b"]}", written)
        except ImuSeriesProcessingError:
            raise
        except OSError as error:
            raise ImuSeriesProcessingError(
                "imu_series_write_failed",
                "The derived IMU series could not be written.",
            ) from error

        if first_timestamp is None or last_timestamp is None or sample_count == 0:
            raise ImuSeriesProcessingError(
                "imu_topic_empty", "The configured IMU topic contains no samples."
            )
        if not any(finite_counts):
            raise ImuSeriesProcessingError(
                "imu_values_unavailable",
                "The IMU stream contains no finite supported values.",
            )

        coverage_start = first_timestamp - descriptor.bag_start_ns
        coverage_end = last_timestamp - descriptor.bag_start_ns
        warnings: list[str] = []
        if coverage_start < 0:
            warnings.append("coverage_starts_before_recording")
        elif coverage_start > 0:
            warnings.append("coverage_starts_after_recording")
        if coverage_end < descriptor.bag_duration_ns:
            warnings.append("coverage_ends_before_recording")
        elif coverage_end > descriptor.bag_duration_ns:
            warnings.append("coverage_ends_after_recording")
        if any(non_finite_counts):
            warnings.append("non_finite_values_present")

        return ImuSeriesResult(
            sample_count=sample_count,
            duplicate_timestamp_count=duplicate_count,
            coverage_start_ns=coverage_start,
            coverage_end_ns=coverage_end,
            series=tuple(
                ImuComponentResult(
                    id=definition.id,
                    component=definition.component,
                    finite_count=finite_counts[index],
                    non_finite_count=non_finite_counts[index],
                    minimum_value=minimum_values[index],
                    maximum_value=maximum_values[index],
                )
                for index, definition in enumerate(IMU_SERIES_DEFINITIONS)
            ),
            warnings=tuple(warnings),
        )


def deserialize_imu_values(serialized: bytes) -> tuple[float, ...]:
    try:
        from rclpy.serialization import deserialize_message
        from sensor_msgs.msg import Imu
    except ImportError as error:
        raise ImuSeriesProcessingError(
            "ros_runtime_unavailable",
            "The ROS 2 Humble Python environment is unavailable to the worker.",
        ) from error
    try:
        message = deserialize_message(serialized, Imu)
    except Exception as error:
        raise ImuSeriesProcessingError(
            "imu_deserialization_failed", "An IMU message could not be decoded."
        ) from error
    return (
        float(message.angular_velocity.x),
        float(message.angular_velocity.y),
        float(message.angular_velocity.z),
        float(message.linear_acceleration.x),
        float(message.linear_acceleration.y),
        float(message.linear_acceleration.z),
    )


def _iter_topic_messages(
    descriptor: ImuSourceDescriptor,
) -> Iterator[tuple[int, bytes]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        file_descriptor = os.open(descriptor.database_path, flags)
    except OSError as error:
        raise ImuSeriesProcessingError(
            "imu_database_open_failed", "The ROS database could not be opened safely."
        ) from error
    connection: sqlite3.Connection | None = None
    try:
        before = os.fstat(file_descriptor)
        before_identity = source_file_identity(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or before_identity != descriptor.database_identity
        ):
            raise ImuSeriesProcessingError(
                "imu_source_changed",
                "The ROS database changed before IMU extraction.",
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
            raise ImuSeriesProcessingError(
                "imu_topic_unavailable",
                "The configured IMU topic is unavailable in the database.",
            )
        topic_id, message_type, serialization = topic_rows[0]
        if message_type != IMU_MESSAGE_TYPE or serialization != "cdr":
            raise ImuSeriesProcessingError(
                "imu_topic_contract_changed",
                "The IMU topic no longer matches its catalogued type.",
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
                or serialized_size > MAX_SERIALIZED_IMU_BYTES
            ):
                raise ImuSeriesProcessingError(
                    "imu_serialized_payload_invalid",
                    "An IMU message exceeds the supported serialized size.",
                )
            row = data_cursor.execute(
                "SELECT data FROM messages WHERE id = ?", (message_id,)
            ).fetchone()
            if row is None:
                raise ImuSeriesProcessingError(
                    "imu_database_read_failed",
                    "The IMU stream could not be read from the ROS database.",
                )
            data = row[0]
            if not isinstance(data, bytes):
                data = bytes(data)
            yield int(timestamp), data
        after = os.fstat(file_descriptor)
        if source_file_identity(after) != before_identity:
            raise ImuSeriesProcessingError(
                "imu_source_changed", "The ROS database changed during IMU extraction."
            )
    except sqlite3.Error as error:
        raise ImuSeriesProcessingError(
            "imu_database_read_failed",
            "The IMU stream could not be read from the ROS database.",
        ) from error
    finally:
        if connection is not None:
            connection.close()
        os.close(file_descriptor)


def _write_bounded(output: BinaryIO, payload: bytes, written: int) -> int:
    new_size = written + len(payload)
    if new_size > MAX_SERIES_BYTES:
        raise ImuSeriesProcessingError(
            "imu_series_too_large",
            "The derived IMU series exceeds the supported size.",
        )
    output.write(payload)
    return new_size
