from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from conftest import metadata_document
from rosbag_analyser.artifact_store import ArtifactStoreError
from rosbag_analyser.imu_series import ImuSeriesService, ImuSourceResolver
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    JobRecord,
    ProcessingComponent,
    ProcessingSourceRecord,
    ProcessingState,
    RequestOutcome,
)


TOPIC = "/sensors/imu"


class FakeRepository:
    def __init__(self, source: ProcessingSourceRecord) -> None:
        self.source = source
        self.artifact: ArtifactRecord | None = None
        self.active_job: JobRecord | None = None
        self.latest_failed_job: JobRecord | None = None
        self.request_count = 0
        self.invalid_artifact_ids: list[int | None] = []

    def get_source(self, recording_id: int) -> ProcessingSourceRecord | None:
        return self.source if recording_id == self.source.id else None

    def get_current_state(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> ProcessingState:
        artifact = self.artifact
        if (
            artifact is not None
            and (
                artifact.recording_id != recording_id
                or artifact.kind != kind
                or artifact.cache_identity != cache_identity
            )
        ):
            artifact = None
        return ProcessingState(
            artifact=artifact,
            active_job=self.active_job,
            latest_failed_job=self.latest_failed_job,
        )

    def request_job(
        self,
        recording_id: int,
        kind: str,
        cache_identity: str,
        *,
        invalid_artifact_id: int | None = None,
    ) -> RequestOutcome:
        self.request_count += 1
        self.invalid_artifact_ids.append(invalid_artifact_id)
        if self.artifact is not None and self.artifact.cache_identity == cache_identity:
            if self.artifact.id != invalid_artifact_id:
                return RequestOutcome(artifact=self.artifact)
            self.artifact = None
        now = datetime.now(timezone.utc)
        self.active_job = JobRecord(
            id=8,
            recording_id=recording_id,
            kind=kind,
            cache_identity=cache_identity,
            state="queued",
            queued_at=now,
            started_at=None,
            finished_at=None,
            error_code=None,
            error_message=None,
        )
        return RequestOutcome(job=self.active_job)


class FakeArtifactStore:
    def validate_series_artifact(self, *args: object) -> None:
        del args


class MissingArtifactStore(FakeArtifactStore):
    def validate_series_artifact(self, *args: object) -> None:
        del args
        raise ArtifactStoreError(
            "artifact_file_missing", "The ready IMU series file is unavailable."
        )


def _write_source(archive: Path) -> tuple[Path, Path]:
    recording = archive / "run"
    recording.mkdir()
    database = recording / "run_0.db3"
    database.write_bytes(b"sqlite-source-identity")
    document = metadata_document("run_0.db3")
    topic = document["rosbag2_bagfile_information"]["topics_with_message_count"][0]
    topic["topic_metadata"].update(
        {"name": TOPIC, "type": "sensor_msgs/msg/Imu"}
    )
    metadata = recording / "metadata.yaml"
    metadata.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return metadata, database


def _source(
    metadata: Path, database: Path, *, health: str = "readable"
) -> ProcessingSourceRecord:
    metadata_stat = metadata.stat()
    database_stat = database.stat()
    return ProcessingSourceRecord(
        id=11,
        archive_relative_path="run",
        start_time_ns=1_700_000_000_000_000_000,
        duration_ns=2_500_000_000,
        ros_health=health,
        metadata=ProcessingComponent(
            "run/metadata.yaml",
            metadata_stat.st_size,
            metadata_stat.st_mtime_ns,
            "readable",
        ),
        database=ProcessingComponent(
            "run/run_0.db3",
            database_stat.st_size,
            database_stat.st_mtime_ns,
            "readable" if health == "readable" else "damaged",
        ),
    )


def _resolver(
    archive: Path, repository: FakeRepository, *, component: str = "angular_velocity.z"
) -> ImuSourceResolver:
    return ImuSourceResolver(
        archive.resolve(),
        repository,  # type: ignore[arg-type]
        TOPIC,
        component,
    )


def _artifact(cache_identity: str) -> ArtifactRecord:
    return ArtifactRecord(
        id=12,
        recording_id=11,
        kind="imu_series",
        cache_identity=cache_identity,
        output_relative_path="rosbag-analyser/artifacts/imu_series/aa/series.json",
        mime_type="application/json",
        size_bytes=100,
        coverage_start_ns=10,
        coverage_end_ns=20,
        manifest={"artifact_kind": "imu_series", "cache_identity": cache_identity},
        created_at=datetime.now(timezone.utc),
    )


def test_cache_identity_reuses_matching_inputs(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))

    first = _resolver(archive, repository).resolve(11)
    repeated = _resolver(archive, repository).resolve(11)
    assert first.descriptor is not None
    assert repeated.descriptor is not None
    assert repeated.descriptor.cache_identity == first.descriptor.cache_identity


