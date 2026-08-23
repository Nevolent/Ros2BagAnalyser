from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from rosbag_analyser.catalog.metadata import ParsedMetadata, TopicFact
from rosbag_analyser.catalog.paths import SourceFileIdentity
from rosbag_analyser.catalog.types import (
    RecordingScanResult,
    SafeDiagnostic,
    SourceComponentResult,
    SourceCondition,
    SourceRole,
)
from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.front_preview import (
    CDR_SERIALIZATION,
    FRONT_TIMING_POLICY,
    IMAGE_MESSAGE_TYPE,
    PROCESSOR_VERSION as FRONT_PROCESSOR_VERSION,
    _cache_identity as front_cache_identity,
)
from rosbag_analyser.imu_series import (
    DUPLICATE_TIMESTAMP_POLICY,
    IMU_MESSAGE_TYPE,
    IMU_SERIES_DEFINITIONS,
    NON_FINITE_POLICY,
    PROCESSOR_VERSION as IMU_PROCESSOR_VERSION,
    SERIES_SCHEMA_VERSION,
    _cache_identity as imu_cache_identity,
)
from rosbag_analyser.persistence.processing_repository import (
    FRONT_PREVIEW_KIND,
    IMU_SERIES_KIND,
    TOPDOWN_PREVIEW_KIND,
    ProcessingSourceRecord,
)
from rosbag_analyser.topdown_preview import (
    PROCESSOR_VERSION as TOPDOWN_PROCESSOR_VERSION,
    _cache_identity as topdown_cache_identity,
)


PREPARATION_KINDS = (
    FRONT_PREVIEW_KIND,
    TOPDOWN_PREVIEW_KIND,
    IMU_SERIES_KIND,
)


@dataclass(frozen=True)
class RecordingPreparationFacts:
    metadata: ParsedMetadata | None
    metadata_identity: SourceFileIdentity | None
    database_identity: SourceFileIdentity | None
    video_identity: SourceFileIdentity | None
    timestamps_identity: SourceFileIdentity | None


@dataclass(frozen=True)
class PreparationTargetPlan:
    kind: str
    planner_identity: str
    target_state: str
    cache_identity: str | None
    diagnostic: SafeDiagnostic | None
    work_units: int | None


