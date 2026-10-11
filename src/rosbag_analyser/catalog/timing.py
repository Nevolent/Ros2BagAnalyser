"""Bounded timestamp-only inspection; no payload decoding or source writes."""
from dataclasses import dataclass, field
import heapq
import sqlite3
from statistics import median
import time
from .limits import is_postgres_text

MAX_MESSAGES = 2_000_000
MAX_SECONDS = 5
MAX_TOPICS = 256
MAX_GAPS = 24
MIN_GAP_NS = 1_000_000_000
CADENCE_MULTIPLIER = 20
# Bump when timestamp inspection semantics change, independently of health
# presentation and preparation policies. Limits also participate in the key.
TIMING_POLICY_VERSION = 2


def timing_policy() -> list[int]:
    return [TIMING_POLICY_VERSION, MAX_MESSAGES, MAX_SECONDS, MAX_TOPICS,
            MAX_GAPS, MIN_GAP_NS, CADENCE_MULTIPLIER]


def valid_cached_timing(value: object) -> bool:
    """Reject incomplete/invalid saved evidence instead of poisoning a rescan."""
    if not isinstance(value, dict):
        return False
    count = value.get("messages_checked")
    gaps = value.get("gaps")
    if (value.get("status") not in ("complete", "partial")
            or type(count) is not int or not 0 <= count <= MAX_MESSAGES
            or value.get("gap_limit") != MAX_GAPS
            or not isinstance(gaps, list) or len(gaps) > MAX_GAPS):
        return False
    try:
        origin = value["origin_ns"]
        if origin is None:
            return count == 0 and not gaps
        if not isinstance(origin, str) or not 0 <= int(origin) <= 2**63 - 1:
            return False
        for gap in gaps:
            topic = gap["topic"]
            if topic is not None and (not isinstance(topic, str) or not is_postgres_text(topic)):
                return False
            times = [gap[key] for key in ("start_ns", "end_ns", "duration_ns")]
            if not all(isinstance(item, str) for item in times):
                return False
            start, end, duration = map(int, times)
            if not (0 <= start < end <= 2**63 - 1 and duration == end - start):
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


@dataclass
class Cadence:
    previous: int | None = None
    intervals: list[int] = field(default_factory=list)
    largest: list[tuple[int, int, int]] = field(default_factory=list)

    def add(self, timestamp: int) -> None:
        if self.previous is not None and timestamp > self.previous:
            delta = timestamp - self.previous
            if len(self.intervals) < 1024:
                self.intervals.append(delta)
            if delta >= MIN_GAP_NS:
                heapq.heappush(self.largest, (delta, self.previous, timestamp))
                if len(self.largest) > MAX_GAPS:
                    heapq.heappop(self.largest)
        self.previous = timestamp

    def gaps(self, topic: str | None, origin: int) -> list[dict]:
        # Sparse/event-driven streams have too little cadence evidence.
        if len(self.intervals) < 20:
            return []
        cadence = median(self.intervals)
        threshold = max(MIN_GAP_NS, int(cadence * CADENCE_MULTIPLIER))
        return [
            {"topic": topic, "start_ns": str(start - origin),
             "end_ns": str(end - origin), "duration_ns": str(delta)}
            for delta, start, end in self.largest if delta >= threshold
        ]


def inspect_timing(connection: sqlite3.Connection) -> dict:
    deadline = time.monotonic() + MAX_SECONDS
    connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    all_messages = Cadence()
    streams = {}
    origin = None
    count = 0
    complete = False
    stamps = {}
    try:
        topics = connection.execute(
            "SELECT id, substr(name, 1, 4096) FROM topics WHERE type IN "
            "('sensor_msgs/msg/Image', 'sensor_msgs/msg/Imu') LIMIT ?",
            (MAX_TOPICS + 1,),
        ).fetchall()
        streams = {row[0]: (row[1], Cadence()) for row in topics[:MAX_TOPICS]
                   if isinstance(row[1], str) and is_postgres_text(row[1])}
        # ROS bags normally provide timestamp_idx. SQLite's query budget also
        # bounds sorting work for bags without an index.
        # The timestamp-only query uses ROS's covering timestamp index. Including
        # topic_id here forces a random source-page read for every message on NAS.
        cursor = connection.execute(
            "SELECT timestamp FROM messages ORDER BY timestamp LIMIT ?",
            (MAX_MESSAGES + 1,),
        )
        for (timestamp,) in cursor:
            if count >= MAX_MESSAGES or time.monotonic() >= deadline:
                break
            if not isinstance(timestamp, int) or timestamp < 0:
                raise ValueError("Invalid ROS timestamp")
            if origin is None:
                origin = timestamp
            all_messages.add(timestamp)
            count += 1
        else:
            complete = True
        global_complete = complete
        complete = False
        # Inspect sensor timestamps with sequential table-header reads. Sort the
        # bounded timestamp lists in memory, so unordered insertions stay valid.
        stamps = {topic_id: [] for topic_id in streams}
        sensor_rows = 0
        if streams:
            for topic_id, timestamp in connection.execute(
                "SELECT topic_id, timestamp FROM messages NOT INDEXED LIMIT ?",
                (MAX_MESSAGES + 1,),
            ):
                if sensor_rows >= MAX_MESSAGES or time.monotonic() >= deadline:
                    break
                sensor_rows += 1
                if not isinstance(timestamp, int) or timestamp < 0:
                    raise ValueError("Invalid ROS timestamp")
                if topic_id in stamps:
                    stamps[topic_id].append(timestamp)
            else:
                complete = global_complete and len(topics) <= MAX_TOPICS and len(streams) == len(topics)
        else:
            complete = global_complete and not topics
    except sqlite3.DatabaseError as error:
        # A time-budget interruption is partial evidence; actual corruption must
        # still reach the caller's damaged/uninspectable classification.
        if getattr(error, "sqlite_errorcode", None) != getattr(sqlite3, "SQLITE_INTERRUPT", 9) and str(error) != "interrupted":
            raise
    except ValueError:
        pass
    finally:
        connection.set_progress_handler(None, 0)
    for topic_id, timestamps in stamps.items():
        for timestamp in sorted(timestamps):
            streams[topic_id][1].add(timestamp)
    gaps = all_messages.gaps(None, origin or 0)
    # A global recording pause already explains the same interval on a sensor.
    global_intervals = {(gap["start_ns"], gap["end_ns"]) for gap in gaps}
    for name, cadence in streams.values():
        gaps.extend(gap for gap in cadence.gaps(name, origin or 0)
                    if (gap["start_ns"], gap["end_ns"]) not in global_intervals)
    gaps.sort(key=lambda gap: int(gap["duration_ns"]), reverse=True)
    return {"status": "complete" if complete else "partial", "messages_checked": count,
            "origin_ns": str(origin) if origin is not None else None,
            "gaps": gaps[:MAX_GAPS], "gap_limit": MAX_GAPS}
