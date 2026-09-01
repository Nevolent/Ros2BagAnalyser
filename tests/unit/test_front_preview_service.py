from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
import os
from pathlib import Path

import yaml

from conftest import metadata_document
from rosbag_analyser.artifact_store import ArtifactStoreError
from rosbag_analyser.catalog.paths import safe_filesystem_text
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import (
    FRONT_PREVIEW_V2_PROCESSOR_VERSION,
    FRONT_TIMING_POLICY_V2,
    FrontPreviewService,
    FrontSourceResolver,
    _cache_identity,
)
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    JobRecord,
    ProcessingComponent,
    ProcessingState,
    ProcessingSourceRecord,
    RequestOutcome,
)


TOPIC = "/camera/image_raw"
PLANNER_IDENTITY = "d" * 64


class FakeRepository:
    def __init__(self, source: ProcessingSourceRecord) -> None:
        self.source = source
        self.artifact: ArtifactRecord | None = None
        self.active_job: JobRecord | None = None
        self.latest_failed_job: JobRecord | None = None
        self.request_count = 0
        self.invalid_artifact_ids: list[int | None] = []
        self.delivery_requests: list[tuple[int, str, int, str]] = []

    def get_source(self, recording_id: int) -> ProcessingSourceRecord | None:
        return self.source if recording_id == self.source.id else None

    def get_artifact(self, recording_id: int, kind: str, cache_identity: str):
        del recording_id, kind
        if self.artifact is not None and self.artifact.cache_identity == cache_identity:
            return self.artifact
        return None

    def get_current_state(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> ProcessingState:
        return ProcessingState(
            artifact=self.get_artifact(recording_id, kind, cache_identity),
            active_job=self.active_job,
            latest_failed_job=self.latest_failed_job,
        )

    def get_current_artifact_for_delivery(
        self,
        recording_id: int,
        kind: str,
        artifact_id: int,
        planner_identity: str,
    ) -> ArtifactRecord | None:
        self.delivery_requests.append(
            (recording_id, kind, artifact_id, planner_identity)
        )
        artifact = self.artifact
        if (
            artifact is None
            or artifact.recording_id != recording_id
            or artifact.kind != kind
            or artifact.id != artifact_id
            or planner_identity != PLANNER_IDENTITY
        ):
            return None
        return artifact

    def get_active_job(self, recording_id: int, kind: str, cache_identity: str):
        del recording_id, kind, cache_identity
        return None

    def get_latest_failed_job(
        self, recording_id: int, kind: str, cache_identity: str
    ):
        del recording_id, kind, cache_identity
        return self.latest_failed_job

    def request_job(
        self,
        recording_id: int,
        kind: str,
        cache_identity: str,
        *,
        invalid_artifact_id: int | None = None,
    ):
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
    def __init__(self) -> None:
        self.opened = object()

    def validate_media(
        self,
        relative_path: str,
        expected_size: int,
        cache_identity: str,
        expected_manifest: dict[str, object],
    ) -> None:
        del relative_path, expected_size, cache_identity, expected_manifest

    def open_media(self, *args: object) -> object:
        del args
        return self.opened


class MissingArtifactStore(FakeArtifactStore):
    def validate_media(
        self,
        relative_path: str,
        expected_size: int,
        cache_identity: str,
        expected_manifest: dict[str, object],
    ) -> None:
        del relative_path, expected_size, cache_identity, expected_manifest
        raise ArtifactStoreError(
            "artifact_file_missing", "The ready preview file is unavailable."
        )


def _write_source(archive: Path) -> tuple[Path, Path]:
    recording = archive / "run"
    recording.mkdir()
    database = recording / "run_0.db3"
    database.write_bytes(b"sqlite-source-identity")
    metadata = recording / "metadata.yaml"
    metadata.write_text(
        yaml.safe_dump(metadata_document("run_0.db3"), sort_keys=False),
        encoding="utf-8",
    )
    return metadata, database


def _source(metadata: Path, database: Path, *, health: str = "readable") -> ProcessingSourceRecord:
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


def _resolver(archive: Path, repository: FakeRepository) -> FrontSourceResolver:
    return FrontSourceResolver(
        archive.resolve(),
        repository,  # type: ignore[arg-type]
        TOPIC,
        V0_PREVIEW_PROFILE,
        "test-encoder-v1",
    )


def test_cache_identity_is_reused_until_a_relevant_front_input_changes(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)

    first = resolver.resolve(11)
    repeated = resolver.resolve(11)
    assert first.descriptor is not None
    assert repeated.descriptor is not None
    assert repeated.descriptor.cache_identity == first.descriptor.cache_identity

    database.write_bytes(database.read_bytes() + b"changed")
    repository.source = _source(metadata, database)
    changed = resolver.resolve(11)

    assert changed.descriptor is not None
    assert changed.descriptor.cache_identity != first.descriptor.cache_identity


def test_front_v3_cache_identity_differs_from_historical_v2(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))

    resolution = _resolver(archive, repository).resolve(11)

    assert resolution.descriptor is not None
    descriptor = resolution.descriptor
    historical_v2 = _cache_identity(
        repository.source,
        descriptor.metadata_identity,
        descriptor.database_identity,
        descriptor.topic,
        TOPIC,
        V0_PREVIEW_PROFILE,
        "test-encoder-v1",
        processor_version=FRONT_PREVIEW_V2_PROCESSOR_VERSION,
        timing_policy=FRONT_TIMING_POLICY_V2,
    )
    assert descriptor.cache_identity != historical_v2


