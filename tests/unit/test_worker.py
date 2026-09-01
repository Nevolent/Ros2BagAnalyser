from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import shutil
from types import SimpleNamespace

from rosbag_analyser.artifact_store import (
    MediaValidation,
    PublishedArtifact,
    SeriesValidation,
)
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import (
    FRONT_ALL_ZERO_HEADER_TIMING_POLICY,
    FRONT_ALL_ZERO_HEADER_TIMESTAMP_PROVENANCE,
)
from rosbag_analyser.imu_series import IMU_SERIES_DEFINITIONS
from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.persistence.processing_repository import JobRecord
from rosbag_analyser.processors.front_preview import (
    FrontPreviewProcessingError,
    FrontPreviewResult,
)
from rosbag_analyser.processors.imu_series import (
    ImuComponentResult,
    ImuSeriesProcessingError,
    ImuSeriesResult,
)
from rosbag_analyser.processors.topdown_preview import (
    TopdownPreviewProcessingError,
    TopdownPreviewResult,
)
from rosbag_analyser.worker import SerialWorker


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


def _topdown_job() -> JobRecord:
    return JobRecord(
        **{
            **_job().__dict__,
            "kind": "topdown_preview",
        }
    )


def _imu_job() -> JobRecord:
    return JobRecord(**{**_job().__dict__, "kind": "imu_series"})


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


class FakeImuResolver:
    def __init__(self) -> None:
        self.descriptor = SimpleNamespace(
            cache_identity="a" * 64,
            topic=SimpleNamespace(
                name="/sensors/imu",
                message_type="sensor_msgs/msg/Imu",
                serialization_format="cdr",
            ),
            component="angular_velocity.z",
        )

    def resolve(self, recording_id: int):
        del recording_id
        return SimpleNamespace(descriptor=self.descriptor, diagnostic=None)


class SuccessfulProcessor:
    profile = V0_PREVIEW_PROFILE

    def process(self, descriptor, output_path: Path, *, control=None) -> FrontPreviewResult:
        del descriptor, control
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
            header_span_ns=790_000_000,
            maximum_presentation_gap_ns=60_000_000,
            media_pts_sha256="c" * 64,
        )


class FailingProcessor(SuccessfulProcessor):
    def process(self, descriptor, output_path: Path, *, control=None) -> FrontPreviewResult:
        del descriptor, output_path, control
        raise FrontPreviewProcessingError(
            "front_payload_invalid", "A front-camera image has an invalid payload."
        )


class SuccessfulAllZeroHeaderProcessor(SuccessfulProcessor):
    def process(
        self, descriptor, output_path: Path, *, control=None
    ) -> FrontPreviewResult:
        result = super().process(descriptor, output_path, control=control)
        return replace(
            result,
            header_span_ns=0,
            timing_policy=FRONT_ALL_ZERO_HEADER_TIMING_POLICY,
            timestamp_provenance=FRONT_ALL_ZERO_HEADER_TIMESTAMP_PROVENANCE,
        )


class CancelingProcessor(SuccessfulProcessor):
    def __init__(self, repository) -> None:
        self.repository = repository

    def process(self, descriptor, output_path: Path, *, control=None) -> FrontPreviewResult:
        del descriptor, control
        output_path.write_bytes(b"temporary-canceled-preview")
        self.repository.control_state = "cancel_requested"
        raise JobCanceled("synthetic cancellation")


class SuccessfulTopdownProcessor:
    profile = V0_PREVIEW_PROFILE

    def process(self, descriptor, output_path: Path, *, control=None) -> TopdownPreviewResult:
        del descriptor, control
        output_path.write_bytes(b"temporary-topdown-preview")
        return TopdownPreviewResult(
            input_frame_count=3,
            timestamp_count=3,
            encoded_frame_count=3,
            coverage_start_ns=200_000_000,
            coverage_end_ns=1_100_000_000,
            output_width=640,
            output_height=480,
            measured_span_ns=900_000_000,
            media_pts_sha256="d" * 64,
            warnings=("coverage_starts_after_recording",),
        )


class FailingTopdownProcessor(SuccessfulTopdownProcessor):
    def process(self, descriptor, output_path: Path, *, control=None) -> TopdownPreviewResult:
        del descriptor, output_path, control
        raise TopdownPreviewProcessingError(
            "topdown_frame_count_mismatch",
            "The top-down video and timestamp row counts do not match.",
        )