class PreparationPlanner:
    """Build the three current output targets from one parsed scan result."""

    def __init__(
        self,
        *,
        front_topic: str,
        imu_topic: str,
        imu_component: str,
        profile: PreviewProfile,
        encoder_identity: str,
    ) -> None:
        self.front_topic = front_topic
        self.imu_topic = imu_topic
        self.imu_component = imu_component
        self.profile = profile
        self.encoder_identity = encoder_identity
        self._planner_identities = {
            FRONT_PREVIEW_KIND: _digest(
                {
                    "kind": FRONT_PREVIEW_KIND,
                    "processor_version": FRONT_PROCESSOR_VERSION,
                    "timing_policy": FRONT_TIMING_POLICY,
                    "topic": front_topic,
                    "message_type": IMAGE_MESSAGE_TYPE,
                    "serialization": CDR_SERIALIZATION,
                    "profile": profile.identity_values(),
                    "encoder": encoder_identity,
                }
            ),
            TOPDOWN_PREVIEW_KIND: _digest(
                {
                    "kind": TOPDOWN_PREVIEW_KIND,
                    "processor_version": TOPDOWN_PROCESSOR_VERSION,
                    "timestamp_policy": "csv_unix_timestamp",
                    "profile": profile.identity_values(),
                    "encoder": encoder_identity,
                }
            ),
            IMU_SERIES_KIND: _digest(
                {
                    "kind": IMU_SERIES_KIND,
                    "processor_version": IMU_PROCESSOR_VERSION,
                    "series_schema_version": SERIES_SCHEMA_VERSION,
                    "topic": imu_topic,
                    "message_type": IMU_MESSAGE_TYPE,
                    "serialization": CDR_SERIALIZATION,
                    "default_component": imu_component,
                    "series": [
                        definition.identity_values()
                        for definition in IMU_SERIES_DEFINITIONS
                    ],
                    "non_finite_policy": NON_FINITE_POLICY,
                    "duplicate_timestamp_policy": DUPLICATE_TIMESTAMP_POLICY,
                    "reduction": "none",
                }
            ),
        }

    def planner_identity(self, kind: str) -> str:
        return self._planner_identities[kind]

    @property
    def planner_identities(self) -> dict[str, str]:
        return dict(self._planner_identities)

    def plan_recording(
        self,
        recording_id: int,
        recording: RecordingScanResult,
        cache_identity_recording_id: int | None = None,
        cache_identity_relative_path: str | None = None,
    ) -> tuple[PreparationTargetPlan, ...]:
        facts = recording.preparation_facts
        if facts is None:
            return tuple(
                self._unavailable(
                    kind,
                    "preparation_scan_facts_unavailable",
                    "Preparation targets require another explicit catalog rescan.",
                )
                for kind in PREPARATION_KINDS
            )

        source = ProcessingSourceRecord(
            id=recording_id,
            archive_relative_path=recording.archive_relative_path,
            start_time_ns=recording.start_time_ns,
            duration_ns=recording.duration_ns,
            ros_health=recording.ros_health.value,
            metadata=None,
            database=None,
            cache_identity_recording_id=cache_identity_recording_id,
            cache_identity_relative_path=cache_identity_relative_path,
        )
        return (
            self._plan_front(source, recording, facts),
            self._plan_topdown(source, recording, facts),
            self._plan_imu(source, recording, facts),
        )

    def unavailable_targets(
        self,
        code: str,
        message: str,
    ) -> tuple[PreparationTargetPlan, ...]:
        return tuple(self._unavailable(kind, code, message) for kind in PREPARATION_KINDS)

    def _plan_front(
        self,
        source: ProcessingSourceRecord,
        recording: RecordingScanResult,
        facts: RecordingPreparationFacts,
    ) -> PreparationTargetPlan:
        common = self._ros_prerequisite(recording, facts)
        if common is not None:
            return self._unavailable(FRONT_PREVIEW_KIND, common.code, common.message)
        topic = _one_topic(facts.metadata, self.front_topic)
        diagnostic = _topic_diagnostic(
            topic,
            expected_type=IMAGE_MESSAGE_TYPE,
            missing_code="front_topic_unavailable",
            type_code="front_topic_type_unsupported",
            serialization_code="front_serialization_unsupported",
            empty_code="front_topic_empty",
            label="front-camera",
        )
        if diagnostic is not None:
            return self._unavailable(
                FRONT_PREVIEW_KIND, diagnostic.code, diagnostic.message
            )
        assert topic is not None
        assert facts.metadata_identity is not None
        assert facts.database_identity is not None
        cache_identity = front_cache_identity(
            source,
            facts.metadata_identity,
            facts.database_identity,
            topic,
            self.front_topic,
            self.profile,
            self.encoder_identity,
        )
        return self._available(
            FRONT_PREVIEW_KIND,
            cache_identity,
            facts.database_identity.size_bytes,
        )

    def _plan_topdown(
        self,
        source: ProcessingSourceRecord,
        recording: RecordingScanResult,
        facts: RecordingPreparationFacts,
    ) -> PreparationTargetPlan:
        common = self._ros_prerequisite(recording, facts)
        if common is not None:
            return self._unavailable(TOPDOWN_PREVIEW_KIND, common.code, common.message)
        components = _components_by_role(recording)
        video = components.get(SourceRole.TOPDOWN_VIDEO)
        timestamps = components.get(SourceRole.TOPDOWN_TIMESTAMPS)
        if (
            video is None
            or video.condition is not SourceCondition.PRESENT
            or facts.video_identity is None
        ):
            return self._unavailable(
                TOPDOWN_PREVIEW_KIND,
                "topdown_video_unavailable",
                "The top-down video companion is unavailable.",
            )
        if (
            timestamps is None
            or timestamps.condition is not SourceCondition.PRESENT
            or facts.timestamps_identity is None
        ):
            return self._unavailable(
                TOPDOWN_PREVIEW_KIND,
                "topdown_timestamps_unavailable",
                "The top-down timestamp companion is unavailable.",
            )
        assert facts.metadata_identity is not None
        cache_identity = topdown_cache_identity(
            source,
            facts.metadata_identity,
            facts.video_identity,
            facts.timestamps_identity,
            self.profile,
            self.encoder_identity,
        )
        return self._available(
            TOPDOWN_PREVIEW_KIND,
            cache_identity,
            facts.video_identity.size_bytes,
        )

    def _plan_imu(
        self,
        source: ProcessingSourceRecord,
        recording: RecordingScanResult,
        facts: RecordingPreparationFacts,
    ) -> PreparationTargetPlan:
        common = self._ros_prerequisite(recording, facts)
        if common is not None:
            return self._unavailable(IMU_SERIES_KIND, common.code, common.message)
        topic = _one_topic(facts.metadata, self.imu_topic)
        diagnostic = _topic_diagnostic(
            topic,
            expected_type=IMU_MESSAGE_TYPE,
            missing_code="imu_topic_unavailable",
            type_code="imu_topic_type_unsupported",
            serialization_code="imu_serialization_unsupported",
            empty_code="imu_topic_empty",
            label="IMU",
        )
        if diagnostic is not None:
            return self._unavailable(IMU_SERIES_KIND, diagnostic.code, diagnostic.message)
        assert topic is not None
        assert facts.metadata_identity is not None
        assert facts.database_identity is not None
        cache_identity = imu_cache_identity(
            source,
            facts.metadata_identity,
            facts.database_identity,
            topic,
            self.imu_topic,
            self.imu_component,
        )
        return self._available(
            IMU_SERIES_KIND,
            cache_identity,
            facts.database_identity.size_bytes,
        )

    @staticmethod
    def _ros_prerequisite(
        recording: RecordingScanResult,
        facts: RecordingPreparationFacts,
    ) -> SafeDiagnostic | None:
        if recording.start_time_ns is None or recording.duration_ns is None:
            return SafeDiagnostic(
                "bag_timing_unavailable",
                "The recording has no trustworthy ROS bag timing.",
            )
        if recording.ros_health.value != "readable":
            return recording.diagnostic or SafeDiagnostic(
                "ros_source_unavailable",
                "The ROS recording is unavailable for preparation.",
            )
        if (
            facts.metadata is None
            or facts.metadata_identity is None
            or facts.database_identity is None
        ):
            return SafeDiagnostic(
                "ros_source_unavailable",
                "The ROS recording prerequisites are unavailable.",
            )
        return None

    def _available(
        self,
        kind: str,
        cache_identity: str,
        work_units: int,
    ) -> PreparationTargetPlan:
        if work_units <= 0:
            return self._unavailable(
                kind,
                "source_work_units_unavailable",
                "The source size required for preparation is unavailable.",
            )
        return PreparationTargetPlan(
            kind=kind,
            planner_identity=self.planner_identity(kind),
            target_state="available",
            cache_identity=cache_identity,
            diagnostic=None,
            work_units=work_units,
        )

    def _unavailable(
        self,
        kind: str,
        code: str,
        message: str,
    ) -> PreparationTargetPlan:
        return PreparationTargetPlan(
            kind=kind,
            planner_identity=self.planner_identity(kind),
            target_state="unavailable",
            cache_identity=None,
            diagnostic=SafeDiagnostic(code, message),
            work_units=None,
        )


