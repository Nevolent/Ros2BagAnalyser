from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StreamCoverage:
    start_ns: int
    end_ns: int
    timestamp_provenance: str = "ros_record_timestamp"
    bounds: str = "measured"

    def __post_init__(self) -> None:
        if self.end_ns < self.start_ns:
            raise ValueError("Coverage end must not precede coverage start.")

    def contains(self, global_time_ns: int) -> bool:
        return self.start_ns <= global_time_ns <= self.end_ns

    def media_time_ns(self, global_time_ns: int) -> int | None:
        if not self.contains(global_time_ns):
            return None
        return global_time_ns - self.start_ns


@dataclass(frozen=True)
class GlobalTimeline:
    duration_ns: int

    def __post_init__(self) -> None:
        if self.duration_ns < 0:
            raise ValueError("Timeline duration must not be negative.")

    def clamp(self, value_ns: int) -> int:
        return min(max(value_ns, 0), self.duration_ns)


def record_time_to_bag_time_ns(
    record_timestamp_ns: int, bag_start_timestamp_ns: int
) -> int:
    return record_timestamp_ns - bag_start_timestamp_ns


def nanoseconds_to_media_pts(value_ns: int, media_timescale: int) -> int:
    if value_ns < 0:
        raise ValueError("Media timestamps must be nonnegative.")
    if media_timescale <= 0:
        raise ValueError("Media timescale must be positive.")
    return (value_ns * media_timescale + 500_000_000) // 1_000_000_000