class SuccessfulImuProcessor:
    def process(self, descriptor, output_path: Path, *, control=None) -> ImuSeriesResult:
        del descriptor, control
        output_path.write_text(
            '{"schema_version":2,"samples":[["100000000",1.5,1.5,1.5,1.5,1.5,1.5],'
            '["300000000",null,null,null,null,null,null],'
            '["900000000",-2.0,-2.0,-2.0,-2.0,-2.0,-2.0]]}'
        )
        return ImuSeriesResult(
            sample_count=3,
            duplicate_timestamp_count=0,
            coverage_start_ns=100_000_000,
            coverage_end_ns=900_000_000,
            series=tuple(
                ImuComponentResult(
                    id=definition.id,
                    component=definition.component,
                    finite_count=2,
                    non_finite_count=1,
                    minimum_value=-2.0,
                    maximum_value=1.5,
                )
                for definition in IMU_SERIES_DEFINITIONS
            ),
            warnings=("non_finite_values_present",),
        )


class FailingImuProcessor(SuccessfulImuProcessor):
    def process(self, descriptor, output_path: Path, *, control=None) -> ImuSeriesResult:
        del descriptor, output_path, control
        raise ImuSeriesProcessingError(
            "imu_deserialization_failed", "An IMU message could not be decoded."
        )


class FakeArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cleaned_interrupted: tuple[int, ...] = ()
        self.published_manifest: dict[str, object] | None = None
        self.validation_expectations: dict[str, object] | None = None

    def create_workspace(self, job_id: int) -> Path:
        workspace = self.root / f"job-{job_id}-owned"
        workspace.mkdir()
        return workspace

    def validate_preview(self, path: Path, profile, **expectations) -> MediaValidation:
        del profile
        self.validation_expectations = expectations
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

    def validate_series(self, path: Path, **expectations) -> SeriesValidation:
        self.validation_expectations = expectations
        details = path.stat(follow_symlinks=False)
        return SeriesValidation(
            size_bytes=details.st_size,
            device_id=details.st_dev,
            inode=details.st_ino,
            mtime_ns=details.st_mtime_ns,
            sample_count=3,
            column_count=6,
            coverage_start_ns=100_000_000,
            coverage_end_ns=900_000_000,
        )

    def publish_series(
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
        series = workspace / "series.json"
        final = self.root / "published-series.json"
        series.replace(final)
        return PublishedArtifact(
            "rosbag-analyser/published-series.json", final.stat().st_size
        )

    def clean_workspace(self, workspace: Path, job_id: int) -> None:
        del job_id
        shutil.rmtree(workspace)

    def clean_interrupted_workspaces(self, job_ids: tuple[int, ...]) -> None:
        self.cleaned_interrupted = job_ids


class CancelingRepository(FakeRepository):
    def __init__(self, job: JobRecord) -> None:
        super().__init__(job)
        self.control_state = "none"
        self.cancel_cleanup_started = False
        self.cancellation_completed = False

    def worker_checkpoint(self, job_id: int, phase: str):
        del phase
        assert job_id == 5
        return SimpleNamespace(state="running", control_state=self.control_state)

    def acknowledge_pause(self, job_id: int):
        raise AssertionError(f"Job {job_id} should not pause in this test.")

    def enter_publishing(self, job_id: int):
        raise AssertionError(f"Job {job_id} must not publish after cancellation.")

    def begin_cancel_cleanup(self, job_id: int):
        assert job_id == 5
        self.cancel_cleanup_started = True
        return SimpleNamespace(state="running", control_state="cancel_requested")

    def complete_cancellation(self, job_id: int):
        assert job_id == 5 and self.cancel_cleanup_started
        self.cancellation_completed = True
        return SimpleNamespace(state="canceled", control_state="none")


def _worker(
    repository: FakeRepository,
    processor: SuccessfulProcessor,
    store: FakeArtifactStore,
    resolver: FakeResolver | None = None,
) -> SerialWorker:
    return SerialWorker(
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
        "timestamp_provenance": "ros_image_header_affine_to_record_span",
        "policy": "capture_header_affine_to_record_span_v2",
        "bounds": "measured",
        "coverage_start_ns": "100000000",
        "coverage_end_ns": "900000000",
        "measured_span_ns": "800000000",
        "header_span_ns": "790000000",
        "affine_scale_numerator": "800000000",
        "affine_scale_denominator": "790000000",
        "maximum_presentation_gap_ns": "60000000",
        "media_timescale": 1_000_000,
        "media_pts_sha256": "c" * 64,
    }
    assert store.validation_expectations is not None
    assert store.validation_expectations["expected_media_pts_sha256"] == "c" * 64
    assert not (tmp_path / "job-5-owned").exists()


def test_worker_records_all_zero_header_record_time_provenance(tmp_path: Path) -> None:
    repository = FakeRepository(_job())
    store = FakeArtifactStore(tmp_path)

    assert _worker(
        repository, SuccessfulAllZeroHeaderProcessor(), store
    ).run_once()

    assert store.published_manifest is not None
    timing = store.published_manifest["timing"]
    assert isinstance(timing, dict)
    assert timing["timestamp_provenance"] == (
        "ros_record_timestamp_all_zero_image_headers"
    )
    assert timing["policy"] == "ros_record_timestamp_all_zero_image_headers_v3"
    assert timing["header_span_ns"] == "0"
    assert timing["image_header_stamps"] == "all_zero"
    assert "affine_scale_numerator" not in timing
    assert "affine_scale_denominator" not in timing


def test_worker_leaves_queue_untouched_when_admission_is_paused(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(_job())
    store = FakeArtifactStore(tmp_path)
    worker = SerialWorker(
        repository,  # type: ignore[arg-type]
        FakeResolver(),  # type: ignore[arg-type]
        SuccessfulProcessor(),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
        admission_check=lambda: SimpleNamespace(
            code="derived_space_low",
            message="New preparation is paused because derived storage is low on space.",
        ),
    )

    assert not worker.run_once()
    assert repository.job is not None
    assert repository.completed == []
    assert repository.failures == []


def test_worker_dispatches_topdown_job_with_csv_provenance(tmp_path: Path) -> None:
    repository = FakeRepository(_topdown_job())
    front_store = FakeArtifactStore(tmp_path)
    topdown_store = FakeArtifactStore(tmp_path)
    resolver = FakeResolver()
    worker = SerialWorker(
        repository,  # type: ignore[arg-type]
        FakeResolver(),  # type: ignore[arg-type]
        SuccessfulProcessor(),  # type: ignore[arg-type]
        front_store,  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
        topdown_resolver=resolver,  # type: ignore[arg-type]
        topdown_processor=SuccessfulTopdownProcessor(),  # type: ignore[arg-type]
        topdown_artifact_store=topdown_store,  # type: ignore[arg-type]
    )

    assert worker.run_once()

    assert repository.failures == []
    assert len(repository.completed) == 1
    _, artifact = repository.completed[0]
    assert artifact.kind == "topdown_preview"
    assert artifact.coverage_start_ns == 200_000_000
    assert topdown_store.published_manifest is not None
    assert topdown_store.published_manifest["artifact_kind"] == "topdown_preview"
    assert topdown_store.published_manifest["warnings"] == [
        "coverage_starts_after_recording"
    ]
    assert topdown_store.validation_expectations is not None
    assert topdown_store.validation_expectations["expected_media_pts_sha256"] == (
        "d" * 64
    )
    assert topdown_store.published_manifest["timing"] == {
        "timestamp_provenance": "csv_unix_timestamp",
        "bounds": "measured",
        "coverage_start_ns": "200000000",
        "coverage_end_ns": "1100000000",
        "measured_span_ns": "900000000",
        "media_timescale": 1_000_000,
        "media_pts_sha256": "d" * 64,
    }


def test_topdown_processing_failure_creates_no_artifact(tmp_path: Path) -> None:
    repository = FakeRepository(_topdown_job())
    store = FakeArtifactStore(tmp_path)
    worker = SerialWorker(
        repository,  # type: ignore[arg-type]
        FakeResolver(),  # type: ignore[arg-type]
        SuccessfulProcessor(),  # type: ignore[arg-type]
        FakeArtifactStore(tmp_path),  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
        topdown_resolver=FakeResolver(),  # type: ignore[arg-type]
        topdown_processor=FailingTopdownProcessor(),  # type: ignore[arg-type]
        topdown_artifact_store=store,  # type: ignore[arg-type]
    )

    assert worker.run_once()

    assert repository.completed == []
    assert repository.failures == [
        (
            5,
            "topdown_frame_count_mismatch",
            "The top-down video and timestamp row counts do not match.",
        )
    ]
    assert not (tmp_path / "job-5-owned").exists()


def test_worker_dispatches_imu_series_with_record_time_provenance(
    tmp_path: Path,
) -> None:
    repository = FakeRepository(_imu_job())
    imu_store = FakeArtifactStore(tmp_path)
    worker = SerialWorker(
        repository,  # type: ignore[arg-type]
        FakeResolver(),  # type: ignore[arg-type]
        SuccessfulProcessor(),  # type: ignore[arg-type]
        FakeArtifactStore(tmp_path),  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
        imu_resolver=FakeImuResolver(),  # type: ignore[arg-type]
        imu_processor=SuccessfulImuProcessor(),  # type: ignore[arg-type]
        imu_artifact_store=imu_store,  # type: ignore[arg-type]
    )

    assert worker.run_once()

    assert repository.failures == []
    assert len(repository.completed) == 1
    _, artifact = repository.completed[0]
    assert artifact.kind == "imu_series"
    assert artifact.mime_type == "application/json"
    assert artifact.coverage_start_ns == 100_000_000
    assert imu_store.published_manifest is not None
    assert imu_store.published_manifest["artifact_kind"] == "imu_series"
    assert imu_store.published_manifest["timing"] == {
        "timestamp_provenance": "ros_record_timestamp",
        "bounds": "measured",
        "coverage_start_ns": "100000000",
        "coverage_end_ns": "900000000",
        "duplicate_timestamp_policy": "preserve-database-order",
    }
    assert imu_store.published_manifest["reduction"] == {"method": "none"}
    source = imu_store.published_manifest["source"]
    assert isinstance(source, dict)
    assert source["default_component"] == "angular_velocity.z"
    assert source["default_series_id"] == "angular_velocity_z"
    series = imu_store.published_manifest["series"]
    assert isinstance(series, list)
    assert [item["id"] for item in series] == [
        definition.id for definition in IMU_SERIES_DEFINITIONS
    ]
    assert all(item["available"] for item in series)
    assert imu_store.validation_expectations is not None
    assert imu_store.validation_expectations["expected_schema_version"] == 2
    assert imu_store.validation_expectations["expected_sample_count"] == 3
    assert (
        imu_store.validation_expectations["expected_coverage_start_ns"]
        == 100_000_000
    )
    assert (
        imu_store.validation_expectations["expected_coverage_end_ns"]
        == 900_000_000
    )
    columns = imu_store.validation_expectations["expected_columns"]
    assert isinstance(columns, tuple)
    assert [column.id for column in columns] == [
        definition.id for definition in IMU_SERIES_DEFINITIONS
    ]
    assert all(column.finite_count == 2 for column in columns)
    assert all(column.non_finite_count == 1 for column in columns)


def test_imu_failure_creates_no_ready_artifact(tmp_path: Path) -> None:
    repository = FakeRepository(_imu_job())
    imu_store = FakeArtifactStore(tmp_path)
    worker = SerialWorker(
        repository,  # type: ignore[arg-type]
        FakeResolver(),  # type: ignore[arg-type]
        SuccessfulProcessor(),  # type: ignore[arg-type]
        FakeArtifactStore(tmp_path),  # type: ignore[arg-type]
        "/camera/image_raw",
        "test-encoder-v1",
        imu_resolver=FakeImuResolver(),  # type: ignore[arg-type]
        imu_processor=FailingImuProcessor(),  # type: ignore[arg-type]
        imu_artifact_store=imu_store,  # type: ignore[arg-type]
    )

    assert worker.run_once()

    assert repository.completed == []
    assert repository.failures == [
        (5, "imu_deserialization_failed", "An IMU message could not be decoded.")
    ]
    assert imu_store.published_manifest is None
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


def test_worker_cancellation_cleans_only_owned_workspace_and_preserves_ready_output(
    tmp_path: Path,
) -> None:
    repository = CancelingRepository(_job())
    store = FakeArtifactStore(tmp_path)
    prior_ready = tmp_path / "prior-ready.mp4"
    prior_ready.write_bytes(b"validated-existing-output")

    assert _worker(repository, CancelingProcessor(repository), store).run_once()

    assert repository.cancel_cleanup_started
    assert repository.cancellation_completed
    assert repository.completed == []
    assert repository.failures == []
    assert store.published_manifest is None
    assert not (tmp_path / "job-5-owned").exists()
    assert prior_ready.read_bytes() == b"validated-existing-output"


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