def _one_topic(metadata: ParsedMetadata | None, name: str) -> TopicFact | None:
    if metadata is None:
        return None
    matches = [topic for topic in metadata.topics if topic.name == name]
    return matches[0] if len(matches) == 1 else None


def _topic_diagnostic(
    topic: TopicFact | None,
    *,
    expected_type: str,
    missing_code: str,
    type_code: str,
    serialization_code: str,
    empty_code: str,
    label: str,
) -> SafeDiagnostic | None:
    if topic is None:
        return SafeDiagnostic(missing_code, f"The configured {label} topic is unavailable.")
    if topic.message_type != expected_type:
        return SafeDiagnostic(type_code, f"The configured {label} topic type is unsupported.")
    if topic.serialization_format != CDR_SERIALIZATION:
        return SafeDiagnostic(
            serialization_code,
            f"The configured {label} serialization format is unsupported.",
        )
    if topic.message_count <= 0:
        return SafeDiagnostic(empty_code, f"The configured {label} topic is empty.")
    return None


def _components_by_role(
    recording: RecordingScanResult,
) -> dict[SourceRole, SourceComponentResult]:
    return {component.role: component for component in recording.components}


def _digest(document: dict[str, object]) -> str:
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "PREPARATION_KINDS",
    "PreparationPlanner",
    "PreparationTargetPlan",
    "RecordingPreparationFacts",
]
