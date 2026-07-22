from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import yaml

from conftest import metadata_document
from rosbag_analyser.artifact_store import ArtifactStoreError
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord,
    JobRecord,
    ProcessingComponent,
    ProcessingSourceRecord,
    ProcessingState,
    RequestOutcome,
)
from rosbag_analyser.topdown_preview import (
    TopdownPreviewService,
    TopdownSourceResolver,
)


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
        del recording_id, kind
        artifact = (
            self.artifact
            if self.artifact is not None
            and self.artifact.cache_identity == cache_identity
            else None
        )
        return ProcessingState(artifact, self.active_job, self.latest_failed_job)

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
        if self.artifact is not None:
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
    def validate_media(self, *args: object) -> None:
        del args


class MissingArtifactStore(FakeArtifactStore):
    def validate_media(self, *args: object) -> None:
        del args
        raise ArtifactStoreError(
            "artifact_file_missing", "The ready preview file is unavailable."
        )


def _write_source(archive: Path) -> tuple[Path, Path, Path]:
    recording = archive / "run"
    recording.mkdir()
    metadata = recording / "metadata.yaml"
    metadata.write_text(
        yaml.safe_dump(metadata_document("run_0.db3"), sort_keys=False),
        encoding="utf-8",
    )
    video = recording / "run.avi"
    video.write_bytes(b"synthetic-video")
    timestamps = recording / "run.csv"
    timestamps.write_text(
        "unix_timestamp,human_timestamp\n1700000000.1,ignored\n",
        encoding="utf-8",
    )
    return metadata, video, timestamps


def _component(path: Path, condition: str) -> ProcessingComponent:
    details = path.stat()
    return ProcessingComponent(
        f"run/{path.name}", details.st_size, details.st_mtime_ns, condition
    )


def _source(metadata: Path, video: Path, timestamps: Path) -> ProcessingSourceRecord:
    return ProcessingSourceRecord(
        id=11,
        archive_relative_path="run",
        start_time_ns=1_700_000_000_000_000_000,
        duration_ns=2_500_000_000,
        ros_health="readable",
        metadata=_component(metadata, "readable"),
        database=None,
        topdown_video=_component(video, "present"),
        topdown_timestamps=_component(timestamps, "present"),
    )


def _resolver(archive: Path, repository: FakeRepository) -> TopdownSourceResolver:
    return TopdownSourceResolver(
        archive.resolve(),
        repository,  # type: ignore[arg-type]
        V0_PREVIEW_PROFILE,
        "test-encoder-v1",
    )


def _artifact(cache_identity: str) -> ArtifactRecord:
    return ArtifactRecord(
        id=3,
        recording_id=11,
        kind="topdown_preview",
        cache_identity=cache_identity,
        output_relative_path="derived/preview.mp4",
        mime_type="video/mp4",
        size_bytes=10,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={
            "artifact_kind": "topdown_preview",
            "cache_identity": cache_identity,
        },
        created_at=datetime.now(timezone.utc),
    )


def test_cache_identity_reuses_only_matching_topdown_inputs(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, video, timestamps = _write_source(archive)
    repository = FakeRepository(_source(metadata, video, timestamps))
    resolver = _resolver(archive, repository)

    first = resolver.resolve(11)
    repeated = resolver.resolve(11)
    assert first.descriptor is not None
    assert repeated.descriptor is not None
    assert first.descriptor.cache_identity == repeated.descriptor.cache_identity

    timestamps.write_text(
        "unix_timestamp,human_timestamp\n1700000000.2,ignored\n",
        encoding="utf-8",
    )
    repository.source = replace(
        repository.source,
        topdown_timestamps=_component(timestamps, "present"),
    )
    changed = resolver.resolve(11)
    assert changed.descriptor is not None
    assert changed.descriptor.cache_identity != first.descriptor.cache_identity


def test_damaged_or_missing_prerequisites_are_unavailable_without_job(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, video, timestamps = _write_source(archive)
    source = _source(metadata, video, timestamps)
    repository = FakeRepository(replace(source, ros_health="damaged"))
    service = TopdownPreviewService(
        _resolver(archive, repository),
        repository,  # type: ignore[arg-type]
        FakeArtifactStore(),  # type: ignore[arg-type]
    )

    damaged = service.request(11)
    assert damaged.state == "unavailable"
    assert damaged.diagnostic is not None
    assert damaged.diagnostic.code == "bag_origin_unavailable"
    assert repository.request_count == 0

    repository.source = replace(source, topdown_video=None)
    missing = service.request(11)
    assert missing.state == "unavailable"
    assert missing.diagnostic is not None
    assert missing.diagnostic.code == "topdown_video_unavailable"
    assert repository.request_count == 0


def test_request_reuses_ready_output_and_queues_only_when_needed(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, video, timestamps = _write_source(archive)
    repository = FakeRepository(_source(metadata, video, timestamps))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    service = TopdownPreviewService(
        resolver, repository, FakeArtifactStore()  # type: ignore[arg-type]
    )

    queued = service.request(11)
    assert queued.state == "queued"
    assert repository.request_count == 1

    repository.active_job = None
    repository.artifact = _artifact(resolution.descriptor.cache_identity)
    ready = service.get_state(11)
    assert ready.state == "ready"
    assert ready.artifact is repository.artifact
    assert repository.request_count == 1


def test_invalid_ready_artifact_requires_explicit_replacement_request(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    metadata, video, timestamps = _write_source(archive)
    repository = FakeRepository(_source(metadata, video, timestamps))
    resolver = _resolver(archive, repository)
    resolution = resolver.resolve(11)
    assert resolution.descriptor is not None
    repository.artifact = _artifact(resolution.descriptor.cache_identity)
    service = TopdownPreviewService(
        resolver, repository, MissingArtifactStore()  # type: ignore[arg-type]
    )

    failed = service.get_state(11)
    assert failed.state == "failed"
    assert repository.request_count == 0

    queued = service.request(11)
    assert queued.state == "queued"
    assert repository.invalid_artifact_ids == [3]
