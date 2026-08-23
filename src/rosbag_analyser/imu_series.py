from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat

from rosbag_analyser.artifact_store import (
    ArtifactStore,
    ArtifactStoreError,
    OpenedMedia,
)
from rosbag_analyser.catalog.metadata import MetadataError, TopicFact, parse_metadata_file
from rosbag_analyser.catalog.paths import (
    SourceFileIdentity,
    UnsafeSourcePath,
    filesystem_text_from_safe,
    safe_filesystem_text,
    source_file_identity,
)
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    IMU_SERIES_KIND,
    JobRecord,
    ProcessingComponent,
    ProcessingRepository,
    ProcessingSourceRecord,
)


PROCESSOR_VERSION = "imu-series-v2"
SERIES_SCHEMA_VERSION = 2
IMU_MESSAGE_TYPE = "sensor_msgs/msg/Imu"
CDR_SERIALIZATION = "cdr"
IMU_COMPONENT = "angular_velocity.z"
IMU_DISPLAY_LABEL = "IMU angular_velocity.z (rad/s)"
IMU_UNITS = "rad/s"
NON_FINITE_POLICY = "json-null"
DUPLICATE_TIMESTAMP_POLICY = "preserve-database-order"


@dataclass(frozen=True)
class ImuSeriesDefinition:
    id: str
    component: str
    display_label: str
    units: str
    column_index: int

    def identity_values(self) -> dict[str, int | str]:
        return {
            "id": self.id,
            "component": self.component,
            "display_label": self.display_label,
            "units": self.units,
            "column_index": self.column_index,
        }


IMU_SERIES_DEFINITIONS = (
    ImuSeriesDefinition(
        "angular_velocity_x",
        "angular_velocity.x",
        "IMU angular_velocity.x (rad/s)",
        "rad/s",
        1,
    ),
    ImuSeriesDefinition(
        "angular_velocity_y",
        "angular_velocity.y",
        "IMU angular_velocity.y (rad/s)",
        "rad/s",
        2,
    ),
    ImuSeriesDefinition(
        "angular_velocity_z",
        "angular_velocity.z",
        IMU_DISPLAY_LABEL,
        IMU_UNITS,
        3,
    ),
    ImuSeriesDefinition(
        "linear_acceleration_x",
        "linear_acceleration.x",
        "IMU linear_acceleration.x (m/s²)",
        "m/s²",
        4,
    ),
    ImuSeriesDefinition(
        "linear_acceleration_y",
        "linear_acceleration.y",
        "IMU linear_acceleration.y (m/s²)",
        "m/s²",
        5,
    ),
    ImuSeriesDefinition(
        "linear_acceleration_z",
        "linear_acceleration.z",
        "IMU linear_acceleration.z (m/s²)",
        "m/s²",
        6,
    ),
)
IMU_SERIES_BY_COMPONENT = {
    definition.component: definition for definition in IMU_SERIES_DEFINITIONS
}


@dataclass(frozen=True)
class ImuSourceDescriptor:
    recording_id: int
    archive_relative_path: str
    metadata_path: Path
    database_path: Path
    metadata_identity: SourceFileIdentity
    database_identity: SourceFileIdentity
    bag_start_ns: int
    bag_duration_ns: int
    topic: TopicFact
    component: str
    cache_identity: str


@dataclass(frozen=True)
class ImuSourceResolution:
    recording_exists: bool
    descriptor: ImuSourceDescriptor | None = None
    diagnostic: SafeDiagnostic | None = None
    duration_ns: int | None = None


@dataclass(frozen=True)
class ImuSeriesDisplay:
    recording_exists: bool
    state: str
    duration_ns: int | None
    diagnostic: SafeDiagnostic | None = None
    artifact: ArtifactRecord | None = None


