from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rosbag_analyser.preparation_planner import RecordingPreparationFacts


class SourceRole(str, Enum):
    METADATA = "metadata"
    ROS_DATABASE = "ros_database"
    TOPDOWN_VIDEO = "topdown_video"
    TOPDOWN_TIMESTAMPS = "topdown_timestamps"


class SourceCondition(str, Enum):
    PRESENT = "present"
    READABLE = "readable"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    DAMAGED = "damaged"
    UNINSPECTABLE = "uninspectable"


class RosHealth(str, Enum):
    READABLE = "readable"
    DAMAGED = "damaged"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    UNINSPECTABLE = "uninspectable"


@dataclass(frozen=True)
class SafeDiagnostic:
    code: str
    message: str


@dataclass(frozen=True)
class SourceComponentResult:
    role: SourceRole
    condition: SourceCondition
    relative_path: str | None = None
    size_bytes: int | None = None
    mtime_ns: int | None = None
    diagnostic: SafeDiagnostic | None = None
    revision_facts: tuple[tuple[str, int | str], ...] = ()

    @property
    def display_name(self) -> str | None:
        if self.relative_path is None:
            return None
        return self.relative_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class RecordingScanResult:
    archive_relative_path: str
    display_name: str
    start_time_ns: int | None
    duration_ns: int | None
    total_source_size_bytes: int | None
    storage_format: str | None
    metadata_version: int | None
    message_count: int | None
    topic_count: int | None
    ros_health: RosHealth
    diagnostic: SafeDiagnostic | None
    source_revision: str
    components: tuple[SourceComponentResult, ...]
    preparation_facts: RecordingPreparationFacts | None = field(
        default=None,
        compare=False,
        repr=False,
    )


@dataclass(frozen=True)
class ScanSnapshot:
    recordings: tuple[RecordingScanResult, ...]
    duration_ms: int


class RootScanError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.diagnostic = SafeDiagnostic(code=code, message=message)