def test_safe_catalog_paths_resolve_non_utf8_recording_name(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    raw_recording_name = os.fsdecode(b"run_\xff")
    recording = archive / raw_recording_name
    recording.mkdir()
    database = recording / "run_0.db3"
    database.write_bytes(b"sqlite-source-identity")
    metadata = recording / "metadata.yaml"
    metadata.write_text(
        yaml.safe_dump(metadata_document("run_0.db3"), sort_keys=False),
        encoding="utf-8",
    )
    encoded_name = safe_filesystem_text(raw_recording_name)
    source = _source(metadata, database)
    source = replace(
        source,
        archive_relative_path=encoded_name,
        metadata=replace(
            source.metadata,
            relative_path=f"{encoded_name}/metadata.yaml",
        ),
        database=replace(
            source.database,
            relative_path=f"{encoded_name}/run_0.db3",
        ),
    )
    repository = FakeRepository(source)

    resolution = _resolver(archive, repository).resolve(11)

    assert resolution.descriptor is not None
    assert resolution.descriptor.database_path == database


def test_matching_ready_artifact_is_reused_without_a_job(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    repository.artifact = ArtifactRecord(
        id=3,
        recording_id=11,
        kind="front_preview",
        cache_identity=resolution.descriptor.cache_identity,
        output_relative_path="rosbag-analyser/artifacts/front_preview/preview.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={"cache_identity": resolution.descriptor.cache_identity},
        created_at=datetime.now(timezone.utc),
    )
    service = FrontPreviewService(
        resolver,
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
        PLANNER_IDENTITY,
    )

    state = service.request(11)

    assert state.state == "ready"
    assert state.artifact == repository.artifact
    assert repository.request_count == 0


def test_media_delivery_uses_persisted_target_without_resolving_source(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    repository.artifact = ArtifactRecord(
        id=3,
        recording_id=11,
        kind="front_preview",
        cache_identity="a" * 64,
        output_relative_path="rosbag-analyser/artifacts/front_preview/preview.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={"cache_identity": "a" * 64},
        created_at=datetime.now(timezone.utc),
    )
    repository.source = None  # type: ignore[assignment]
    store = FakeArtifactStore()
    service = FrontPreviewService(
        _resolver(archive, repository),
        repository,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        PLANNER_IDENTITY,
    )

    resolved = service.resolve_media(11, 3)

    assert resolved is not None
    assert resolved[0] is store.opened
    assert resolved[1] is repository.artifact
    assert repository.delivery_requests == [
        (11, "front_preview", 3, PLANNER_IDENTITY)
    ]


def test_poll_state_tracks_processing_failure_and_ready_artifact(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    identity = resolution.descriptor.cache_identity
    now = datetime.now(timezone.utc)
    repository.active_job = JobRecord(
        id=8,
        recording_id=11,
        kind="front_preview",
        cache_identity=identity,
        state="running",
        queued_at=now,
        started_at=now,
        finished_at=None,
        error_code=None,
        error_message=None,
    )
    service = FrontPreviewService(
        resolver,
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
        PLANNER_IDENTITY,
    )

    assert service.get_state(11).state == "processing"

    repository.active_job = None
    repository.latest_failed_job = JobRecord(
        id=8,
        recording_id=11,
        kind="front_preview",
        cache_identity=identity,
        state="failed",
        queued_at=now,
        started_at=now,
        finished_at=now,
        error_code="preview_processing_failed",
        error_message="Preview generation failed.",
    )
    failed = service.get_state(11)
    assert failed.state == "failed"
    assert failed.diagnostic is not None
    assert failed.diagnostic.code == "preview_processing_failed"

    repository.latest_failed_job = None
    repository.artifact = ArtifactRecord(
        id=3,
        recording_id=11,
        kind="front_preview",
        cache_identity=identity,
        output_relative_path="rosbag-analyser/artifacts/front_preview/preview.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={"cache_identity": identity},
        created_at=now,
    )
    ready = service.get_state(11)
    assert ready.state == "ready"
    assert ready.artifact == repository.artifact


def test_missing_ready_file_is_retired_and_retry_job_is_queued(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    repository.artifact = ArtifactRecord(
        id=3,
        recording_id=11,
        kind="front_preview",
        cache_identity=resolution.descriptor.cache_identity,
        output_relative_path="rosbag-analyser/missing.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={"cache_identity": resolution.descriptor.cache_identity},
        created_at=datetime.now(timezone.utc),
    )
    service = FrontPreviewService(
        resolver,
        repository,  # type: ignore[arg-type]
        MissingArtifactStore(),  # type: ignore[arg-type]
        PLANNER_IDENTITY,
    )

    state = service.request(11)

    assert state.state == "queued"
    assert state.diagnostic is None
    assert repository.request_count == 1
    assert repository.invalid_artifact_ids == [3]
    assert repository.artifact is None


def test_damaged_recording_is_unavailable_and_creates_no_job(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database, health="damaged"))
    service = FrontPreviewService(
        _resolver(archive, repository),
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
        PLANNER_IDENTITY,
    )

    state = service.request(11)

    assert state.state == "unavailable"
    assert state.diagnostic is not None
    assert state.diagnostic.code == "ros_source_unavailable"
    assert repository.request_count == 0


def test_configured_topic_must_match_metadata_exactly(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, database = _write_source(archive)
    repository = FakeRepository(_source(metadata, database))
    resolver = FrontSourceResolver(
        archive.resolve(),
        repository,  # type: ignore[arg-type]
        "/different/topic",
        V0_PREVIEW_PROFILE,
        "test-encoder-v1",
    )

    resolution = resolver.resolve(11)

    assert resolution.descriptor is None
    assert resolution.diagnostic is not None
    assert resolution.diagnostic.code == "front_topic_unavailable"
