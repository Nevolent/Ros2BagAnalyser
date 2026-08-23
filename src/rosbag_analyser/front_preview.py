from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat

import av

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
from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    FRONT_PREVIEW_KIND,
    JobRecord,
    ProcessingComponent,
    ProcessingRepository,
    ProcessingSourceRecord,
)


PROCESSOR_VERSION = "front-preview-v2"
FRONT_TIMING_POLICY = "capture_header_affine_to_record_span_v2"
FRONT_TIMESTAMP_PROVENANCE = "ros_image_header_affine_to_record_span"
IMAGE_MESSAGE_TYPE = "sensor_msgs/msg/Image"
CDR_SERIALIZATION = "cdr"


@dataclass(frozen=True)
class FrontSourceDescriptor:
    recording_id: int
    archive_relative_path: str
    metadata_path: Path
    database_path: Path
    metadata_identity: SourceFileIdentity
    database_identity: SourceFileIdentity
    bag_start_ns: int
    bag_duration_ns: int
    topic: TopicFact
    cache_identity: str


@dataclass(frozen=True)
class SourceResolution:
    recording_exists: bool
    descriptor: FrontSourceDescriptor | None = None
    diagnostic: SafeDiagnostic | None = None
    duration_ns: int | None = None


@dataclass(frozen=True)
class PreviewDisplay:
    recording_exists: bool
    state: str
    duration_ns: int | None
    diagnostic: SafeDiagnostic | None = None
    artifact: ArtifactRecord | None = None


