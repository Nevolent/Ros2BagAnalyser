from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from types import SimpleNamespace

from rosbag_analyser.artifact_store import MediaValidation, PublishedArtifact
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.persistence.processing_repository import JobRecord
from rosbag_analyser.processors.front_preview import (
    FrontPreviewProcessingError,
    FrontPreviewResult,
)
from rosbag_analyser.worker import FrontPreviewWorker


def _job() -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        id=5,
        recording_id=11,
        kind="front_preview",
        cache_identity="a" * 64,
        state="running",
        queued_at=now,
        started_at=now,
        finished_at=None,
        error_code=None,
        error_message=None,
    )


class FakeRepository:
    def __init__(self, job: JobRecord | None) -> None:
        self.job = job
        self.completed = []
        self.failures: list[tuple[int, str, str]] = []
        self.interrupted = (21, 22)

    def claim_next_job(self):
        job, self.job = self.job, None
        return job

    def complete_job(self, job_id: int, artifact):
        self.completed.append((job_id, artifact))

    def fail_job(self, job_id: int, code: str, message: str) -> None:
        self.failures.append((job_id, code, message))

    def mark_running_jobs_interrupted(self) -> tuple[int, ...]:
        return self.interrupted


class FakeResolver:
    def __init__(self) -> None:
        self.descriptor = SimpleNamespace(
            cache_identity="a" * 64,
            topic=SimpleNamespace(
                message_type="sensor_msgs/msg/Image",
                serialization_format="cdr",
            ),
        )

    def resolve(self, recording_id: int):
        del recording_id
        return SimpleNamespace(descriptor=self.descriptor, diagnostic=None)


class SuccessfulProcessor:
    profile = V0_PREVIEW_PROFILE

    def process(self, descriptor, output_path: Path) -> FrontPreviewResult:
        del descriptor
        output_path.write_bytes(b"temporary-preview")
        return FrontPreviewResult(
            input_frame_count=4,
            encoded_frame_count=3,
            duplicate_timestamp_count=1,
            coverage_start_ns=100_000_000,
            coverage_end_ns=900_000_000,
            output_width=640,
            output_height=360,
            measured_span_ns=800_000_000,
        )


class FailingProcessor(SuccessfulProcessor):
    def process(self, descriptor, output_path: Path) -> FrontPreviewResult:
        del descriptor, output_path
        raise FrontPreviewProcessingError(
            "front_payload_invalid", "A front-camera image has an invalid payload."
        )


class FakeArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cleaned_interrupted: tuple[int, ...] = ()
        self.published_manifest: dict[str, object] | None = None

    def create_workspace(self, job_id: int) -> Path:
        workspace = self.root / f"job-{job_id}-owned"
        workspace.mkdir()
        return workspace

    def validate_preview(self, path: Path, profile, **expectations) -> MediaValidation:
        del profile, expectations
        details = path.stat(follow_symlinks=False)
        return MediaValidation(
            size_bytes=details.st_size,
            device_id=details.st_dev,
            inode=details.st_ino,
            mtime_ns=details.st_mtime_ns,
            width=640,
            height=360,
            codec="h264",
            pixel_format="yuv420p",
            duration_seconds=0.8,
            frame_count=3,
        )

    def publish(
        self,
        workspace: Path,
        job_id: int,
        cache_identity: str,
        manifest: dict[str, object],
        *,
        replace_conflicting: bool = False,
    ) -> PublishedArtifact:
        del job_id, cache_identity
        assert replace_conflicting
        self.published_manifest = manifest
        media = workspace / "preview.mp4"
        final = self.root / "published.mp4"
        media.replace(final)
        return PublishedArtifact("rosbag-analyser/published.mp4", final.stat().st_size)

    def clean_workspace(self, workspace: Path, job_id: int) -> None:
        del job_id
        shutil.rmtree(workspace)

    def clean_interrupted_workspaces(self, job_ids: tuple[int, ...]) -> None:
        self.cleaned_interrupted = job_ids


def _worker(
    repository: FakeRepository,
    processor: SuccessfulProcessor,
    store: FakeArtifactStore,
    resolver: FakeResolver | None = None,
) -> FrontPreviewWorker:
    return FrontPreviewWorker(
        repository,  # type: ignore[arg-type]
        resolver or FakeResolver(),  # type: ignore[arg-type]
        processor,  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
    )


def test_worker_publishes_only_after_validation_and_completes_job(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(_job())
    store = FakeArtifactStore(tmp_path)

    assert _worker(repository, SuccessfulProcessor(), store).run_once()

    assert repository.failures == []
    assert len(repository.completed) == 1
    job_id, artifact = repository.completed[0]
    assert job_id == 5
    assert artifact.coverage_start_ns == 100_000_000
    assert artifact.coverage_end_ns == 900_000_000
    assert store.published_manifest is not None
    assert store.published_manifest["cache_identity"] == "a" * 64
    output = store.published_manifest["output"]
    assert isinstance(output, dict)
    published_stat = (tmp_path / "published.mp4").stat()
    assert output["file_identity"] == {
        "device_id": published_stat.st_dev,
        "inode": published_stat.st_ino,
        "mtime_ns": published_stat.st_mtime_ns,
    }
    assert store.published_manifest["timing"] == {
        "timestamp_provenance": "ros_record_timestamp",
        "bounds": "measured",
        "coverage_start_ns": "100000000",
        "coverage_end_ns": "900000000",
        "measured_span_ns": "800000000",
        "media_timescale": 1_000_000,
    }
    assert not (tmp_path / "job-5-owned").exists()


def test_processing_failure_creates_no_ready_artifact_and_cleans_workspace(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(_job())
    store = FakeArtifactStore(tmp_path)

    assert _worker(repository, FailingProcessor(), store).run_once()

    assert repository.completed == []
    assert repository.failures == [
        (5, "front_payload_invalid", "A front-camera image has an invalid payload.")
    ]
    assert store.published_manifest is None
    assert not (tmp_path / "job-5-owned").exists()


def test_source_identity_is_rechecked_after_output_validation_before_publish(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(_job())
    resolver = FakeResolver()

    class SourceChangingStore(FakeArtifactStore):
        def validate_preview(
            self, path: Path, profile, **expectations
        ) -> MediaValidation:
            validation = super().validate_preview(path, profile, **expectations)
            resolver.descriptor = SimpleNamespace(
                cache_identity="b" * 64,
                topic=resolver.descriptor.topic,
            )
            return validation

    store = SourceChangingStore(tmp_path)

    assert _worker(
        repository, SuccessfulProcessor(), store, resolver=resolver
    ).run_once()

    assert repository.completed == []
    assert repository.failures == [
        (5, "preview_inputs_changed", "Preview inputs changed during generation.")
    ]
    assert store.published_manifest is None
    assert not (tmp_path / "job-5-owned").exists()


def test_startup_marks_running_jobs_interrupted_before_owned_cleanup(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(None)
    store = FakeArtifactStore(tmp_path)

    interrupted = _worker(repository, SuccessfulProcessor(), store).recover_interrupted_jobs()

    assert interrupted == (21, 22)
    assert store.cleaned_interrupted == (21, 22)


def test_idle_worker_reports_no_work(tmp_path: Path) -> None:
    repository = FakeRepository(None)

    assert not _worker(
        repository, SuccessfulProcessor(), FakeArtifactStore(tmp_path)
    ).run_once()
