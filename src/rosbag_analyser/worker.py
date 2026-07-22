from __future__ import annotations

import logging
import signal
import time

from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.config import AppConfig, ConfigurationError
from rosbag_analyser.front_preview import (
    PROCESSOR_VERSION,
    FrontSourceResolver,
    encoder_identity,
)
from rosbag_analyser.imu_series import (
    DUPLICATE_TIMESTAMP_POLICY,
    IMU_DISPLAY_LABEL,
    IMU_UNITS,
    NON_FINITE_POLICY,
    PROCESSOR_VERSION as IMU_PROCESSOR_VERSION,
    SERIES_SCHEMA_VERSION,
    ImuSourceResolver,
)
from rosbag_analyser.persistence.database import open_connection
from rosbag_analyser.persistence.processing_repository import (
    ArtifactWrite,
    FRONT_PREVIEW_KIND,
    IMU_SERIES_KIND,
    JobRecord,
    ProcessingRepository,
    TOPDOWN_PREVIEW_KIND,
)
from rosbag_analyser.processors.front_preview import (
    FrontPreviewProcessingError,
    FrontPreviewProcessor,
)
from rosbag_analyser.processors.imu_series import (
    ImuSeriesProcessingError,
    ImuSeriesProcessor,
)
from rosbag_analyser.processors.topdown_preview import (
    TopdownPreviewProcessingError,
    TopdownPreviewProcessor,
)
from rosbag_analyser.topdown_preview import (
    PROCESSOR_VERSION as TOPDOWN_PROCESSOR_VERSION,
    TopdownSourceResolver,
)


logger = logging.getLogger(__name__)
WORKER_LOCK_NAME = "rosbag_analyser_serial_worker"
POLL_INTERVAL_SECONDS = 1.0