class FrontSourceResolver:
    def __init__(
        self,
        archive_root: Path,
        repository: ProcessingRepository,
        topic_name: str,
        profile: PreviewProfile,
        encoder_identity: str,
    ) -> None:
        self.archive_root = archive_root
        self.repository = repository
        self.topic_name = topic_name
        self.profile = profile
        self.encoder_identity = encoder_identity

    def resolve(self, recording_id: int) -> SourceResolution:
        record = self.repository.get_source(recording_id)
        if record is None:
            return SourceResolution(recording_exists=False)
        if record.duration_ns is None or record.start_time_ns is None:
            return self._unavailable(
                record,
                "bag_timing_unavailable",
                "The recording has no trustworthy bag timing.",
            )
        if record.ros_health != "readable":
            return self._unavailable(
                record,
                "ros_source_unavailable",
                "The ROS recording is not readable enough to generate a preview.",
            )
        if record.metadata is None or record.metadata.condition != "readable":
            return self._unavailable(
                record,
                "metadata_unavailable",
                "The recording metadata is unavailable for preview generation.",
            )
        if record.database is None or record.database.condition != "readable":
            return self._unavailable(
                record,
                "database_unavailable",
                "The ROS database is unavailable for preview generation.",
            )

        try:
            metadata_path, metadata_identity = self._resolve_component(record.metadata)
            database_path, database_identity = self._resolve_component(record.database)
            metadata = parse_metadata_file(
                metadata_path, expected_identity=metadata_identity
            )
            if metadata.start_time_ns != record.start_time_ns:
                return self._unavailable(
                    record,
                    "catalog_source_changed",
                    "The recording changed after its last scan. Rescan before processing.",
                )
            if metadata.duration_ns != record.duration_ns:
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
                    "front_topic_unavailable",
                    "The configured front-camera topic is unavailable.",
                )
            topic = matches[0]
            if topic.message_type != IMAGE_MESSAGE_TYPE:
                return self._unavailable(
                    record,
                    "front_topic_type_unsupported",
                    "The configured front-camera topic is not a standard image stream.",
                )
            if topic.serialization_format != CDR_SERIALIZATION:
                return self._unavailable(
                    record,
                    "front_serialization_unsupported",
                    "The front-camera serialization format is unsupported.",
                )
            if topic.message_count <= 0:
                return self._unavailable(
                    record,
                    "front_topic_empty",
                    "The configured front-camera topic contains no frames.",
                )
        except (OSError, MetadataError, UnsafeSourcePath, ValueError, IndexError):
            return self._unavailable(
                record,
                "front_source_uninspectable",
                "The front-camera source could not be resolved safely.",
            )

        identity = _cache_identity(
            record,
            metadata_identity,
            database_identity,
            topic,
            self.topic_name,
            self.profile,
            self.encoder_identity,
        )
        return SourceResolution(
            recording_exists=True,
            descriptor=FrontSourceDescriptor(
                recording_id=record.id,
                archive_relative_path=record.archive_relative_path,
                metadata_path=metadata_path,
                database_path=database_path,
                metadata_identity=metadata_identity,
                database_identity=database_identity,
                bag_start_ns=record.start_time_ns,
                bag_duration_ns=record.duration_ns,
                topic=topic,
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
    ) -> SourceResolution:
        return SourceResolution(
            recording_exists=True,
            diagnostic=SafeDiagnostic(code, message),
            duration_ns=record.duration_ns,
        )


class FrontPreviewService:
    def __init__(
        self,
        resolver: FrontSourceResolver,
        repository: ProcessingRepository,
        artifact_store: ArtifactStore,
    ) -> None:
        self.resolver = resolver
        self.repository = repository
        self.artifact_store = artifact_store

    def get_state(self, recording_id: int) -> PreviewDisplay:
        resolution = self.resolver.resolve(recording_id)
        return self._display_for_resolution(resolution, request_if_needed=False)

    def request(self, recording_id: int) -> PreviewDisplay:
        resolution = self.resolver.resolve(recording_id)
        return self._display_for_resolution(resolution, request_if_needed=True)

    def _display_for_resolution(
        self, resolution: SourceResolution, *, request_if_needed: bool
    ) -> PreviewDisplay:
        if not resolution.recording_exists:
            return PreviewDisplay(False, "not_found", None)
        if resolution.descriptor is None:
            return PreviewDisplay(
                True,
                "unavailable",
                resolution.duration_ns,
                diagnostic=resolution.diagnostic,
            )
        descriptor = resolution.descriptor
        current = self.repository.get_current_state(
            descriptor.recording_id, FRONT_PREVIEW_KIND, descriptor.cache_identity
        )
        artifact = current.artifact
        invalid_artifact_id: int | None = None
        if artifact is not None:
            try:
                self.artifact_store.validate_media(
                    artifact.output_relative_path,
                    artifact.size_bytes,
                    artifact.cache_identity,
                    artifact.manifest,
                )
            except ArtifactStoreError as error:
                if not request_if_needed:
                    return PreviewDisplay(
                        True,
                        "failed",
                        descriptor.bag_duration_ns,
                        diagnostic=SafeDiagnostic(error.code, error.safe_message),
                    )
                invalid_artifact_id = artifact.id
            else:
                return PreviewDisplay(
                    True, "ready", descriptor.bag_duration_ns, artifact=artifact
                )
        active = current.active_job
        if active is not None:
            return PreviewDisplay(
                True,
                "queued" if active.state == "queued" else "processing",
                descriptor.bag_duration_ns,
            )
        failed = current.latest_failed_job
        if not request_if_needed and failed is not None:
            return PreviewDisplay(
                True,
                "failed",
                descriptor.bag_duration_ns,
                diagnostic=SafeDiagnostic(
                    failed.error_code or "preview_failed",
                    failed.error_message or "Preview generation failed.",
                ),
            )
        if not request_if_needed:
            return PreviewDisplay(
                True, "not_requested", descriptor.bag_duration_ns
            )
        outcome = self.repository.request_job(
            descriptor.recording_id,
            FRONT_PREVIEW_KIND,
            descriptor.cache_identity,
            invalid_artifact_id=invalid_artifact_id,
        )
        if outcome.artifact is not None:
            try:
                self.artifact_store.validate_media(
                    outcome.artifact.output_relative_path,
                    outcome.artifact.size_bytes,
                    outcome.artifact.cache_identity,
                    outcome.artifact.manifest,
                )
            except ArtifactStoreError as error:
                return PreviewDisplay(
                    True,
                    "failed",
                    descriptor.bag_duration_ns,
                    diagnostic=SafeDiagnostic(error.code, error.safe_message),
                )
            return PreviewDisplay(
                True,
                "ready",
                descriptor.bag_duration_ns,
                artifact=outcome.artifact,
            )
        if outcome.job is None:
            raise RuntimeError("The preview request returned no job or artifact.")
        return _display_for_job(outcome.job, descriptor.bag_duration_ns)

    def resolve_media(
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
            opened = self.artifact_store.open_media(
                state.artifact.output_relative_path,
                state.artifact.size_bytes,
                state.artifact.cache_identity,
                state.artifact.manifest,
            )
        except ArtifactStoreError:
            return None
        return opened, state.artifact


def encoder_identity() -> str:
    versions = ",".join(
        f"{name}={'.'.join(str(part) for part in version)}"
        for name, version in sorted(av.library_versions.items())
    )
    return f"pyav={av.__version__};{versions}"


def _display_for_job(job: JobRecord, duration_ns: int) -> PreviewDisplay:
    return PreviewDisplay(
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
    profile: PreviewProfile,
    media_encoder_identity: str,
) -> str:
    document = {
        "artifact_kind": FRONT_PREVIEW_KIND,
        "processor_version": PROCESSOR_VERSION,
        "timing_policy": FRONT_TIMING_POLICY,
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
        "profile": profile.identity_values(),
        "encoder": media_encoder_identity,
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
