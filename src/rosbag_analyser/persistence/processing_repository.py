from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping, Protocol

from rosbag_analyser.estimation import (
    EstimateSample,
    MAX_ESTIMATE_SAMPLES,
    estimate_total_ms,
)

from .database import open_connection


FRONT_PREVIEW_KIND = "front_preview"
TOPDOWN_PREVIEW_KIND = "topdown_preview"
IMU_SERIES_KIND = "imu_series"
PROCESSING_KINDS = (FRONT_PREVIEW_KIND, TOPDOWN_PREVIEW_KIND, IMU_SERIES_KIND)
WORKER_LOCK_NAME = "rosbag_analyser_serial_worker"
QUEUE_LOCK_NAME = "rosbag_analyser_job_queue"


class AdmissionDiagnostic(Protocol):
    code: str
    message: str


@dataclass(frozen=True)
class ProcessingComponent:
    relative_path: str | None
    size_bytes: int | None
    mtime_ns: int | None
    condition: str


@dataclass(frozen=True)
class ProcessingSourceRecord:
    id: int
    archive_relative_path: str
    start_time_ns: int | None
    duration_ns: int | None
    ros_health: str
    metadata: ProcessingComponent | None
    database: ProcessingComponent | None
    topdown_video: ProcessingComponent | None = None
    topdown_timestamps: ProcessingComponent | None = None
    cache_identity_recording_id: int | None = None
    cache_identity_relative_path: str | None = None

    @property
    def identity_recording_id(self) -> int:
        return (
            self.id
            if self.cache_identity_recording_id is None
            else self.cache_identity_recording_id
        )

    @property
    def identity_relative_path(self) -> str:
        return (
            self.archive_relative_path
            if self.cache_identity_relative_path is None
            else self.cache_identity_relative_path
        )


@dataclass(frozen=True)
class ArtifactRecord:
    id: int
    recording_id: int
    kind: str
    cache_identity: str
    output_relative_path: str
    mime_type: str
    size_bytes: int
    coverage_start_ns: int
    coverage_end_ns: int
    manifest: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class JobRecord:
    id: int
    recording_id: int
    kind: str
    cache_identity: str
    state: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    work_units: int | None = None
    estimate_key: str | None = None
    estimated_total_ms: int | None = None
    estimate_method: str | None = None
    estimate_sample_count: int | None = None
    control_state: str = "none"
    execution_phase: str | None = None
    control_revision: int = 0
    last_pause_requested_at: datetime | None = None
    last_pause_acknowledged_at: datetime | None = None
    last_resumed_at: datetime | None = None
    accumulated_paused_ms: int = 0
    cancel_requested_at: datetime | None = None
    cancel_finished_at: datetime | None = None
    queue_order: int = 0


@dataclass(frozen=True)
class ArtifactWrite:
    recording_id: int
    kind: str
    cache_identity: str
    output_relative_path: str
    mime_type: str
    size_bytes: int
    coverage_start_ns: int
    coverage_end_ns: int
    manifest: dict[str, object]


@dataclass(frozen=True)
class RequestOutcome:
    artifact: ArtifactRecord | None = None
    job: JobRecord | None = None


@dataclass(frozen=True)
class ProcessingState:
    artifact: ArtifactRecord | None = None
    active_job: JobRecord | None = None
    latest_failed_job: JobRecord | None = None


@dataclass(frozen=True)
class PreparationTargetRecord:
    recording_id: int
    kind: str
    scan_generation: int
    planner_identity: str
    target_state: str
    cache_identity: str | None
    diagnostic_code: str | None
    diagnostic_message: str | None
    work_units: int | None


@dataclass(frozen=True)
class CurrentOutputRecord:
    target: PreparationTargetRecord
    artifact: ArtifactRecord | None = None
    active_job: JobRecord | None = None
    latest_failed_job: JobRecord | None = None


@dataclass(frozen=True)
class ScheduledOutput:
    kind: str
    outcome: str
    state: str
    target: PreparationTargetRecord | None = None
    artifact: ArtifactRecord | None = None
    job: JobRecord | None = None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None


@dataclass(frozen=True)
class PreparationSchedule:
    recording_id: int
    recording_found: bool
    outputs: tuple[ScheduledOutput, ...]


@dataclass(frozen=True)
class RetrySchedule:
    job_found: bool
    job_failed: bool
    output: ScheduledOutput | None = None


@dataclass(frozen=True)
class JobControlResult:
    job_found: bool
    outcome: str
    job: JobRecord | None = None
    recording_name: str = ""


@dataclass(frozen=True)
class BulkJobControlResult:
    items: tuple[JobControlResult, ...]


@dataclass(frozen=True)
class QueueReorderResult:
    outcome: str
    jobs: tuple[ProcessingJobViewRecord, ...]


@dataclass(frozen=True)
class ProcessingJobViewRecord:
    job: JobRecord
    recording_name: str
    output_size_bytes: int | None = None
    queue_position: int | None = None


@dataclass(frozen=True)
class ProcessingOverviewData:
    server_time: datetime
    running_count: int
    queued_count: int
    failed_count: int
    succeeded_count: int
    canceled_count: int
    running: ProcessingJobViewRecord | None
    queue: tuple[ProcessingJobViewRecord, ...]


class ProcessingRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_source(self, recording_id: int) -> ProcessingSourceRecord | None:
        with open_connection(self.database_url) as connection:
            recording = connection.execute(
                """
                SELECT id, archive_relative_path, start_time_ns, duration_ns,
                       ros_health, cache_identity_recording_id,
                       cache_identity_relative_path
                FROM recordings
                WHERE id = %s AND source_present = TRUE
                """,
                (recording_id,),
            ).fetchone()
            if recording is None:
                return None
            rows = connection.execute(
                """
                SELECT role, relative_path, size_bytes, mtime_ns, condition
                FROM source_components
                WHERE recording_id = %s
                  AND role IN (
                      'metadata', 'ros_database',
                      'topdown_video', 'topdown_timestamps'
                  )
                """,
                (recording_id,),
            ).fetchall()
        components = {
            str(row["role"]): _component_from_row(row)
            for row in rows
        }
        return ProcessingSourceRecord(
            id=int(recording["id"]),
            archive_relative_path=str(recording["archive_relative_path"]),
            start_time_ns=_optional_int(recording["start_time_ns"]),
            duration_ns=_optional_int(recording["duration_ns"]),
            ros_health=str(recording["ros_health"]),
            metadata=components.get("metadata"),
            database=components.get("ros_database"),
            topdown_video=components.get("topdown_video"),
            topdown_timestamps=components.get("topdown_timestamps"),
            cache_identity_recording_id=int(
                recording["cache_identity_recording_id"]
            ),
            cache_identity_relative_path=str(
                recording["cache_identity_relative_path"]
            ),
        )

    def get_artifact(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> ArtifactRecord | None:
        with open_connection(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity,
                       output_relative_path, mime_type, size_bytes,
                       coverage_start_ns, coverage_end_ns, manifest, created_at
                FROM artifacts
                WHERE recording_id = %s AND kind = %s AND cache_identity = %s
                """,
                (recording_id, kind, cache_identity),
            ).fetchone()
        return None if row is None else _artifact_from_row(row)

    def get_current_artifact_for_delivery(
        self,
        recording_id: int,
        kind: str,
        artifact_id: int,
        planner_identity: str,
    ) -> ArtifactRecord | None:
        """Return only an artifact owned by the current persisted output target."""
        if kind not in PROCESSING_KINDS:
            raise ValueError("The artifact kind is unsupported.")
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            row = connection.execute(
                """
                SELECT artifact.id, artifact.recording_id, artifact.kind,
                       artifact.cache_identity, artifact.output_relative_path,
                       artifact.mime_type, artifact.size_bytes,
                       artifact.coverage_start_ns, artifact.coverage_end_ns,
                       artifact.manifest, artifact.created_at
                FROM artifacts AS artifact
                JOIN preparation_targets AS target
                  ON target.recording_id = artifact.recording_id
                 AND target.kind = artifact.kind
                 AND target.cache_identity = artifact.cache_identity
                JOIN catalog_state AS catalog ON catalog.singleton = TRUE
                WHERE artifact.id = %s
                  AND artifact.recording_id = %s
                  AND artifact.kind = %s
                  AND target.scan_generation = catalog.successful_generation
                  AND target.planner_identity = %s
                  AND target.target_state = 'available'
                """,
                (artifact_id, recording_id, kind, planner_identity),
            ).fetchone()
        return None if row is None else _artifact_from_row(row)

    def get_current_state(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> ProcessingState:
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            artifact_row = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity,
                       output_relative_path, mime_type, size_bytes,
                       coverage_start_ns, coverage_end_ns, manifest, created_at
                FROM artifacts
                WHERE recording_id = %s AND kind = %s AND cache_identity = %s
                """,
                (recording_id, kind, cache_identity),
            ).fetchone()
            active_row = _select_active_job(
                connection, recording_id, kind, cache_identity
            )
            failed_row = _select_latest_failed_job(
                connection, recording_id, kind, cache_identity
            )
        return ProcessingState(
            artifact=(
                None if artifact_row is None else _artifact_from_row(artifact_row)
            ),
            active_job=None if active_row is None else _job_from_row(active_row),
            latest_failed_job=(
                None if failed_row is None else _job_from_row(failed_row)
            ),
        )

    def get_active_job(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> JobRecord | None:
        with open_connection(self.database_url) as connection:
            row = _select_active_job(
                connection, recording_id, kind, cache_identity
            )
        return None if row is None else _job_from_row(row)

    def get_latest_failed_job(
        self, recording_id: int, kind: str, cache_identity: str
    ) -> JobRecord | None:
        with open_connection(self.database_url) as connection:
            row = _select_latest_failed_job(
                connection, recording_id, kind, cache_identity
            )
        return None if row is None else _job_from_row(row)

    def request_job(
        self,
        recording_id: int,
        kind: str,
        cache_identity: str,
        *,
        invalid_artifact_id: int | None = None,
        work_units: int | None = None,
        estimate_key: str | None = None,
    ) -> RequestOutcome:
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            _lock_cache_identity(connection, kind, cache_identity)
            artifact_row = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity,
                       output_relative_path, mime_type, size_bytes,
                       coverage_start_ns, coverage_end_ns, manifest, created_at
                FROM artifacts
                WHERE recording_id = %s AND kind = %s AND cache_identity = %s
                FOR UPDATE
                """,
                (recording_id, kind, cache_identity),
            ).fetchone()
            if artifact_row is not None:
                if int(artifact_row["id"]) != invalid_artifact_id:
                    return RequestOutcome(artifact=_artifact_from_row(artifact_row))
                connection.execute(
                    "DELETE FROM artifacts WHERE id = %s",
                    (invalid_artifact_id,),
                )

            active_row = _select_active_job(
                connection, recording_id, kind, cache_identity
            )
            if active_row is not None:
                return RequestOutcome(job=_job_from_row(active_row))

            estimate_values = _estimate_values_for_new_job(
                connection, work_units, estimate_key
            )
            inserted = connection.execute(
                """
                INSERT INTO jobs (
                    recording_id, kind, cache_identity, state,
                    work_units, estimate_key, estimated_total_ms,
                    estimate_method, estimate_sample_count, queue_order
                )
                VALUES (%s, %s, %s, 'queued', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (kind, cache_identity)
                    WHERE state IN ('queued', 'running')
                DO NOTHING
                RETURNING id, recording_id, kind, cache_identity, state,
                          queued_at, started_at, finished_at,
                          error_code, error_message, work_units, estimate_key,
                          estimated_total_ms, estimate_method,
                          estimate_sample_count, control_state, execution_phase,
                          control_revision, last_pause_requested_at,
                          last_pause_acknowledged_at, last_resumed_at,
                          accumulated_paused_ms, cancel_requested_at,
                          cancel_finished_at, queue_order
                """,
                (
                    recording_id,
                    kind,
                    cache_identity,
                    work_units,
                    estimate_key,
                    estimate_values["estimated_total_ms"],
                    estimate_values["estimate_method"],
                    estimate_values["estimate_sample_count"],
                    _next_queue_order(connection),
                ),
            ).fetchone()
            if inserted is not None:
                return RequestOutcome(job=_job_from_row(inserted))

            active_row = _select_active_job(
                connection, recording_id, kind, cache_identity
            )
            if active_row is None:
                raise RuntimeError("The processing request could not be serialized.")
            return RequestOutcome(job=_job_from_row(active_row))

    def claim_next_job(self) -> JobRecord | None:
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            queued = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity, state,
                       queued_at, started_at, finished_at, error_code,
                       error_message, work_units, estimate_key,
                       estimated_total_ms, estimate_method,
                       estimate_sample_count, control_state, execution_phase,
                       control_revision, last_pause_requested_at,
                       last_pause_acknowledged_at, last_resumed_at,
                       accumulated_paused_ms, cancel_requested_at,
                       cancel_finished_at, queue_order
                FROM jobs
                WHERE state = 'queued'
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs AS running WHERE running.state = 'running'
                  )
                ORDER BY queue_order, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ).fetchone()
            if queued is None:
                return None
            estimate_values: dict[str, object] = {
                "estimated_total_ms": queued["estimated_total_ms"],
                "estimate_method": queued["estimate_method"],
                "estimate_sample_count": queued["estimate_sample_count"],
            }
            work_units = _optional_int(queued["work_units"])
            estimate_key = _optional_str(queued["estimate_key"])
            if estimate_values["estimate_method"] is None and work_units is not None and estimate_key is not None:
                frozen = _freeze_estimate(
                    connection,
                    estimate_key,
                    work_units,
                )
                estimate_values = {
                    "estimated_total_ms": frozen.estimated_total_ms,
                    "estimate_method": frozen.method,
                    "estimate_sample_count": frozen.sample_count,
                }
            row = connection.execute(
                """
                UPDATE jobs
                SET state = 'running', started_at = CURRENT_TIMESTAMP,
                    execution_phase = 'setup', control_state = 'none',
                    estimated_total_ms = %(estimated_total_ms)s,
                    estimate_method = %(estimate_method)s,
                    estimate_sample_count = %(estimate_sample_count)s
                WHERE id = %(job_id)s
                RETURNING id, recording_id, kind, cache_identity, state,
                          queued_at, started_at, finished_at,
                          error_code, error_message, work_units, estimate_key,
                          estimated_total_ms, estimate_method,
                          estimate_sample_count, control_state, execution_phase,
                          control_revision, last_pause_requested_at,
                          last_pause_acknowledged_at, last_resumed_at,
                          accumulated_paused_ms, cancel_requested_at,
                          cancel_finished_at, queue_order
                """,
                {"job_id": queued["id"], **estimate_values},
            ).fetchone()
        return None if row is None else _job_from_row(row)

    def get_current_outputs(
        self,
        recording_ids: tuple[int, ...] | None = None,
    ) -> tuple[CurrentOutputRecord, ...]:
        selected_ids = None if recording_ids is None else list(recording_ids)
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            target_rows = connection.execute(
                """
                SELECT target.recording_id, target.kind, target.scan_generation,
                       target.planner_identity, target.target_state,
                       target.cache_identity, target.diagnostic_code,
                       target.diagnostic_message, target.work_units
                FROM preparation_targets AS target
                WHERE (%s::bigint[] IS NULL OR target.recording_id = ANY (%s))
                ORDER BY target.recording_id,
                         CASE target.kind
                             WHEN 'front_preview' THEN 1
                             WHEN 'topdown_preview' THEN 2
                             WHEN 'imu_series' THEN 3
                         END
                """,
                (selected_ids, selected_ids),
            ).fetchall()
            if not target_rows:
                return ()
            artifact_rows = connection.execute(
                """
                SELECT artifact.id, artifact.recording_id, artifact.kind,
                       artifact.cache_identity, artifact.output_relative_path,
                       artifact.mime_type, artifact.size_bytes,
                       artifact.coverage_start_ns, artifact.coverage_end_ns,
                       artifact.manifest, artifact.created_at
                FROM artifacts AS artifact
                JOIN preparation_targets AS target
                  ON target.recording_id = artifact.recording_id
                 AND target.kind = artifact.kind
                 AND target.cache_identity = artifact.cache_identity
                WHERE (%s::bigint[] IS NULL OR artifact.recording_id = ANY (%s))
                """,
                (selected_ids, selected_ids),
            ).fetchall()
            active_rows = connection.execute(
                """
                SELECT job.id, job.recording_id, job.kind, job.cache_identity,
                       job.state, job.queued_at, job.started_at, job.finished_at,
                       job.error_code, job.error_message, job.work_units,
                       job.estimate_key, job.estimated_total_ms,
                       job.estimate_method, job.estimate_sample_count
                FROM jobs AS job
                JOIN preparation_targets AS target
                  ON target.recording_id = job.recording_id
                 AND target.kind = job.kind
                 AND target.cache_identity = job.cache_identity
                WHERE job.state IN ('queued', 'running')
                  AND (%s::bigint[] IS NULL OR job.recording_id = ANY (%s))
                """,
                (selected_ids, selected_ids),
            ).fetchall()
            failed_rows = connection.execute(
                """
                SELECT DISTINCT ON (job.recording_id, job.kind)
                       job.id, job.recording_id, job.kind, job.cache_identity,
                       job.state, job.queued_at, job.started_at, job.finished_at,
                       job.error_code, job.error_message, job.work_units,
                       job.estimate_key, job.estimated_total_ms,
                       job.estimate_method, job.estimate_sample_count
                FROM jobs AS job
                JOIN preparation_targets AS target
                  ON target.recording_id = job.recording_id
                 AND target.kind = job.kind
                 AND target.cache_identity = job.cache_identity
                WHERE job.state = 'failed'
                  AND (%s::bigint[] IS NULL OR job.recording_id = ANY (%s))
                ORDER BY job.recording_id, job.kind, job.finished_at DESC, job.id DESC
                """,
                (selected_ids, selected_ids),
            ).fetchall()
        artifacts = {
            (int(row["recording_id"]), str(row["kind"])): _artifact_from_row(row)
            for row in artifact_rows
        }
        active = {
            (int(row["recording_id"]), str(row["kind"])): _job_from_row(row)
            for row in active_rows
        }
        failed = {
            (int(row["recording_id"]), str(row["kind"])): _job_from_row(row)
            for row in failed_rows
        }
        return tuple(
            CurrentOutputRecord(
                target=_target_from_row(row),
                artifact=artifacts.get((int(row["recording_id"]), str(row["kind"]))),
                active_job=active.get((int(row["recording_id"]), str(row["kind"]))),
                latest_failed_job=failed.get(
                    (int(row["recording_id"]), str(row["kind"]))
                ),
            )
            for row in target_rows
        )

    def prepare_recording(
        self,
        recording_id: int,
        planner_identities: Mapping[str, str],
        *,
        output_kinds: tuple[str, ...] = PROCESSING_KINDS,
        invalid_artifact_ids: Mapping[str, int] | None = None,
        admission_diagnostic: AdmissionDiagnostic | None = None,
    ) -> PreparationSchedule:
        selected_kinds = tuple(kind for kind in PROCESSING_KINDS if kind in output_kinds)
        if not selected_kinds or len(output_kinds) != len(set(output_kinds)):
            raise ValueError("Select a unique non-empty set of supported outputs.")
        if set(selected_kinds) != set(output_kinds):
            raise ValueError("The preparation output kind is unsupported.")
        invalid_ids = {} if invalid_artifact_ids is None else invalid_artifact_ids
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            recording = connection.execute(
                """
                SELECT recording.id, recording.source_present,
                       recording.last_seen_generation,
                       state.successful_generation
                FROM recordings AS recording
                CROSS JOIN catalog_state AS state
                WHERE recording.id = %s AND state.singleton = TRUE
                FOR UPDATE OF recording
                """,
                (recording_id,),
            ).fetchone()
            if recording is None:
                return PreparationSchedule(recording_id, False, ())
            rows = connection.execute(
                """
                SELECT recording_id, kind, scan_generation, planner_identity,
                       target_state, cache_identity, diagnostic_code,
                       diagnostic_message, work_units
                FROM preparation_targets
                WHERE recording_id = %s
                ORDER BY CASE kind
                    WHEN 'front_preview' THEN 1
                    WHEN 'topdown_preview' THEN 2
                    WHEN 'imu_series' THEN 3
                END
                FOR UPDATE
                """,
                (recording_id,),
            ).fetchall()
            targets = {str(row["kind"]): _target_from_row(row) for row in rows}
            unavailable = (
                not bool(recording["source_present"])
                or int(recording["last_seen_generation"])
                != int(recording["successful_generation"])
                or not set(selected_kinds).issubset(targets)
                or any(
                    target.target_state != "available"
                    or target.scan_generation != int(recording["successful_generation"])
                    or target.planner_identity != planner_identities.get(kind)
                    for kind, target in targets.items()
                    if kind in selected_kinds
                )
            )
            if unavailable:
                return PreparationSchedule(
                    recording_id,
                    True,
                    tuple(
                        ScheduledOutput(
                            kind=kind,
                            outcome="unavailable",
                            state="unavailable",
                            target=targets.get(kind),
                        )
                        for kind in selected_kinds
                    ),
                )

            for kind in sorted(selected_kinds):
                target = targets[kind]
                assert target.cache_identity is not None
                _lock_cache_identity(connection, kind, target.cache_identity)

            outputs: list[ScheduledOutput] = []
            for kind in selected_kinds:
                target = targets[kind]
                assert target.cache_identity is not None
                artifact_row = _select_artifact(
                    connection, recording_id, kind, target.cache_identity, for_update=True
                )
                if artifact_row is not None:
                    artifact = _artifact_from_row(artifact_row)
                    if invalid_ids.get(kind) != artifact.id:
                        outputs.append(
                            ScheduledOutput(
                                kind, "ready_reused", "ready", target, artifact=artifact
                            )
                        )
                        continue
                    connection.execute("DELETE FROM artifacts WHERE id = %s", (artifact.id,))

                active_row = _select_active_job(
                    connection, recording_id, kind, target.cache_identity
                )
                if active_row is not None:
                    job = _job_from_row(active_row)
                    outputs.append(
                        ScheduledOutput(
                            kind,
                            "active_reused",
                            "queued" if job.state == "queued" else "processing",
                            target,
                            job=job,
                        )
                    )
                    continue
                failed_before = _select_latest_failed_job(
                    connection, recording_id, kind, target.cache_identity
                )
                if admission_diagnostic is not None:
                    outputs.append(
                        ScheduledOutput(
                            kind,
                            "unavailable",
                            "unavailable",
                            target,
                            diagnostic_code=admission_diagnostic.code,
                            diagnostic_message=admission_diagnostic.message,
                        )
                    )
                    continue
                job = _insert_v1_job(connection, target)
                outputs.append(
                    ScheduledOutput(
                        kind,
                        "retry_queued" if failed_before is not None else "queued",
                        "queued",
                        target,
                        job=job,
                    )
                )
        return PreparationSchedule(recording_id, True, tuple(outputs))

    def retry_failed_job(
        self,
        failed_job_id: int,
        planner_identities: Mapping[str, str],
        *,
        invalid_artifact_id: int | None = None,
        admission_diagnostic: AdmissionDiagnostic | None = None,
    ) -> RetrySchedule:
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            failed = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity, state,
                       control_state, execution_phase
                FROM jobs
                WHERE id = %s
                FOR UPDATE
                """,
                (failed_job_id,),
            ).fetchone()
            if failed is None:
                return RetrySchedule(False, False)
            if str(failed["state"]) != "failed":
                return RetrySchedule(True, False)
            recording_id = int(failed["recording_id"])
            kind = str(failed["kind"])
            target_row = connection.execute(
                """
                SELECT target.recording_id, target.kind, target.scan_generation,
                       target.planner_identity, target.target_state,
                       target.cache_identity, target.diagnostic_code,
                       target.diagnostic_message, target.work_units,
                       recording.source_present, recording.last_seen_generation,
                       state.successful_generation
                FROM preparation_targets AS target
                JOIN recordings AS recording ON recording.id = target.recording_id
                CROSS JOIN catalog_state AS state
                WHERE target.recording_id = %s
                  AND target.kind = %s
                  AND state.singleton = TRUE
                FOR UPDATE OF target, recording
                """,
                (recording_id, kind),
            ).fetchone()
            if target_row is None:
                return RetrySchedule(
                    True,
                    True,
                    ScheduledOutput(kind, "unavailable", "unavailable"),
                )
            target = _target_from_row(target_row)
            if (
                not bool(target_row["source_present"])
                or int(target_row["last_seen_generation"])
                != int(target_row["successful_generation"])
                or target.scan_generation != int(target_row["successful_generation"])
                or target.target_state != "available"
                or target.cache_identity is None
                or target.planner_identity != planner_identities.get(kind)
            ):
                return RetrySchedule(
                    True,
                    True,
                    ScheduledOutput(kind, "unavailable", "unavailable", target),
                )
            _lock_cache_identity(connection, kind, target.cache_identity)
            artifact_row = _select_artifact(
                connection,
                recording_id,
                kind,
                target.cache_identity,
                for_update=True,
            )
            if artifact_row is not None:
                artifact = _artifact_from_row(artifact_row)
                if artifact.id != invalid_artifact_id:
                    return RetrySchedule(
                        True,
                        True,
                        ScheduledOutput(
                            kind,
                            "ready_reused",
                            "ready",
                            target,
                            artifact=artifact,
                        ),
                    )
                connection.execute("DELETE FROM artifacts WHERE id = %s", (artifact.id,))
            active = _select_active_job(
                connection,
                recording_id,
                kind,
                target.cache_identity,
            )
            if active is not None:
                job = _job_from_row(active)
                return RetrySchedule(
                    True,
                    True,
                    ScheduledOutput(
                        kind,
                        "active_reused",
                        "queued" if job.state == "queued" else "processing",
                        target,
                        job=job,
                    ),
                )
            if admission_diagnostic is not None:
                return RetrySchedule(
                    True,
                    True,
                    ScheduledOutput(
                        kind,
                        "unavailable",
                        "unavailable",
                        target,
                        diagnostic_code=admission_diagnostic.code,
                        diagnostic_message=admission_diagnostic.message,
                    ),
                )
            job = _insert_v1_job(connection, target)
            return RetrySchedule(
                True,
                True,
                ScheduledOutput(
                    kind,
                    "retry_queued",
                    "queued",
                    target,
                    job=job,
                ),
            )

    def processing_overview(self, *, queue_limit: int) -> ProcessingOverviewData:
        if queue_limit <= 0:
            raise ValueError("The queue overview limit must be positive.")
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            count_row = connection.execute(
                """
                WITH latest_failures AS (
                    SELECT DISTINCT ON (job.recording_id, job.kind)
                           job.id, job.recording_id, job.kind, job.cache_identity
                    FROM jobs AS job
                    JOIN preparation_targets AS target
                      ON target.recording_id = job.recording_id
                     AND target.kind = job.kind
                     AND target.cache_identity = job.cache_identity
                    WHERE job.state = 'failed'
                    ORDER BY job.recording_id, job.kind,
                             job.finished_at DESC, job.id DESC
                ), actionable_failures AS (
                    SELECT failure.id
                    FROM latest_failures AS failure
                    WHERE NOT EXISTS (
                        SELECT 1 FROM jobs AS active
                        WHERE active.recording_id = failure.recording_id
                          AND active.kind = failure.kind
                          AND active.cache_identity = failure.cache_identity
                          AND active.state IN ('queued', 'running')
                    )
                      AND NOT EXISTS (
                        SELECT 1 FROM artifacts AS artifact
                        WHERE artifact.recording_id = failure.recording_id
                          AND artifact.kind = failure.kind
                          AND artifact.cache_identity = failure.cache_identity
                    )
                )
                SELECT CURRENT_TIMESTAMP AS server_time,
                       (SELECT count(*) FROM jobs WHERE state = 'running') AS running_count,
                       (SELECT count(*) FROM jobs WHERE state = 'queued') AS queued_count,
                       (SELECT count(*) FROM actionable_failures) AS failed_count,
                       (SELECT count(*) FROM jobs WHERE state = 'succeeded') AS succeeded_count,
                       (SELECT count(*) FROM jobs WHERE state = 'canceled') AS canceled_count
                """
            ).fetchone()
            assert count_row is not None
            running_row = connection.execute(
                """
                SELECT job.id, job.recording_id, job.kind, job.cache_identity,
                       job.state, job.queued_at, job.started_at, job.finished_at,
                       job.error_code, job.error_message, job.work_units,
                       job.estimate_key, job.estimated_total_ms,
                       job.estimate_method, job.estimate_sample_count,
                       job.control_state, job.execution_phase,
                       job.control_revision, job.last_pause_requested_at,
                       job.last_pause_acknowledged_at, job.last_resumed_at,
                       job.accumulated_paused_ms, job.cancel_requested_at,
                       job.cancel_finished_at, job.queue_order,
                       recording.display_name
                FROM jobs AS job
                JOIN recordings AS recording ON recording.id = job.recording_id
                WHERE job.state = 'running'
                ORDER BY job.started_at, job.id
                LIMIT 1
                """
            ).fetchone()
            queue_rows = connection.execute(
                """
                SELECT job.id, job.recording_id, job.kind, job.cache_identity,
                       job.state, job.queued_at, job.started_at, job.finished_at,
                       job.error_code, job.error_message, job.work_units,
                       job.estimate_key, job.estimated_total_ms,
                       job.estimate_method, job.estimate_sample_count,
                       job.control_state, job.execution_phase,
                       job.control_revision, job.last_pause_requested_at,
                       job.last_pause_acknowledged_at, job.last_resumed_at,
                       job.accumulated_paused_ms, job.cancel_requested_at,
                       job.cancel_finished_at, job.queue_order,
                       recording.display_name,
                       row_number() OVER (ORDER BY job.queue_order, job.id) AS queue_position
                FROM jobs AS job
                JOIN recordings AS recording ON recording.id = job.recording_id
                WHERE job.state = 'queued'
                ORDER BY job.queue_order, job.id
                LIMIT %s
                """,
                (queue_limit,),
            ).fetchall()
        return ProcessingOverviewData(
            server_time=count_row["server_time"],  # type: ignore[arg-type]
            running_count=int(count_row["running_count"]),
            queued_count=int(count_row["queued_count"]),
            failed_count=int(count_row["failed_count"]),
            succeeded_count=int(count_row["succeeded_count"]),
            canceled_count=int(count_row["canceled_count"]),
            running=None if running_row is None else _job_view_from_row(running_row),
            queue=tuple(_job_view_from_row(row) for row in queue_rows),
        )

    def list_processing_jobs(
        self,
        view: str,
        *,
        limit: int,
        cursor: tuple[datetime | int, int] | None = None,
        search: str = "",
    ) -> tuple[ProcessingJobViewRecord, ...]:
        if view not in {"queued", "failed", "history", "canceled"}:
            raise ValueError("The processing view is invalid.")
        if limit <= 0:
            raise ValueError("The processing limit must be positive.")
        pattern = f"%{_escape_like(search)}%"
        cursor_value = None if cursor is None else cursor[0]
        cursor_id = None if cursor is None else cursor[1]
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            if view == "queued":
                rows = connection.execute(
                    """
                    WITH positioned AS (
                        SELECT job.id, job.recording_id, job.kind,
                               job.cache_identity, job.state, job.queued_at,
                               job.started_at, job.finished_at, job.error_code,
                               job.error_message, job.work_units, job.estimate_key,
                               job.estimated_total_ms, job.estimate_method,
                               job.estimate_sample_count, job.control_state,
                               job.execution_phase, job.control_revision,
                               job.last_pause_requested_at,
                               job.last_pause_acknowledged_at,
                               job.last_resumed_at, job.accumulated_paused_ms,
                               job.cancel_requested_at, job.cancel_finished_at,
                               job.queue_order, recording.display_name,
                               row_number() OVER (
                                   ORDER BY job.queue_order, job.id
                               ) AS queue_position
                        FROM jobs AS job
                        JOIN recordings AS recording
                          ON recording.id = job.recording_id
                        WHERE job.state = 'queued'
                    )
                    SELECT * FROM positioned
                    WHERE (%s = '' OR display_name ILIKE %s ESCAPE '\\')
                      AND (
                          %s::bigint IS NULL
                          OR (queue_order, id) > (%s::bigint, %s::bigint)
                      )
                    ORDER BY queue_order, id
                    LIMIT %s
                    """,
                    (
                        search,
                        pattern,
                        cursor_value,
                        cursor_value,
                        cursor_id,
                        limit,
                    ),
                ).fetchall()
            elif view == "failed":
                rows = connection.execute(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (job.recording_id, job.kind)
                               job.id, job.recording_id, job.kind,
                               job.cache_identity, job.state, job.queued_at,
                               job.started_at, job.finished_at, job.error_code,
                               job.error_message, job.work_units, job.estimate_key,
                               job.estimated_total_ms, job.estimate_method,
                               job.estimate_sample_count, recording.display_name
                        FROM jobs AS job
                        JOIN recordings AS recording
                          ON recording.id = job.recording_id
                        JOIN preparation_targets AS target
                          ON target.recording_id = job.recording_id
                         AND target.kind = job.kind
                         AND target.cache_identity = job.cache_identity
                        WHERE job.state = 'failed'
                        ORDER BY job.recording_id, job.kind,
                                 job.finished_at DESC, job.id DESC
                    )
                    SELECT latest.*
                    FROM latest
                    WHERE NOT EXISTS (
                        SELECT 1 FROM jobs AS active
                        WHERE active.recording_id = latest.recording_id
                          AND active.kind = latest.kind
                          AND active.cache_identity = latest.cache_identity
                          AND active.state IN ('queued', 'running')
                    )
                      AND NOT EXISTS (
                        SELECT 1 FROM artifacts AS artifact
                        WHERE artifact.recording_id = latest.recording_id
                          AND artifact.kind = latest.kind
                          AND artifact.cache_identity = latest.cache_identity
                    )
                      AND (%s = '' OR latest.display_name ILIKE %s ESCAPE '\\')
                      AND (
                          %s::timestamptz IS NULL
                          OR (latest.finished_at, latest.id)
                             < (%s::timestamptz, %s::bigint)
                      )
                    ORDER BY latest.finished_at DESC, latest.id DESC
                    LIMIT %s
                    """,
                    (
                        search,
                        pattern,
                        cursor_value,
                        cursor_value,
                        cursor_id,
                        limit,
                    ),
                ).fetchall()
            else:
                terminal_state = "succeeded" if view == "history" else "canceled"
                rows = connection.execute(
                    """
                    SELECT job.id, job.recording_id, job.kind,
                           job.cache_identity, job.state, job.queued_at,
                           job.started_at, job.finished_at, job.error_code,
                           job.error_message, job.work_units, job.estimate_key,
                           job.estimated_total_ms, job.estimate_method,
                           job.estimate_sample_count, recording.display_name,
                           artifact.size_bytes AS output_size_bytes
                    FROM jobs AS job
                    JOIN recordings AS recording ON recording.id = job.recording_id
                    LEFT JOIN artifacts AS artifact
                      ON artifact.recording_id = job.recording_id
                     AND artifact.kind = job.kind
                     AND artifact.cache_identity = job.cache_identity
                    WHERE job.state = %s
                      AND (%s = '' OR recording.display_name ILIKE %s ESCAPE '\\')
                      AND (
                          %s::timestamptz IS NULL
                          OR (job.finished_at, job.id)
                             < (%s::timestamptz, %s::bigint)
                      )
                    ORDER BY job.finished_at DESC, job.id DESC
                    LIMIT %s
                    """,
                    (
                        terminal_state,
                        search,
                        pattern,
                        cursor_value,
                        cursor_value,
                        cursor_id,
                        limit,
                    ),
                ).fetchall()
        return tuple(_job_view_from_row(row) for row in rows)

    def worker_online(self, lock_name: str) -> bool:
        with open_connection(self.database_url) as connection:
            acquired = bool(
                connection.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s)) AS acquired",
                    (lock_name,),
                ).fetchone()["acquired"]
            )
            if acquired:
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    (lock_name,),
                )
                return False
            return True

    def request_pause(self, job_id: int) -> JobControlResult:
        with open_connection(self.database_url) as connection:
            row = _select_job_for_update(connection, job_id)
            if row is None:
                return JobControlResult(False, "not_found")
            job = _job_from_row(row)
            recording_name = str(row["display_name"])
            if job.state != "running" or job.execution_phase == "publishing":
                return JobControlResult(True, "conflict", job, recording_name)
            if job.control_state == "paused":
                return JobControlResult(True, "already_paused", job, recording_name)
            if job.control_state == "pause_requested":
                return JobControlResult(True, "already_requested", job, recording_name)
            if job.control_state != "none":
                return JobControlResult(True, "conflict", job, recording_name)
            updated = connection.execute(
                """
                UPDATE jobs
                SET control_state = 'pause_requested',
                    last_pause_requested_at = CURRENT_TIMESTAMP,
                    control_revision = control_revision + 1
                WHERE id = %s
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            assert updated is not None
            return JobControlResult(
                True, "requested", _job_from_row(updated), recording_name
            )

    def request_resume(self, job_id: int) -> JobControlResult:
        with open_connection(self.database_url) as connection:
            row = _select_job_for_update(connection, job_id)
            if row is None:
                return JobControlResult(False, "not_found")
            job = _job_from_row(row)
            recording_name = str(row["display_name"])
            if job.state != "running":
                return JobControlResult(True, "conflict", job, recording_name)
            if job.control_state == "none":
                return JobControlResult(True, "already_running", job, recording_name)
            if job.control_state not in {"pause_requested", "paused"}:
                return JobControlResult(True, "conflict", job, recording_name)
            updated = connection.execute(
                """
                UPDATE jobs
                SET accumulated_paused_ms = accumulated_paused_ms + CASE
                        WHEN control_state = 'paused'
                             AND last_pause_acknowledged_at IS NOT NULL
                        THEN GREATEST(
                            0,
                            floor(extract(epoch FROM (
                                CURRENT_TIMESTAMP - last_pause_acknowledged_at
                            )) * 1000)::bigint
                        )
                        ELSE 0
                    END,
                    control_state = 'none',
                    last_resumed_at = CURRENT_TIMESTAMP,
                    control_revision = control_revision + 1
                WHERE id = %s
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            assert updated is not None
            return JobControlResult(
                True, "resumed", _job_from_row(updated), recording_name
            )

    def cancel_job(self, job_id: int) -> JobControlResult:
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            return _cancel_job_locked(connection, job_id)

    def cancel_jobs(self, job_ids: tuple[int, ...]) -> BulkJobControlResult:
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            indexed: dict[int, JobControlResult] = {}
            for job_id in sorted(job_ids):
                indexed[job_id] = _cancel_job_locked(connection, job_id)
            return BulkJobControlResult(tuple(indexed[job_id] for job_id in job_ids))

    def reorder_jobs(
        self, job_ids: tuple[int, ...], direction: str
    ) -> QueueReorderResult:
        if direction not in {"earlier", "later"}:
            raise ValueError("The queue direction is invalid.")
        with open_connection(self.database_url) as connection:
            _lock_job_queue(connection)
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE state = 'queued'
                ORDER BY queue_order, id
                FOR UPDATE
                """
            ).fetchall()
            by_id = {int(row["id"]): row for row in rows}
            if any(job_id not in by_id for job_id in job_ids):
                return QueueReorderResult("conflict", ())
            selected = set(job_ids)
            ordered = list(rows)
            if direction == "earlier":
                for index in range(1, len(ordered)):
                    if (
                        int(ordered[index]["id"]) in selected
                        and int(ordered[index - 1]["id"]) not in selected
                    ):
                        ordered[index - 1], ordered[index] = (
                            ordered[index],
                            ordered[index - 1],
                        )
            else:
                for index in range(len(ordered) - 2, -1, -1):
                    if (
                        int(ordered[index]["id"]) in selected
                        and int(ordered[index + 1]["id"]) not in selected
                    ):
                        ordered[index], ordered[index + 1] = (
                            ordered[index + 1],
                            ordered[index],
                        )
            for queue_order, row in enumerate(ordered, start=1):
                connection.execute(
                    """
                    UPDATE jobs
                    SET queue_order = %s, control_revision = control_revision + 1
                    WHERE id = %s AND queue_order <> %s
                    """,
                    (queue_order, row["id"], queue_order),
                )
            refreshed = connection.execute(
                """
                SELECT job.*, recording.display_name
                FROM jobs AS job
                JOIN recordings AS recording ON recording.id = job.recording_id
                WHERE job.id = ANY (%s) AND job.state = 'queued'
                ORDER BY job.queue_order, job.id
                """,
                (list(job_ids),),
            ).fetchall()
            return QueueReorderResult(
                "reordered",
                tuple(
                    ProcessingJobViewRecord(
                        _job_from_row(row), str(row["display_name"])
                    )
                    for row in refreshed
                ),
            )

    def worker_checkpoint(self, job_id: int, phase: str) -> JobRecord:
        if phase not in {"setup", "processing", "validating", "cleanup"}:
            raise ValueError("The worker phase is invalid.")
        with open_connection(self.database_url) as connection:
            row = _select_job_for_update(connection, job_id)
            if row is None:
                raise RuntimeError("The worker job no longer exists.")
            job = _job_from_row(row)
            if job.state != "running":
                return job
            if job.control_state != "cancel_requested" and job.execution_phase != phase:
                row = connection.execute(
                    "UPDATE jobs SET execution_phase = %s WHERE id = %s RETURNING *",
                    (phase, job_id),
                ).fetchone()
                assert row is not None
                job = _job_from_row(row)
            return job

    def acknowledge_pause(self, job_id: int) -> JobRecord:
        with open_connection(self.database_url) as connection:
            row = _select_job_for_update(connection, job_id)
            if row is None:
                raise RuntimeError("The worker job no longer exists.")
            job = _job_from_row(row)
            if job.state == "running" and job.control_state == "pause_requested":
                row = connection.execute(
                    """
                    UPDATE jobs
                    SET control_state = 'paused',
                        last_pause_acknowledged_at = CURRENT_TIMESTAMP,
                        control_revision = control_revision + 1
                    WHERE id = %s
                    RETURNING *
                    """,
                    (job_id,),
                ).fetchone()
                assert row is not None
                return _job_from_row(row)
            return job

    def enter_publishing(self, job_id: int) -> JobRecord:
        with open_connection(self.database_url) as connection:
            row = _select_job_for_update(connection, job_id)
            if row is None:
                raise RuntimeError("The worker job no longer exists.")
            job = _job_from_row(row)
            if job.state == "running" and job.control_state == "none":
                row = connection.execute(
                    """
                    UPDATE jobs SET execution_phase = 'publishing'
                    WHERE id = %s
                    RETURNING *
                    """,
                    (job_id,),
                ).fetchone()
                assert row is not None
                return _job_from_row(row)
            return job

    def begin_cancel_cleanup(self, job_id: int) -> JobRecord:
        with open_connection(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE jobs SET execution_phase = 'cleanup'
                WHERE id = %s AND state = 'running'
                  AND control_state = 'cancel_requested'
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("Only a cancel-requested job can be cleaned.")
            return _job_from_row(row)

    def complete_cancellation(self, job_id: int) -> JobRecord:
        with open_connection(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE jobs
                SET state = 'canceled', control_state = 'none',
                    execution_phase = NULL, finished_at = CURRENT_TIMESTAMP,
                    cancel_finished_at = CURRENT_TIMESTAMP,
                    control_revision = control_revision + 1
                WHERE id = %s AND state = 'running'
                  AND control_state = 'cancel_requested'
                  AND execution_phase = 'cleanup'
                RETURNING *
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("The cancellation could not be completed safely.")
            return _job_from_row(row)

    def complete_job(self, job_id: int, artifact: ArtifactWrite) -> ArtifactRecord:
        with open_connection(self.database_url) as connection:
            _lock_cache_identity(connection, artifact.kind, artifact.cache_identity)
            job = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity, state,
                       control_state, execution_phase
                FROM jobs
                WHERE id = %s
                FOR UPDATE
                """,
                (job_id,),
            ).fetchone()
            if (
                job is None
                or str(job["state"]) != "running"
                or int(job["recording_id"]) != artifact.recording_id
                or str(job["kind"]) != artifact.kind
                or str(job["cache_identity"]) != artifact.cache_identity
                or str(job["control_state"]) != "none"
                or str(job["execution_phase"]) != "publishing"
            ):
                raise RuntimeError("The running job no longer matches its artifact.")

            connection.execute(
                """
                INSERT INTO artifacts (
                    recording_id, kind, cache_identity, output_relative_path,
                    mime_type, size_bytes, coverage_start_ns, coverage_end_ns,
                    manifest
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (kind, cache_identity) DO NOTHING
                """,
                (
                    artifact.recording_id,
                    artifact.kind,
                    artifact.cache_identity,
                    artifact.output_relative_path,
                    artifact.mime_type,
                    artifact.size_bytes,
                    artifact.coverage_start_ns,
                    artifact.coverage_end_ns,
                    json.dumps(artifact.manifest, sort_keys=True),
                ),
            )
            artifact_row = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity,
                       output_relative_path, mime_type, size_bytes,
                       coverage_start_ns, coverage_end_ns, manifest, created_at
                FROM artifacts
                WHERE kind = %s AND cache_identity = %s
                """,
                (artifact.kind, artifact.cache_identity),
            ).fetchone()
            if artifact_row is None:
                raise RuntimeError("The validated artifact was not recorded.")
            connection.execute(
                """
                UPDATE jobs
                SET state = 'succeeded', finished_at = CURRENT_TIMESTAMP,
                    control_state = 'none', execution_phase = NULL
                WHERE id = %s
                """,
                (job_id,),
            )
        return _artifact_from_row(artifact_row)

    def fail_job(self, job_id: int, code: str, message: str) -> None:
        with open_connection(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE jobs
                SET state = 'failed', finished_at = CURRENT_TIMESTAMP,
                    error_code = %s, error_message = %s,
                    accumulated_paused_ms = accumulated_paused_ms + CASE
                        WHEN control_state = 'paused'
                             AND last_pause_acknowledged_at IS NOT NULL
                        THEN GREATEST(
                            0,
                            floor(extract(epoch FROM (
                                CURRENT_TIMESTAMP - last_pause_acknowledged_at
                            )) * 1000)::bigint
                        )
                        ELSE 0
                    END,
                    control_state = 'none', execution_phase = NULL
                WHERE id = %s AND state = 'running'
                RETURNING id
                """,
                (code, message[:500], job_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("Only a running job can fail.")

    def mark_running_jobs_interrupted(self) -> tuple[int, ...]:
        with open_connection(self.database_url) as connection:
            rows = connection.execute(
                """
                UPDATE jobs
                SET state = 'failed', finished_at = CURRENT_TIMESTAMP,
                    error_code = 'worker_interrupted',
                    error_message = CASE kind
                        WHEN 'front_preview'
                            THEN 'Preview generation was interrupted. Request it again.'
                        WHEN 'topdown_preview'
                            THEN 'Top-down preview generation was interrupted. Request it again.'
                        ELSE 'IMU series generation was interrupted. Request it again.'
                    END,
                    accumulated_paused_ms = accumulated_paused_ms + CASE
                        WHEN control_state = 'paused'
                             AND last_pause_acknowledged_at IS NOT NULL
                        THEN GREATEST(
                            0,
                            floor(extract(epoch FROM (
                                CURRENT_TIMESTAMP - last_pause_acknowledged_at
                            )) * 1000)::bigint
                        )
                        ELSE 0
                    END,
                    control_state = 'none', execution_phase = NULL
                WHERE state = 'running'
                RETURNING id
                """
            ).fetchall()
        return tuple(int(row["id"]) for row in rows)


def _select_active_job(
    connection: Any, recording_id: int, kind: str, cache_identity: str
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT id, recording_id, kind, cache_identity, state, queued_at,
               started_at, finished_at, error_code, error_message,
               work_units, estimate_key, estimated_total_ms,
               estimate_method, estimate_sample_count, control_state,
               execution_phase, control_revision, last_pause_requested_at,
               last_pause_acknowledged_at, last_resumed_at,
               accumulated_paused_ms, cancel_requested_at,
               cancel_finished_at, queue_order
        FROM jobs
        WHERE recording_id = %s AND kind = %s AND cache_identity = %s
          AND state IN ('queued', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        (recording_id, kind, cache_identity),
    ).fetchone()


def _select_job_for_update(connection: Any, job_id: int) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT job.*, recording.display_name
        FROM jobs AS job
        JOIN recordings AS recording ON recording.id = job.recording_id
        WHERE job.id = %s
        FOR UPDATE OF job
        """,
        (job_id,),
    ).fetchone()


def _cancel_job_locked(connection: Any, job_id: int) -> JobControlResult:
    row = _select_job_for_update(connection, job_id)
    if row is None:
        return JobControlResult(False, "not_found")
    job = _job_from_row(row)
    recording_name = str(row["display_name"])
    if job.state == "queued":
        updated = connection.execute(
            """
            UPDATE jobs
            SET state = 'canceled', finished_at = CURRENT_TIMESTAMP,
                cancel_requested_at = CURRENT_TIMESTAMP,
                cancel_finished_at = CURRENT_TIMESTAMP,
                control_revision = control_revision + 1
            WHERE id = %s
            RETURNING *
            """,
            (job_id,),
        ).fetchone()
        assert updated is not None
        return JobControlResult(
            True, "canceled", _job_from_row(updated), recording_name
        )
    if job.state == "running":
        if job.execution_phase == "publishing":
            return JobControlResult(
                True, "already_finalizing", job, recording_name
            )
        if job.control_state == "cancel_requested":
            return JobControlResult(
                True, "already_requested", job, recording_name
            )
        updated = connection.execute(
            """
            UPDATE jobs
            SET accumulated_paused_ms = accumulated_paused_ms + CASE
                    WHEN control_state = 'paused'
                         AND last_pause_acknowledged_at IS NOT NULL
                    THEN GREATEST(
                        0,
                        floor(extract(epoch FROM (
                            CURRENT_TIMESTAMP - last_pause_acknowledged_at
                        )) * 1000)::bigint
                    )
                    ELSE 0
                END,
                control_state = 'cancel_requested',
                cancel_requested_at = COALESCE(
                    cancel_requested_at, CURRENT_TIMESTAMP
                ),
                control_revision = control_revision + 1
            WHERE id = %s
            RETURNING *
            """,
            (job_id,),
        ).fetchone()
        assert updated is not None
        return JobControlResult(
            True, "requested", _job_from_row(updated), recording_name
        )
    if job.state == "canceled":
        return JobControlResult(True, "already_canceled", job, recording_name)
    return JobControlResult(True, "conflict", job, recording_name)


def _select_latest_failed_job(
    connection: Any, recording_id: int, kind: str, cache_identity: str
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT id, recording_id, kind, cache_identity, state, queued_at,
               started_at, finished_at, error_code, error_message,
               work_units, estimate_key, estimated_total_ms,
               estimate_method, estimate_sample_count, control_state,
               execution_phase, control_revision, last_pause_requested_at,
               last_pause_acknowledged_at, last_resumed_at,
               accumulated_paused_ms, cancel_requested_at,
               cancel_finished_at, queue_order
        FROM jobs
        WHERE recording_id = %s AND kind = %s AND cache_identity = %s
          AND state = 'failed'
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """,
        (recording_id, kind, cache_identity),
    ).fetchone()


def _lock_cache_identity(connection: Any, kind: str, cache_identity: str) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{kind}:{cache_identity}",),
    )


def _lock_job_queue(connection: Any) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        (QUEUE_LOCK_NAME,),
    )


def _next_queue_order(connection: Any) -> int:
    row = connection.execute(
        "SELECT nextval('jobs_queue_order_seq') AS next_order"
    ).fetchone()
    return 1 if row is None else int(row["next_order"])


def _select_artifact(
    connection: Any,
    recording_id: int,
    kind: str,
    cache_identity: str,
    *,
    for_update: bool = False,
) -> dict[str, object] | None:
    lock_clause = "FOR UPDATE" if for_update else ""
    return connection.execute(
        f"""
        SELECT id, recording_id, kind, cache_identity,
               output_relative_path, mime_type, size_bytes,
               coverage_start_ns, coverage_end_ns, manifest, created_at
        FROM artifacts
        WHERE recording_id = %s AND kind = %s AND cache_identity = %s
        {lock_clause}
        """,
        (recording_id, kind, cache_identity),
    ).fetchone()


def _insert_v1_job(
    connection: Any,
    target: PreparationTargetRecord,
) -> JobRecord:
    if target.cache_identity is None or target.work_units is None:
        raise RuntimeError("Only an available preparation target can be queued.")
    estimate_values = _estimate_values_for_new_job(
        connection, target.work_units, target.planner_identity
    )
    row = connection.execute(
        """
        INSERT INTO jobs (
            recording_id, kind, cache_identity, state, work_units, estimate_key,
            estimated_total_ms, estimate_method, estimate_sample_count,
            queue_order
        ) VALUES (%s, %s, %s, 'queued', %s, %s, %s, %s, %s, %s)
        ON CONFLICT (kind, cache_identity)
            WHERE state IN ('queued', 'running')
        DO NOTHING
        RETURNING id, recording_id, kind, cache_identity, state, queued_at,
                  started_at, finished_at, error_code, error_message,
                  work_units, estimate_key, estimated_total_ms,
                  estimate_method, estimate_sample_count, control_state,
                  execution_phase, control_revision, last_pause_requested_at,
                  last_pause_acknowledged_at, last_resumed_at,
                  accumulated_paused_ms, cancel_requested_at,
                  cancel_finished_at, queue_order
        """,
        (
            target.recording_id,
            target.kind,
            target.cache_identity,
            target.work_units,
            target.planner_identity,
            estimate_values["estimated_total_ms"],
            estimate_values["estimate_method"],
            estimate_values["estimate_sample_count"],
            _next_queue_order(connection),
        ),
    ).fetchone()
    if row is None:
        row = _select_active_job(
            connection,
            target.recording_id,
            target.kind,
            target.cache_identity,
        )
    if row is None:
        raise RuntimeError("The preparation request could not be serialized.")
    return _job_from_row(row)


def _freeze_estimate(
    connection: Any,
    estimate_key: str,
    work_units: int,
):
    rows = connection.execute(
        """
        SELECT job.work_units, job.started_at, job.finished_at,
               job.accumulated_paused_ms
        FROM jobs AS job
        JOIN artifacts AS artifact
          ON artifact.recording_id = job.recording_id
         AND artifact.kind = job.kind
         AND artifact.cache_identity = job.cache_identity
        WHERE job.state = 'succeeded'
          AND job.estimate_key = %s
          AND job.work_units > 0
          AND job.started_at IS NOT NULL
          AND job.finished_at > job.started_at
          AND artifact.manifest ->> 'cache_identity' = job.cache_identity
        ORDER BY job.finished_at DESC, job.id DESC
        LIMIT %s
        """,
        (estimate_key, MAX_ESTIMATE_SAMPLES),
    ).fetchall()
    samples: list[EstimateSample] = []
    for row in rows:
        started_at = row["started_at"]
        finished_at = row["finished_at"]
        if not isinstance(started_at, datetime) or not isinstance(finished_at, datetime):
            continue
        runtime_ms = max(
            1,
            int((finished_at - started_at).total_seconds() * 1_000)
            - (_optional_int(row.get("accumulated_paused_ms")) or 0),
        )
        samples.append(EstimateSample(runtime_ms, int(row["work_units"])))
    return estimate_total_ms(work_units, tuple(samples))


def _estimate_values_for_new_job(
    connection: Any,
    work_units: int | None,
    estimate_key: str | None,
) -> dict[str, object]:
    if work_units is None or estimate_key is None:
        return {
            "estimated_total_ms": None,
            "estimate_method": None,
            "estimate_sample_count": None,
        }
    frozen = _freeze_estimate(connection, estimate_key, work_units)
    return {
        "estimated_total_ms": frozen.estimated_total_ms,
        "estimate_method": frozen.method,
        "estimate_sample_count": frozen.sample_count,
    }


def _component_from_row(row: dict[str, object]) -> ProcessingComponent:
    return ProcessingComponent(
        relative_path=_optional_str(row["relative_path"]),
        size_bytes=_optional_int(row["size_bytes"]),
        mtime_ns=_optional_int(row["mtime_ns"]),
        condition=str(row["condition"]),
    )


def _artifact_from_row(row: dict[str, object]) -> ArtifactRecord:
    manifest = row["manifest"]
    if isinstance(manifest, str):
        manifest = json.loads(manifest)
    if not isinstance(manifest, dict):
        raise ValueError("Artifact manifest is not an object.")
    return ArtifactRecord(
        id=int(row["id"]),
        recording_id=int(row["recording_id"]),
        kind=str(row["kind"]),
        cache_identity=str(row["cache_identity"]),
        output_relative_path=str(row["output_relative_path"]),
        mime_type=str(row["mime_type"]),
        size_bytes=int(row["size_bytes"]),
        coverage_start_ns=int(row["coverage_start_ns"]),
        coverage_end_ns=int(row["coverage_end_ns"]),
        manifest=manifest,
        created_at=row["created_at"],  # type: ignore[arg-type]
    )


def _job_from_row(row: dict[str, object]) -> JobRecord:
    return JobRecord(
        id=int(row["id"]),
        recording_id=int(row["recording_id"]),
        kind=str(row["kind"]),
        cache_identity=str(row["cache_identity"]),
        state=str(row["state"]),
        queued_at=row["queued_at"],  # type: ignore[arg-type]
        started_at=row["started_at"],  # type: ignore[arg-type]
        finished_at=row["finished_at"],  # type: ignore[arg-type]
        error_code=_optional_str(row["error_code"]),
        error_message=_optional_str(row["error_message"]),
        work_units=_optional_int(row.get("work_units")),
        estimate_key=_optional_str(row.get("estimate_key")),
        estimated_total_ms=_optional_int(row.get("estimated_total_ms")),
        estimate_method=_optional_str(row.get("estimate_method")),
        estimate_sample_count=_optional_int(row.get("estimate_sample_count")),
        control_state=_optional_str(row.get("control_state")) or "none",
        execution_phase=_optional_str(row.get("execution_phase")),
        control_revision=_optional_int(row.get("control_revision")) or 0,
        last_pause_requested_at=row.get("last_pause_requested_at"),  # type: ignore[arg-type]
        last_pause_acknowledged_at=row.get("last_pause_acknowledged_at"),  # type: ignore[arg-type]
        last_resumed_at=row.get("last_resumed_at"),  # type: ignore[arg-type]
        accumulated_paused_ms=_optional_int(row.get("accumulated_paused_ms")) or 0,
        cancel_requested_at=row.get("cancel_requested_at"),  # type: ignore[arg-type]
        cancel_finished_at=row.get("cancel_finished_at"),  # type: ignore[arg-type]
        queue_order=_optional_int(row.get("queue_order")) or 0,
    )


def _target_from_row(row: dict[str, object]) -> PreparationTargetRecord:
    return PreparationTargetRecord(
        recording_id=int(row["recording_id"]),
        kind=str(row["kind"]),
        scan_generation=int(row["scan_generation"]),
        planner_identity=str(row["planner_identity"]),
        target_state=str(row["target_state"]),
        cache_identity=_optional_str(row["cache_identity"]),
        diagnostic_code=_optional_str(row["diagnostic_code"]),
        diagnostic_message=_optional_str(row["diagnostic_message"]),
        work_units=_optional_int(row["work_units"]),
    )


def _job_view_from_row(row: dict[str, object]) -> ProcessingJobViewRecord:
    return ProcessingJobViewRecord(
        job=_job_from_row(row),
        recording_name=str(row["display_name"]),
        output_size_bytes=_optional_int(row.get("output_size_bytes")),
        queue_position=_optional_int(row.get("queue_position")),
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