class SerialWorker:
    def __init__(
        self,
        repository: ProcessingRepository,
        resolver: FrontSourceResolver,
        processor: FrontPreviewProcessor,
        artifact_store: ArtifactStore,
        topic_name: str,
        media_encoder_identity: str,
        *,
        topdown_resolver: TopdownSourceResolver | None = None,
        topdown_processor: TopdownPreviewProcessor | None = None,
        topdown_artifact_store: ArtifactStore | None = None,
        imu_resolver: ImuSourceResolver | None = None,
        imu_processor: ImuSeriesProcessor | None = None,
        imu_artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.repository = repository
        self.resolver = resolver
        self.processor = processor
        self.artifact_store = artifact_store
        self.topic_name = topic_name
        self.media_encoder_identity = media_encoder_identity
        self.topdown_resolver = topdown_resolver
        self.topdown_processor = topdown_processor
        self.topdown_artifact_store = topdown_artifact_store
        self.imu_resolver = imu_resolver
        self.imu_processor = imu_processor
        self.imu_artifact_store = imu_artifact_store

    def recover_interrupted_jobs(self) -> tuple[int, ...]:
        interrupted = self.repository.mark_running_jobs_interrupted()
        self.artifact_store.clean_interrupted_workspaces(interrupted)
        return interrupted

    def run_once(self) -> bool:
        job = self.repository.claim_next_job()
        if job is None:
            return False
        self._run_job(job)
        return True

    def _run_job(self, job: JobRecord) -> None:
        if job.kind == FRONT_PREVIEW_KIND:
            self._run_front_job(job)
            return
        if job.kind == TOPDOWN_PREVIEW_KIND:
            self._run_topdown_job(job)
            return
        if job.kind == IMU_SERIES_KIND:
            self._run_imu_job(job)
            return
        self.repository.fail_job(
            job.id,
            "artifact_kind_unsupported",
            "The requested artifact kind is unsupported.",
        )

    def _run_front_job(self, job: JobRecord) -> None:
        workspace = None
        started = time.monotonic()
        try:
            resolution = self.resolver.resolve(job.recording_id)
            if resolution.descriptor is None:
                message = (
                    "Preview prerequisites are no longer available."
                    if resolution.diagnostic is None
                    else resolution.diagnostic.message
                )
                code = (
                    "preview_prerequisites_changed"
                    if resolution.diagnostic is None
                    else resolution.diagnostic.code
                )
                raise FrontPreviewProcessingError(code, message)
            descriptor = resolution.descriptor
            if descriptor.cache_identity != job.cache_identity:
                raise FrontPreviewProcessingError(
                    "preview_inputs_changed",
                    "Preview inputs changed after this job was requested.",
                )

            workspace = self.artifact_store.create_workspace(job.id)
            output_path = workspace / "preview.mp4"
            result = self.processor.process(descriptor, output_path)

            validation = self.artifact_store.validate_preview(
                output_path,
                self.processor.profile,
                expected_width=result.output_width,
                expected_height=result.output_height,
                expected_frame_count=result.encoded_frame_count,
                measured_span_ns=result.measured_span_ns,
            )
            manifest: dict[str, object] = {
                "schema_version": 1,
                "artifact_kind": FRONT_PREVIEW_KIND,
                "cache_identity": job.cache_identity,
                "processor_version": PROCESSOR_VERSION,
                "encoder_identity": self.media_encoder_identity,
                "source": {
                    "topic": self.topic_name,
                    "message_type": descriptor.topic.message_type,
                    "serialization_format": descriptor.topic.serialization_format,
                },
                "timing": {
                    "timestamp_provenance": "ros_record_timestamp",
                    "bounds": "measured",
                    "coverage_start_ns": str(result.coverage_start_ns),
                    "coverage_end_ns": str(result.coverage_end_ns),
                    "measured_span_ns": str(result.measured_span_ns),
                    "media_timescale": self.processor.profile.media_timescale,
                },
                "profile": self.processor.profile.identity_values(),
                "output": {
                    "file_name": "preview.mp4",
                    "mime_type": self.processor.profile.mime_type,
                    "size_bytes": validation.size_bytes,
                    "file_identity": {
                        "device_id": validation.device_id,
                        "inode": validation.inode,
                        "mtime_ns": validation.mtime_ns,
                    },
                    "width": validation.width,
                    "height": validation.height,
                    "codec": validation.codec,
                    "pixel_format": validation.pixel_format,
                    "duration_seconds": validation.duration_seconds,
                },
                "frames": {
                    "input": result.input_frame_count,
                    "encoded": result.encoded_frame_count,
                    "duplicate_timestamps": result.duplicate_timestamp_count,
                },
            }
            current = self.resolver.resolve(job.recording_id)
            if (
                current.descriptor is None
                or current.descriptor.cache_identity != job.cache_identity
            ):
                raise FrontPreviewProcessingError(
                    "preview_inputs_changed",
                    "Preview inputs changed during generation.",
                )
            published = self.artifact_store.publish(
                workspace,
                job.id,
                job.cache_identity,
                manifest,
                replace_conflicting=True,
            )
            self.repository.complete_job(
                job.id,
                ArtifactWrite(
                    recording_id=job.recording_id,
                    kind=job.kind,
                    cache_identity=job.cache_identity,
                    output_relative_path=published.output_relative_path,
                    mime_type=self.processor.profile.mime_type,
                    size_bytes=published.size_bytes,
                    coverage_start_ns=result.coverage_start_ns,
                    coverage_end_ns=result.coverage_end_ns,
                    manifest=manifest,
                ),
            )
            logger.info(
                "Front preview job %s succeeded in %.3f seconds (%s bytes).",
                job.id,
                time.monotonic() - started,
                published.size_bytes,
            )
        except (FrontPreviewProcessingError, ArtifactStoreError) as error:
            self.repository.fail_job(job.id, error.code, error.safe_message)
            logger.warning(
                "Front preview job %s failed with code %s.",
                job.id,
                error.code,
                exc_info=True,
            )
        except Exception:
            self.repository.fail_job(
                job.id,
                "preview_processing_failed",
                "Preview generation failed unexpectedly. Request it again.",
            )
            logger.exception("Front preview job %s failed unexpectedly.", job.id)
        finally:
            if workspace is not None and workspace.exists():
                try:
                    self.artifact_store.clean_workspace(workspace, job.id)
                except ArtifactStoreError:
                    logger.exception(
                        "Owned workspace cleanup failed for preview job %s.", job.id
                    )

    def _run_topdown_job(self, job: JobRecord) -> None:
        workspace = None
        started = time.monotonic()
        resolver = self.topdown_resolver
        processor = self.topdown_processor
        artifact_store = self.topdown_artifact_store
        try:
            if resolver is None or processor is None or artifact_store is None:
                raise TopdownPreviewProcessingError(
                    "topdown_processor_unavailable",
                    "Top-down preview processing is unavailable.",
                )
            resolution = resolver.resolve(job.recording_id)
            if resolution.descriptor is None:
                message = (
                    "Top-down preview prerequisites are no longer available."
                    if resolution.diagnostic is None
                    else resolution.diagnostic.message
                )
                code = (
                    "topdown_prerequisites_changed"
                    if resolution.diagnostic is None
                    else resolution.diagnostic.code
                )
                raise TopdownPreviewProcessingError(code, message)
            descriptor = resolution.descriptor
            if descriptor.cache_identity != job.cache_identity:
                raise TopdownPreviewProcessingError(
                    "topdown_inputs_changed",
                    "Top-down preview inputs changed after this job was requested.",
                )

            workspace = artifact_store.create_workspace(job.id)
            output_path = workspace / "preview.mp4"
            result = processor.process(descriptor, output_path)
            validation = artifact_store.validate_preview(
                output_path,
                processor.profile,
                expected_width=result.output_width,
                expected_height=result.output_height,
                expected_frame_count=result.encoded_frame_count,
                measured_span_ns=result.measured_span_ns,
                expected_media_pts_sha256=result.media_pts_sha256,
            )
            manifest: dict[str, object] = {
                "schema_version": 1,
                "artifact_kind": TOPDOWN_PREVIEW_KIND,
                "cache_identity": job.cache_identity,
                "processor_version": TOPDOWN_PROCESSOR_VERSION,
                "encoder_identity": self.media_encoder_identity,
                "source": {
                    "video_role": "topdown_video",
                    "timestamps_role": "topdown_timestamps",
                    "timestamp_column": "unix_timestamp",
                },
                "timing": {
                    "timestamp_provenance": "csv_unix_timestamp",
                    "bounds": "measured",
                    "coverage_start_ns": str(result.coverage_start_ns),
                    "coverage_end_ns": str(result.coverage_end_ns),
                    "measured_span_ns": str(result.measured_span_ns),
                    "media_timescale": processor.profile.media_timescale,
                    "media_pts_sha256": result.media_pts_sha256,
                },
                "profile": processor.profile.identity_values(),
                "output": {
                    "file_name": "preview.mp4",
                    "mime_type": processor.profile.mime_type,
                    "size_bytes": validation.size_bytes,
                    "file_identity": {
                        "device_id": validation.device_id,
                        "inode": validation.inode,
                        "mtime_ns": validation.mtime_ns,
                    },
                    "width": validation.width,
                    "height": validation.height,
                    "codec": validation.codec,
                    "pixel_format": validation.pixel_format,
                    "duration_seconds": validation.duration_seconds,
                },
                "frames": {
                    "video": result.input_frame_count,
                    "timestamps": result.timestamp_count,
                    "encoded": result.encoded_frame_count,
                },
                "warnings": list(result.warnings),
            }
            current = resolver.resolve(job.recording_id)
            if (
                current.descriptor is None
                or current.descriptor.cache_identity != job.cache_identity
            ):
                raise TopdownPreviewProcessingError(
                    "topdown_inputs_changed",
                    "Top-down preview inputs changed during generation.",
                )
            published = artifact_store.publish(
                workspace,
                job.id,
                job.cache_identity,
                manifest,
                replace_conflicting=True,
            )
            self.repository.complete_job(
                job.id,
                ArtifactWrite(
                    recording_id=job.recording_id,
                    kind=job.kind,
                    cache_identity=job.cache_identity,
                    output_relative_path=published.output_relative_path,
                    mime_type=processor.profile.mime_type,
                    size_bytes=published.size_bytes,
                    coverage_start_ns=result.coverage_start_ns,
                    coverage_end_ns=result.coverage_end_ns,
                    manifest=manifest,
                ),
            )
            logger.info(
                "Top-down preview job %s succeeded in %.3f seconds (%s bytes).",
                job.id,
                time.monotonic() - started,
                published.size_bytes,
            )
        except (TopdownPreviewProcessingError, ArtifactStoreError) as error:
            self.repository.fail_job(job.id, error.code, error.safe_message)
            logger.warning(
                "Top-down preview job %s failed with code %s.",
                job.id,
                error.code,
                exc_info=True,
            )
        except Exception:
            self.repository.fail_job(
                job.id,
                "topdown_processing_failed",
                "Top-down preview generation failed unexpectedly. Request it again.",
            )
            logger.exception(
                "Top-down preview job %s failed unexpectedly.", job.id
            )
        finally:
            if (
                workspace is not None
                and workspace.exists()
                and artifact_store is not None
            ):
                try:
                    artifact_store.clean_workspace(workspace, job.id)
                except ArtifactStoreError:
                    logger.exception(
                        "Owned workspace cleanup failed for top-down job %s.", job.id
                    )

    def _run_imu_job(self, job: JobRecord) -> None:
        workspace = None
        started = time.monotonic()
        resolver = self.imu_resolver
        processor = self.imu_processor
        artifact_store = self.imu_artifact_store
        try:
            if resolver is None or processor is None or artifact_store is None:
                raise ImuSeriesProcessingError(
                    "imu_processor_unavailable", "IMU series processing is unavailable."
                )
            resolution = resolver.resolve(job.recording_id)
            if resolution.descriptor is None:
                message = (
                    "IMU series prerequisites are no longer available."
                    if resolution.diagnostic is None
                    else resolution.diagnostic.message
                )
                code = (
                    "imu_prerequisites_changed"
                    if resolution.diagnostic is None
                    else resolution.diagnostic.code
                )
                raise ImuSeriesProcessingError(code, message)
            descriptor = resolution.descriptor
            if descriptor.cache_identity != job.cache_identity:
                raise ImuSeriesProcessingError(
                    "imu_inputs_changed",
                    "IMU series inputs changed after this job was requested.",
                )

            workspace = artifact_store.create_workspace(job.id)
            output_path = workspace / "series.json"
            result = processor.process(descriptor, output_path)
            validation = artifact_store.validate_series(
                output_path,
                expected_schema_version=SERIES_SCHEMA_VERSION,
                expected_sample_count=result.sample_count,
                expected_finite_count=result.finite_count,
                expected_non_finite_count=result.non_finite_count,
                expected_coverage_start_ns=result.coverage_start_ns,
                expected_coverage_end_ns=result.coverage_end_ns,
                expected_minimum_value=result.minimum_value,
                expected_maximum_value=result.maximum_value,
            )
            manifest: dict[str, object] = {
                "schema_version": 1,
                "artifact_kind": IMU_SERIES_KIND,
                "cache_identity": job.cache_identity,
                "processor_version": IMU_PROCESSOR_VERSION,
                "series_schema_version": SERIES_SCHEMA_VERSION,
                "source": {
                    "topic": descriptor.topic.name,
                    "message_type": descriptor.topic.message_type,
                    "serialization_format": descriptor.topic.serialization_format,
                    "component": descriptor.component,
                    "display_label": IMU_DISPLAY_LABEL,
                    "units": IMU_UNITS,
                },
                "timing": {
                    "timestamp_provenance": "ros_record_timestamp",
                    "bounds": "measured",
                    "coverage_start_ns": str(result.coverage_start_ns),
                    "coverage_end_ns": str(result.coverage_end_ns),
                    "duplicate_timestamp_policy": DUPLICATE_TIMESTAMP_POLICY,
                },
                "samples": {
                    "source": result.sample_count,
                    "delivered": result.sample_count,
                    "finite": result.finite_count,
                    "non_finite": result.non_finite_count,
                    "duplicate_timestamps": result.duplicate_timestamp_count,
                    "minimum": result.minimum_value,
                    "maximum": result.maximum_value,
                    "non_finite_policy": NON_FINITE_POLICY,
                },
                "reduction": {"method": "none"},
                "output": {
                    "file_name": "series.json",
                    "mime_type": "application/json",
                    "size_bytes": validation.size_bytes,
                    "file_identity": {
                        "device_id": validation.device_id,
                        "inode": validation.inode,
                        "mtime_ns": validation.mtime_ns,
                    },
                },
                "warnings": list(result.warnings),
            }
            current = resolver.resolve(job.recording_id)
            if (
                current.descriptor is None
                or current.descriptor.cache_identity != job.cache_identity
            ):
                raise ImuSeriesProcessingError(
                    "imu_inputs_changed", "IMU series inputs changed during generation."
                )
            published = artifact_store.publish_series(
                workspace,
                job.id,
                job.cache_identity,
                manifest,
                replace_conflicting=True,
            )
            self.repository.complete_job(
                job.id,
                ArtifactWrite(
                    recording_id=job.recording_id,
                    kind=job.kind,
                    cache_identity=job.cache_identity,
                    output_relative_path=published.output_relative_path,
                    mime_type="application/json",
                    size_bytes=published.size_bytes,
                    coverage_start_ns=result.coverage_start_ns,
                    coverage_end_ns=result.coverage_end_ns,
                    manifest=manifest,
                ),
            )
            logger.info(
                "IMU series job %s succeeded in %.3f seconds (%s samples, %s bytes).",
                job.id,
                time.monotonic() - started,
                result.sample_count,
                published.size_bytes,
            )
        except (ImuSeriesProcessingError, ArtifactStoreError) as error:
            self.repository.fail_job(job.id, error.code, error.safe_message)
            logger.warning(
                "IMU series job %s failed with code %s.",
                job.id,
                error.code,
                exc_info=True,
            )
        except Exception:
            self.repository.fail_job(
                job.id,
                "imu_processing_failed",
                "IMU series generation failed unexpectedly. Request it again.",
            )
            logger.exception("IMU series job %s failed unexpectedly.", job.id)
        finally:
            if workspace is not None and workspace.exists() and artifact_store is not None:
                try:
                    artifact_store.clean_workspace(workspace, job.id)
                except ArtifactStoreError:
                    logger.exception(
                        "Owned workspace cleanup failed for IMU job %s.", job.id
                    )


def create_worker(config: AppConfig) -> SerialWorker:
    repository = ProcessingRepository(config.database_url)
    media_encoder_identity = encoder_identity()
    resolver = FrontSourceResolver(
        config.archive_root,
        repository,
        config.front_topic,
        config.preview_profile,
        media_encoder_identity,
    )
    artifact_store = ArtifactStore(
        config.derived_root, config.ffmpeg_path, config.ffprobe_path
    )
    topdown_artifact_store = ArtifactStore(
        config.derived_root,
        config.ffmpeg_path,
        config.ffprobe_path,
        TOPDOWN_PREVIEW_KIND,
    )
    topdown_resolver = TopdownSourceResolver(
        config.archive_root,
        repository,
        config.preview_profile,
        media_encoder_identity,
    )
    imu_artifact_store = ArtifactStore(
        config.derived_root,
        config.ffmpeg_path,
        config.ffprobe_path,
        IMU_SERIES_KIND,
    )
    imu_resolver = ImuSourceResolver(
        config.archive_root,
        repository,
        config.imu_topic,
        config.imu_component,
    )
    return SerialWorker(
        repository,
        resolver,
        FrontPreviewProcessor(config.preview_profile),
        artifact_store,
        config.front_topic,
        media_encoder_identity,
        topdown_resolver=topdown_resolver,
        topdown_processor=TopdownPreviewProcessor(config.preview_profile),
        topdown_artifact_store=topdown_artifact_store,
        imu_resolver=imu_resolver,
        imu_processor=ImuSeriesProcessor(),
        imu_artifact_store=imu_artifact_store,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    try:
        config = AppConfig.from_environment()
    except ConfigurationError as error:
        raise SystemExit(str(error)) from error
    worker = create_worker(config)
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    with open_connection(config.database_url) as lock_connection:
        locked = bool(
            lock_connection.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS locked",
                (WORKER_LOCK_NAME,),
            ).fetchone()["locked"]
        )
        if not locked:
            raise SystemExit("Another ROS Bag Analyser worker is already running.")
        interrupted = worker.recover_interrupted_jobs()
        if interrupted:
            logger.warning(
                "Marked %s interrupted processing job(s) failed.", len(interrupted)
            )
        while not stop_requested:
            if not worker.run_once():
                time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