def test_missing_or_unsupported_prerequisites_are_unavailable_without_job(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database, health="damaged"))
    service = ImuSeriesService(
        _resolver(archive, repository),
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
    )

    damaged = service.request(11)
    assert damaged.state == "unavailable"
    assert damaged.diagnostic is not None
    assert damaged.diagnostic.code == "imu_ros_source_unavailable"
    assert repository.request_count == 0

    repository.source = replace(
        _source(metadata, database),
        database=None,
    )
    missing = service.request(11)
    assert missing.state == "unavailable"
    assert missing.diagnostic is not None
    assert missing.diagnostic.code == "imu_database_unavailable"
    assert repository.request_count == 0

    document = yaml.safe_load(metadata.read_text())
    topic = document["rosbag2_bagfile_information"]["topics_with_message_count"][0]
    topic["topic_metadata"]["name"] = "/different/imu"
    metadata.write_text(yaml.safe_dump(document, sort_keys=False))
    repository.source = _source(metadata, database)
    missing_topic = service.request(11)
    assert missing_topic.state == "unavailable"
    assert missing_topic.diagnostic is not None
    assert missing_topic.diagnostic.code == "imu_topic_unavailable"
    assert repository.request_count == 0

    topic["topic_metadata"]["name"] = TOPIC
    topic["topic_metadata"]["type"] = "geometry_msgs/msg/Twist"
    metadata.write_text(yaml.safe_dump(document, sort_keys=False))
    repository.source = _source(metadata, database)
    wrong_type = service.request(11)
    assert wrong_type.state == "unavailable"
    assert wrong_type.diagnostic is not None
    assert wrong_type.diagnostic.code == "imu_topic_type_unsupported"
    assert repository.request_count == 0


def test_unsupported_component_is_unavailable_without_a_job(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    service = ImuSeriesService(
        _resolver(archive, repository, component="angular_velocity.x"),
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
    )

    unavailable = service.request(11)

    assert unavailable.state == "unavailable"
    assert unavailable.diagnostic is not None
    assert unavailable.diagnostic.code == "imu_component_unsupported"
    assert repository.request_count == 0


def test_request_queues_then_reuses_ready_artifact(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)
    service = ImuSeriesService(
        resolver,
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
    )

    queued = service.request(11)
    assert queued.state == "queued"
    assert repository.request_count == 1
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    repository.active_job = None
    repository.artifact = _artifact(resolution.descriptor.cache_identity)

    ready = service.request(11)
    assert ready.state == "ready"
    assert ready.artifact == repository.artifact
    assert repository.request_count == 1


def test_invalid_ready_series_requires_explicit_replacement_request(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    repository.artifact = _artifact(resolution.descriptor.cache_identity)
    service = ImuSeriesService(
        resolver,
        repository,  # type: ignore[arg-type]
        MissingArtifactStore(),  # type: ignore[arg-type]
    )

    observed = service.get_state(11)
    assert observed.state == "failed"
    assert repository.request_count == 0

    replacement = service.request(11)
    assert replacement.state == "queued"
    assert repository.invalid_artifact_ids == [12]
