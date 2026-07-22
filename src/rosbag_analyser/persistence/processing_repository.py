from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from .database import open_connection


FRONT_PREVIEW_KIND = "front_preview"
TOPDOWN_PREVIEW_KIND = "topdown_preview"
IMU_SERIES_KIND = "imu_series"


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


class ProcessingRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def get_source(self, recording_id: int) -> ProcessingSourceRecord | None:
        with open_connection(self.database_url) as connection:
            recording = connection.execute(
                """
                SELECT id, archive_relative_path, start_time_ns, duration_ns,
                       ros_health
                FROM recordings
                WHERE id = %s
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
    ) -> RequestOutcome:
        with open_connection(self.database_url) as connection:
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

            inserted = connection.execute(
                """
                INSERT INTO jobs (recording_id, kind, cache_identity, state)
                VALUES (%s, %s, %s, 'queued')
                ON CONFLICT (kind, cache_identity)
                    WHERE state IN ('queued', 'running')
                DO NOTHING
                RETURNING id, recording_id, kind, cache_identity, state,
                          queued_at, started_at, finished_at,
                          error_code, error_message
                """,
                (recording_id, kind, cache_identity),
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
            row = connection.execute(
                """
                WITH next_job AS (
                    SELECT id
                    FROM jobs
                    WHERE state = 'queued'
                    ORDER BY queued_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE jobs
                SET state = 'running', started_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM next_job)
                RETURNING id, recording_id, kind, cache_identity, state,
                          queued_at, started_at, finished_at,
                          error_code, error_message
                """
            ).fetchone()
        return None if row is None else _job_from_row(row)

    def complete_job(self, job_id: int, artifact: ArtifactWrite) -> ArtifactRecord:
        with open_connection(self.database_url) as connection:
            _lock_cache_identity(connection, artifact.kind, artifact.cache_identity)
            job = connection.execute(
                """
                SELECT id, recording_id, kind, cache_identity, state
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
                SET state = 'succeeded', finished_at = CURRENT_TIMESTAMP
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
                    error_code = %s, error_message = %s
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
                    END
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
               started_at, finished_at, error_code, error_message
        FROM jobs
        WHERE recording_id = %s AND kind = %s AND cache_identity = %s
          AND state IN ('queued', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        (recording_id, kind, cache_identity),
    ).fetchone()


def _select_latest_failed_job(
    connection: Any, recording_id: int, kind: str, cache_identity: str
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT id, recording_id, kind, cache_identity, state, queued_at,
               started_at, finished_at, error_code, error_message
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
    )


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
