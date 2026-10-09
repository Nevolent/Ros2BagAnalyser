"""Bounded CDR decoder for Header + Float64MultiArray; no custom ROS package needed."""
import struct

from rosbag_analyser.encoder_series import (
    ENCODER_MESSAGE_TYPE,
    ENCODER_SERIES_DEFINITIONS,
    ENCODER_SERIES_BY_COMPONENT,
)
from rosbag_analyser.processors.imu_series import (
    ImuSeriesProcessor, ImuSeriesProcessingError, ImuValueDecoder,
)

MAX_SERIALIZED_ENCODER_BYTES = 4096


class _CdrReader:
    def __init__(self, data: bytes) -> None:
        if (
            len(data) > MAX_SERIALIZED_ENCODER_BYTES
            or data[:4] not in (b"\x00\x01\x00\x00", b"\x00\x00\x00\x00")
        ):
            raise ValueError("Unsupported encoder CDR encapsulation or size")
        self.data = data
        self.offset = 4
        self.endian = "<" if data[1] == 1 else ">"

    def scalar(self, fmt: str, alignment: int):
        self.offset += (-(self.offset - 4)) % alignment
        size = struct.calcsize(fmt)
        if self.offset + size > len(self.data):
            raise ValueError("Truncated encoder message")
        value = struct.unpack_from(self.endian + fmt, self.data, self.offset)[0]
        self.offset += size
        return value

    def string(self) -> str:
        size = self.scalar("I", 4)
        if not 1 <= size <= 1024 or self.offset + size > len(self.data):
            raise ValueError("Invalid encoder string")
        value = self.data[self.offset:self.offset + size]
        self.offset += size
        if value[-1] != 0:
            raise ValueError("Unterminated encoder string")
        return value[:-1].decode("utf-8")


def deserialize_encoder_values(serialized: bytes) -> tuple[float, ...]:
    reader = _CdrReader(serialized)
    reader.scalar("i", 4)  # Header stamp seconds; the timeline uses database record time.
    if reader.scalar("I", 4) >= 1_000_000_000:
        raise ValueError("Invalid encoder header nanoseconds")
    reader.string()  # frame_id
    count = reader.scalar("I", 4)
    if count > 16:
        raise ValueError("Encoder layout exceeds the dimension bound")
    sizes = []
    for _ in range(count):
        reader.string()
        sizes.append(reader.scalar("I", 4))
        reader.scalar("I", 4)  # stride
    if reader.scalar("I", 4) != 0:
        raise ValueError("Encoder data offset must be zero")
    if reader.scalar("I", 4) != 6:
        raise ValueError("Encoder message must contain six wheel values")
    if sizes:
        product = 1
        for size in sizes:
            product *= size
        if product != 6:
            raise ValueError("Encoder layout does not describe six values")
    values = tuple(reader.scalar("d", 8) for _ in range(6))
    if reader.offset != len(serialized):
        raise ValueError("Unexpected trailing encoder data")
    return values


class EncoderSeriesProcessor(ImuSeriesProcessor):
    message_type = ENCODER_MESSAGE_TYPE
    definitions = ENCODER_SERIES_DEFINITIONS
    series_by_component = ENCODER_SERIES_BY_COMPONENT
    max_serialized_bytes = MAX_SERIALIZED_ENCODER_BYTES
    label = "encoder"
    prefix = "encoder"

    def __init__(self, value_decoder: ImuValueDecoder | None = None) -> None:
        super().__init__(value_decoder or deserialize_encoder_values)


EncoderSeriesProcessingError = ImuSeriesProcessingError