class ImuSourceResolver:
    def __init__(
        self,
        archive_root: Path,
        repository: ProcessingRepository,
        topic_name: str,
        component: str,
    ) -> None:
        self.archive_root = archive_root
        self.repository = repository
        self.topic_name = topic_name
        self.component = component

    def resolve(self, recording_id: int) -> ImuSourceResolution:
        record = self.repository.get_source(recording_id)
        if record is None:
            return ImuSourceResolution(recording_exists=False)
        if self.component not in IMU_SERIES_BY_COMPONENT:
            return self._unavailable(
                record,
                "imu_component_unsupported",
                "The configured IMU component is unsupported.",
            )
        if record.duration_ns is None or record.start_time_ns is None:
            return self._unavailable(
                record,
                "bag_timing_unavailable",
                "The recording has no trustworthy bag timing for IMU alignment.",
            )
        if record.ros_health != "readable":
            return self._unavailable(
                record,
                "imu_ros_source_unavailable",
                "The ROS recording is not readable enough to extract IMU data.",
            )
        if record.metadata is None or record.metadata.condition != "readable":
            return self._unavailable(
                record,
                "imu_metadata_unavailable",
                "The recording metadata is unavailable for IMU extraction.",
            )
        if record.database is None or record.database.condition != "readable":
            return self._unavailable(
                record,
                "imu_database_unavailable",
                "The ROS database is unavailable for IMU extraction.",
            )

        try:
            metadata_path, metadata_identity = self._resolve_component(record.metadata)
            database_path, database_identity = self._resolve_component(record.database)
            metadata = parse_metadata_file(
                metadata_path, expected_identity=metadata_identity
            )
            if (
                metadata.start_time_ns != record.start_time_ns
                or metadata.duration_ns != record.duration_ns
            ):
                return self._unavailable(
                    record,
                    "catalog_source_changed",
                    "The recording changed after its last scan. Rescan before processing.",
                )
            declared_database = _resolve_declared_database(
                self.archive_root,
                record.archive_relative_path,
                metadata.relative_file_paths[0],
            )
            if declared_database != database_path:
                return self._unavailable(
                    record,
                    "catalog_source_changed",
                    "The recording changed after its last scan. Rescan before processing.",
                )
            matches = [topic for topic in metadata.topics if topic.name == self.topic_name]
            if len(matches) != 1:
                return self._unavailable(
                    record,
                    "imu_topic_unavailable",
                    "The configured IMU topic is unavailable.",
                )
            topic = matches[0]
            if topic.message_type != IMU_MESSAGE_TYPE:
                return self._unavailable(
                    record,
                    "imu_topic_type_unsupported",
                    "The configured IMU topic is not a standard IMU stream.",
                )
            if topic.serialization_format != CDR_SERIALIZATION:
                return self._unavailable(
                    record,
                    "imu_serialization_unsupported",
                    "The IMU serialization format is unsupported.",
                )
            if topic.message_count <= 0:
                return self._unavailable(
                    record,
                    "imu_topic_empty",
                    "The configured IMU topic contains no samples.",
                )
        except (OSError, MetadataError, UnsafeSourcePath, ValueError, IndexError):
            return self._unavailable(
                record,
                "imu_source_uninspectable",
                "The IMU source could not be resolved safely.",
            )

        identity = _cache_identity(
            record,
            metadata_identity,
            database_identity,
            topic,
            self.topic_name,
            self.component,
        )
        return ImuSourceResolution(
            recording_exists=True,
            descriptor=ImuSourceDescriptor(
                recording_id=record.id,
                archive_relative_path=record.archive_relative_path,
                metadata_path=metadata_path,
                database_path=database_path,
                metadata_identity=metadata_identity,
                database_identity=database_identity,
                bag_start_ns=record.start_time_ns,
                bag_duration_ns=record.duration_ns,
                topic=topic,
                component=self.component,
                cache_identity=identity,
            ),
            duration_ns=record.duration_ns,
        )

    def _resolve_component(
        self, component: ProcessingComponent
    ) -> tuple[Path, SourceFileIdentity]:
        if (
            component.relative_path is None
            or component.size_bytes is None
            or component.mtime_ns is None
        ):
            raise ValueError("Component facts are incomplete.")
        path = _resolve_catalog_path(self.archive_root, component.relative_path)
        details = path.stat(follow_symlinks=False)
        identity = source_file_identity(details)
        if (
            not stat.S_ISREG(identity.mode)
            or identity.size_bytes != component.size_bytes
            or identity.mtime_ns != component.mtime_ns
        ):
            raise ValueError("Component changed after the catalog scan.")
        return path, identity

    @staticmethod
    def _unavailable(
        record: ProcessingSourceRecord, code: str, message: str
    ) -> ImuSourceResolution:
        return ImuSourceResolution(
            recording_exists=True,
            diagnostic=SafeDiagnostic(code, message),
            duration_ns=record.duration_ns,
        )


class ImuSeriesService:
    def __init__(
        self,
        resolver: ImuSourceResolver,
        repository: ProcessingRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self.resolver = resolver
        self.repository = repository
        self.artifact_store = artifact_store

    def get_state(self, recording_id: int) -> ImuSeriesDisplay:
        return self._display_for_resolution(
            self.resolver.resolve(recording_id), request_if_needed=False
        )

    def request(self, recording_id: int) -> ImuSeriesDisplay:
        return self._display_for_resolution(
            self.resolver.resolve(recording_id), request_if_needed=True
        )

    def _display_for_resolution(
        self,
        resolution: ImuSourceResolution,
        *,
        request_if_needed: bool,
    ) -> ImuSeriesDisplay:
        if not resolution.recording_exists:
            return ImuSeriesDisplay(False, "not_found", None)
        if resolution.descriptor is None:
            return ImuSeriesDisplay(
                True,
                "unavailable",
                resolution.duration_ns,
                diagnostic=resolution.diagnostic,
            )
        descriptor = resolution.descriptor
        current = self.repository.get_current_state(
            descriptor.recording_id,
            IMU_SERIES_KIND,
            descriptor.cache_identity,
        )
        artifact = current.artifact
        invalid_artifact_id: int | None = None
        if artifact is not None:
            try:
                self.artifact_store.validate_series_artifact(
                    artifact.output_relative_path,
                    artifact.size_bytes,
                    artifact.cache_identity,
                    artifact.manifest,
                )
            except ArtifactStoreError as error:
                if not request_if_needed:
                    return ImuSeriesDisplay(
                        True,
                        "failed",
                        descriptor.bag_duration_ns,
                        diagnostic=SafeDiagnostic(error.code, error.safe_message),
                    )
                invalid_artifact_id = artifact.id
            else:
                return ImuSeriesDisplay(
                    True, "ready", descriptor.bag_duration_ns, artifact=artifact
                )
        if current.active_job is not None:
            return _display_for_job(current.active_job, descriptor.bag_duration_ns)
        if not request_if_needed and current.latest_failed_job is not None:
            failed = current.latest_failed_job
            return ImuSeriesDisplay(
                True,
                "failed",
                descriptor.bag_duration_ns,
                diagnostic=SafeDiagnostic(
                    failed.error_code or "imu_series_failed",
                    failed.error_message or "IMU series generation failed.",
                ),
            )
        if not request_if_needed:
            return ImuSeriesDisplay(True, "not_requested", descriptor.bag_duration_ns)
        outcome = self.repository.request_job(
            descriptor.recording_id,
            IMU_SERIES_KIND,
            descriptor.cache_identity,
            invalid_artifact_id=invalid_artifact_id,
        )
        if outcome.artifact is not None:
            try:
                self.artifact_store.validate_series_artifact(
                    outcome.artifact.output_relative_path,
                    outcome.artifact.size_bytes,
                    outcome.artifact.cache_identity,
                    outcome.artifact.manifest,
                )
            except ArtifactStoreError as error:
                return ImuSeriesDisplay(
                    True,
                    "failed",
                    descriptor.bag_duration_ns,
                    diagnostic=SafeDiagnostic(error.code, error.safe_message),
                )
            return ImuSeriesDisplay(
                True,
                "ready",
                descriptor.bag_duration_ns,
                artifact=outcome.artifact,
            )
        if outcome.job is None:
            raise RuntimeError("The IMU request returned no job or artifact.")
        return _display_for_job(outcome.job, descriptor.bag_duration_ns)

    def resolve_series(
        self, recording_id: int, artifact_id: int
    ) -> tuple[OpenedMedia, ArtifactRecord] | None:
        state = self.get_state(recording_id)
        if (
            state.state != "ready"
            or state.artifact is None
            or state.artifact.id != artifact_id
        ):
            return None
        try:
            opened = self.artifact_store.open_series(
                state.artifact.output_relative_path,
                state.artifact.size_bytes,
                state.artifact.cache_identity,
                state.artifact.manifest,
            )
        except ArtifactStoreError:
            return None
        return opened, state.artifact


def _display_for_job(job: JobRecord, duration_ns: int) -> ImuSeriesDisplay:
    return ImuSeriesDisplay(
        True,
        "queued" if job.state == "queued" else "processing",
        duration_ns,
    )


def _cache_identity(
    record: ProcessingSourceRecord,
    metadata_identity: SourceFileIdentity,
    database_identity: SourceFileIdentity,
    topic: TopicFact,
    configured_topic: str,
    component: str,
) -> str:
    document = {
        "artifact_kind": IMU_SERIES_KIND,
        "processor_version": PROCESSOR_VERSION,
        "series_schema_version": SERIES_SCHEMA_VERSION,
        "recording": {
            "id": record.identity_recording_id,
            "archive_relative_path": record.identity_relative_path,
            "bag_start_ns": record.start_time_ns,
            "bag_duration_ns": record.duration_ns,
        },
        "metadata": _identity_values(metadata_identity),
        "database": _identity_values(database_identity),
        "topic": {
            "configured_name": configured_topic,
            "name": topic.name,
            "message_type": topic.message_type,
            "serialization_format": topic.serialization_format,
            "message_count": topic.message_count,
        },
        "default_component": component,
        "series": [
            definition.identity_values() for definition in IMU_SERIES_DEFINITIONS
        ],
        "non_finite_policy": NON_FINITE_POLICY,
        "duplicate_timestamp_policy": DUPLICATE_TIMESTAMP_POLICY,
        "reduction": "none",
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _identity_values(identity: SourceFileIdentity) -> dict[str, int]:
    return {
        "device_id": identity.device_id,
        "inode": identity.inode,
        "mode": identity.mode,
        "size_bytes": identity.size_bytes,
        "mtime_ns": identity.mtime_ns,
    }


def _resolve_declared_database(
    archive_root: Path, archive_relative_recording: str, declared_path: str
) -> Path:
    recording_root = _resolve_catalog_path(archive_root, archive_relative_recording)
    raw_parts = declared_path.split("/")
    if (
        not declared_path
        or "\\" in declared_path
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise ValueError("Declared source path is unsafe.")
    return _resolve_catalog_path(
        archive_root,
        (
            PurePosixPath(archive_relative_recording)
            / PurePosixPath(safe_filesystem_text(declared_path))
        ).as_posix(),
        required_parent=recording_root,
    )


def _resolve_catalog_path(
    archive_root: Path, relative_path: str, *, required_parent: Path | None = None
) -> Path:
    decoded_relative_path = filesystem_text_from_safe(relative_path)
    relative = PurePosixPath(decoded_relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or "\\" in decoded_relative_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("Catalog source path is unsafe.")
    current = archive_root
    for part in relative.parts:
        current = current / part
        details = current.lstat()
        if stat.S_ISLNK(details.st_mode):
            raise ValueError("Source symlinks are unsupported.")
    resolved = current.resolve(strict=True)
    if archive_root not in resolved.parents:
        raise ValueError("Catalog source escaped the archive root.")
    if required_parent is not None and required_parent not in resolved.parents:
        raise ValueError("Declared source escaped its recording directory.")
    return resolved
