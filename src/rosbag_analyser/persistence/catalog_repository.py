from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Protocol

from psycopg import IsolationLevel

from rosbag_analyser.catalog.types import (
    RecordingScanResult,
    SafeDiagnostic,
    ScanSnapshot,
    SourceComponentResult,
)
from rosbag_analyser.preparation_planner import (
    PREPARATION_KINDS,
    PreparationTargetPlan,
)

from .database import open_connection


@dataclass(frozen=True)
class ApplySummary:
    recording_count: int
    component_count: int
    generation: int


@dataclass(frozen=True)
class CatalogState:
    successful_generation: int
    successful_completed_at: datetime | None
    duration_ms: int
    recording_count: int
    readable_count: int
    damaged_count: int
    missing_count: int
    unsupported_count: int
    uninspectable_count: int


@dataclass(frozen=True)
class CatalogRecording:
    id: int
    archive_relative_path: str
    display_name: str
    start_time_ns: int | None
    duration_ns: int | None
    total_source_size_bytes: int | None
    storage_format: str | None
    metadata_version: int | None
    message_count: int | None
    topic_count: int | None
    ros_health: str
    diagnostic: SafeDiagnostic | None
    source_present: bool
    last_seen_generation: int


@dataclass(frozen=True)
class CatalogComponent:
    role: str
    condition: str
    display_name: str | None
    size_bytes: int | None
    mtime_ns: int | None
    diagnostic: SafeDiagnostic | None


@dataclass(frozen=True)
class CatalogRecordingDetail:
    recording: CatalogRecording
    components: tuple[CatalogComponent, ...]


@dataclass(frozen=True)
class _PersistedRecordingIdentity:
    id: int
    cache_identity_recording_id: int
    cache_identity_relative_path: str


@dataclass(frozen=True)
class _StoredMoveCandidate:
    id: int
    archive_relative_path: str
    cache_identity_recording_id: int
    cache_identity_relative_path: str
    source_present: bool
    has_history: bool
    move_fingerprint: str | None


class TargetPlanner(Protocol):
    def plan_recording(
        self,
        recording_id: int,
        recording: RecordingScanResult,
        cache_identity_recording_id: int | None = None,
        cache_identity_relative_path: str | None = None,
    ) -> tuple[PreparationTargetPlan, ...]: ...

    def unavailable_targets(
        self,
        code: str,
        message: str,
    ) -> tuple[PreparationTargetPlan, ...]: ...


class CatalogRepository:
    def __init__(
        self,
        database_url: str,
        target_planner: TargetPlanner | None = None,
    ) -> None:
        self.database_url = database_url
        self.target_planner = target_planner

    def apply_snapshot(self, snapshot: ScanSnapshot) -> ApplySummary:
        recording_paths = [item.archive_relative_path for item in snapshot.recordings]
        if len(recording_paths) != len(set(recording_paths)):
            raise ValueError("A scan snapshot contains duplicate recording identities.")

        component_count = 0
        with open_connection(self.database_url) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                ("rosbag_analyser_catalog_apply",),
            )
            state = connection.execute(
                """
                SELECT successful_generation
                FROM catalog_state
                WHERE singleton = TRUE
                FOR UPDATE
                """
            ).fetchone()
            if state is None:
                raise RuntimeError("The catalog state row is unavailable.")
            generation = int(state["successful_generation"]) + 1
            move_fingerprints = {
                recording.archive_relative_path: _scan_move_fingerprint(recording)
                for recording in snapshot.recordings
            }
            self._reconcile_recording_moves(
                connection,
                snapshot,
                move_fingerprints,
            )
            for recording in snapshot.recordings:
                roles = [component.role.value for component in recording.components]
                if len(roles) != len(set(roles)):
                    raise ValueError("A recording contains duplicate component roles.")
                persisted_identity = self._upsert_recording(
                    connection,
                    recording,
                    generation,
                    move_fingerprints[recording.archive_relative_path],
                )
                for component in recording.components:
                    self._upsert_component(
                        connection, persisted_identity.id, component
                    )
                    component_count += 1
                targets = self._plan_recording(
                    persisted_identity.id,
                    recording,
                    persisted_identity.cache_identity_recording_id,
                    persisted_identity.cache_identity_relative_path,
                )
                if tuple(target.kind for target in targets) != PREPARATION_KINDS:
                    raise ValueError(
                        "Preparation planning did not return the three fixed targets."
                    )
                for target in targets:
                    self._upsert_target(
                        connection, persisted_identity.id, generation, target
                    )

            connection.execute(
                """
                UPDATE recordings
                SET source_present = FALSE,
                    ros_health = 'missing',
                    diagnostic_code = 'recording_missing',
                    diagnostic_message =
                        'The recording was absent from the latest complete scan.',
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_present = TRUE
                  AND last_seen_generation < %s
                """,
                (generation,),
            )
            missing_targets = self._unavailable_targets(
                "recording_missing",
                "The recording was absent from the latest complete scan.",
            )
            for target in missing_targets:
                connection.execute(
                    """
                    UPDATE preparation_targets AS target
                    SET scan_generation = %(generation)s,
                        planner_identity = %(planner_identity)s,
                        target_state = 'unavailable',
                        cache_identity = NULL,
                        diagnostic_code = %(diagnostic_code)s,
                        diagnostic_message = %(diagnostic_message)s,
                        work_units = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    FROM recordings AS recording
                    WHERE target.recording_id = recording.id
                      AND target.kind = %(kind)s
                      AND recording.source_present = FALSE
                    """,
                    {
                        "generation": generation,
                        "planner_identity": target.planner_identity,
                        "diagnostic_code": target.diagnostic.code,
                        "diagnostic_message": target.diagnostic.message,
                        "kind": target.kind,
                    },
                )

            counts = connection.execute(
                """
                SELECT count(*) FILTER (
                           WHERE source_present = TRUE
                       ) AS recording_count,
                       count(*) FILTER (
                           WHERE source_present = TRUE
                             AND ros_health = 'readable'
                       ) AS readable_count,
                       count(*) FILTER (
                           WHERE source_present = TRUE
                             AND ros_health = 'damaged'
                       ) AS damaged_count,
                       count(*) FILTER (
                           WHERE source_present = TRUE
                             AND ros_health = 'missing'
                       ) AS missing_count,
                       count(*) FILTER (
                           WHERE source_present = TRUE
                             AND ros_health = 'unsupported'
                       ) AS unsupported_count,
                       count(*) FILTER (
                           WHERE source_present = TRUE
                             AND ros_health = 'uninspectable'
                       ) AS uninspectable_count
                FROM recordings
                """
            ).fetchone()
            assert counts is not None
            connection.execute(
                """
                UPDATE catalog_state
                SET successful_generation = %(generation)s,
                    successful_completed_at = CURRENT_TIMESTAMP,
                    duration_ms = %(duration_ms)s,
                    recording_count = %(recording_count)s,
                    readable_count = %(readable_count)s,
                    damaged_count = %(damaged_count)s,
                    missing_count = %(missing_count)s,
                    unsupported_count = %(unsupported_count)s,
                    uninspectable_count = %(uninspectable_count)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE singleton = TRUE
                """,
                {
                    "generation": generation,
                    "duration_ms": snapshot.duration_ms,
                    **counts,
                },
            )
        return ApplySummary(
            recording_count=len(snapshot.recordings),
            component_count=component_count,
            generation=generation,
        )

    def get_catalog_state(self) -> CatalogState:
        with open_connection(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT successful_generation, successful_completed_at,
                       duration_ms, recording_count, readable_count,
                       damaged_count, missing_count, unsupported_count,
                       uninspectable_count
                FROM catalog_state
                WHERE singleton = TRUE
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("The catalog state row is unavailable.")
        return _catalog_state_from_row(row)

    def list_recordings(
        self,
        limit: int | None = None,
        *,
        include_missing: bool = False,
    ) -> tuple[CatalogRecording, ...]:
        if limit is not None and limit <= 0:
            raise ValueError("The catalog limit must be positive.")
        with open_connection(self.database_url) as connection:
            rows = connection.execute(
                """
                SELECT id, archive_relative_path, display_name,
                       start_time_ns, duration_ns,
                       total_source_size_bytes, storage_format, metadata_version,
                       message_count, topic_count, ros_health,
                       diagnostic_code, diagnostic_message,
                       source_present, last_seen_generation
                FROM recordings
                WHERE source_present = TRUE OR %s
                ORDER BY start_time_ns DESC NULLS LAST, display_name, id
                LIMIT %s
                """,
                (include_missing, limit),
            ).fetchall()
        return tuple(_recording_from_row(row) for row in rows)

    def get_recording(self, recording_id: int) -> CatalogRecordingDetail | None:
        with open_connection(self.database_url) as connection:
            connection.isolation_level = IsolationLevel.REPEATABLE_READ
            row = connection.execute(
                """
                SELECT id, archive_relative_path, display_name,
                       start_time_ns, duration_ns,
                       total_source_size_bytes, storage_format, metadata_version,
                       message_count, topic_count, ros_health,
                       diagnostic_code, diagnostic_message,
                       source_present, last_seen_generation
                FROM recordings
                WHERE id = %s
                """,
                (recording_id,),
            ).fetchone()
            if row is None:
                return None
            component_rows = connection.execute(
                """
                SELECT role, relative_path, size_bytes, mtime_ns, condition,
                       diagnostic_code, diagnostic_message
                FROM source_components
                WHERE recording_id = %s
                ORDER BY CASE role
                    WHEN 'metadata' THEN 1
                    WHEN 'ros_database' THEN 2
                    WHEN 'topdown_video' THEN 3
                    WHEN 'topdown_timestamps' THEN 4
                    ELSE 5
                END
                """,
                (recording_id,),
            ).fetchall()
        return CatalogRecordingDetail(
            recording=_recording_from_row(row),
            components=tuple(_component_from_row(item) for item in component_rows),
        )

    @staticmethod
    def _upsert_recording(
        connection: Any,
        recording: RecordingScanResult,
        generation: int,
        move_fingerprint: str | None,
    ) -> _PersistedRecordingIdentity:
        existing = connection.execute(
            """
            SELECT id, display_name, start_time_ns, duration_ns,
                   total_source_size_bytes, storage_format, metadata_version,
                   message_count, topic_count, ros_health,
                   diagnostic_code, diagnostic_message, source_revision,
                   source_present, last_seen_generation,
                   cache_identity_recording_id,
                   cache_identity_relative_path, move_fingerprint
            FROM recordings
            WHERE archive_relative_path = %s
            FOR UPDATE
            """,
            (recording.archive_relative_path,),
        ).fetchone()
        values = _recording_values(recording, generation, move_fingerprint)
        if existing is None:
            row = connection.execute(
                """
                WITH allocated AS (
                    SELECT nextval(
                        pg_get_serial_sequence('recordings', 'id')
                    )::bigint AS id
                )
                INSERT INTO recordings (
                    id, archive_relative_path, display_name, start_time_ns,
                    duration_ns, total_source_size_bytes, storage_format,
                    metadata_version, message_count, topic_count, ros_health,
                    diagnostic_code, diagnostic_message, source_revision,
                    source_present, last_seen_generation,
                    cache_identity_recording_id,
                    cache_identity_relative_path, move_fingerprint
                )
                SELECT allocated.id,
                    %(archive_relative_path)s, %(display_name)s, %(start_time_ns)s,
                    %(duration_ns)s, %(total_source_size_bytes)s,
                    %(storage_format)s, %(metadata_version)s, %(message_count)s,
                    %(topic_count)s, %(ros_health)s, %(diagnostic_code)s,
                    %(diagnostic_message)s, %(source_revision)s,
                    %(source_present)s, %(last_seen_generation)s,
                    allocated.id, %(archive_relative_path)s, %(move_fingerprint)s
                FROM allocated
                RETURNING id, cache_identity_recording_id,
                          cache_identity_relative_path
                """,
                values,
            ).fetchone()
            assert row is not None
            return _persisted_identity_from_row(row)

        if any(
            existing[key] != value
            for key, value in values.items()
            if key != "archive_relative_path"
        ):
            connection.execute(
                """
                UPDATE recordings
                SET display_name = %(display_name)s,
                    start_time_ns = %(start_time_ns)s,
                    duration_ns = %(duration_ns)s,
                    total_source_size_bytes = %(total_source_size_bytes)s,
                    storage_format = %(storage_format)s,
                    metadata_version = %(metadata_version)s,
                    message_count = %(message_count)s,
                    topic_count = %(topic_count)s,
                    ros_health = %(ros_health)s,
                    diagnostic_code = %(diagnostic_code)s,
                    diagnostic_message = %(diagnostic_message)s,
                    source_revision = %(source_revision)s,
                    source_present = %(source_present)s,
                    last_seen_generation = %(last_seen_generation)s,
                    move_fingerprint = %(move_fingerprint)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s
                """,
                {**values, "id": existing["id"]},
            )
        return _persisted_identity_from_row(existing)

    @staticmethod
    def _reconcile_recording_moves(
        connection: Any,
        snapshot: ScanSnapshot,
        move_fingerprints: dict[str, str | None],
    ) -> None:
        candidates = _load_move_candidates(
            connection,
            tuple(move_fingerprints.values()),
            tuple(move_fingerprints),
        )
        if not candidates:
            return

        incoming_by_fingerprint: dict[str, list[str]] = {}
        for path, fingerprint in move_fingerprints.items():
            if fingerprint is not None:
                incoming_by_fingerprint.setdefault(fingerprint, []).append(path)
        candidates_by_fingerprint: dict[str, list[_StoredMoveCandidate]] = {}
        candidates_by_path = {
            candidate.archive_relative_path: candidate for candidate in candidates
        }
        for candidate in candidates:
            if candidate.move_fingerprint is not None:
                candidates_by_fingerprint.setdefault(
                    candidate.move_fingerprint, []
                ).append(candidate)

        incoming_paths = {item.archive_relative_path for item in snapshot.recordings}
        claimed_candidates: set[int] = set()
        for path in sorted(incoming_paths):
            fingerprint = move_fingerprints[path]
            if (
                fingerprint is None
                or len(incoming_by_fingerprint.get(fingerprint, ())) != 1
            ):
                continue
            exact = candidates_by_path.get(path)
            matching = candidates_by_fingerprint.get(fingerprint, [])
            if exact is None:
                prior_current = [
                    candidate
                    for candidate in matching
                    if candidate.source_present
                    and candidate.archive_relative_path not in incoming_paths
                    and candidate.id not in claimed_candidates
                ]
                if len(prior_current) != 1:
                    continue
                moved = prior_current[0]
                connection.execute(
                    """
                    UPDATE recordings
                    SET archive_relative_path = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (path, moved.id),
                )
                claimed_candidates.add(moved.id)
                continue

            if exact.has_history:
                continue
            historical = [
                candidate
                for candidate in matching
                if candidate.id != exact.id
                and not candidate.source_present
                and candidate.has_history
                and candidate.archive_relative_path not in incoming_paths
                and candidate.id not in claimed_candidates
            ]
            if len(historical) != 1:
                continue
            owner = historical[0]
            connection.execute(
                """
                UPDATE recordings
                SET cache_identity_recording_id = %s,
                    cache_identity_relative_path = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    owner.cache_identity_recording_id,
                    owner.cache_identity_relative_path,
                    exact.id,
                ),
            )
            connection.execute(
                "UPDATE artifacts SET recording_id = %s WHERE recording_id = %s",
                (exact.id, owner.id),
            )
            connection.execute(
                "UPDATE jobs SET recording_id = %s WHERE recording_id = %s",
                (exact.id, owner.id),
            )
            claimed_candidates.add(owner.id)

    @staticmethod
    def _upsert_target(
        connection: Any,
        recording_id: int,
        generation: int,
        target: PreparationTargetPlan,
    ) -> None:
        connection.execute(
            """
            INSERT INTO preparation_targets (
                recording_id, kind, scan_generation, planner_identity,
                target_state, cache_identity, diagnostic_code,
                diagnostic_message, work_units
            ) VALUES (
                %(recording_id)s, %(kind)s, %(scan_generation)s,
                %(planner_identity)s, %(target_state)s, %(cache_identity)s,
                %(diagnostic_code)s, %(diagnostic_message)s, %(work_units)s
            )
            ON CONFLICT (recording_id, kind) DO UPDATE
            SET scan_generation = EXCLUDED.scan_generation,
                planner_identity = EXCLUDED.planner_identity,
                target_state = EXCLUDED.target_state,
                cache_identity = EXCLUDED.cache_identity,
                diagnostic_code = EXCLUDED.diagnostic_code,
                diagnostic_message = EXCLUDED.diagnostic_message,
                work_units = EXCLUDED.work_units,
                updated_at = CURRENT_TIMESTAMP
            """,
            {
                "recording_id": recording_id,
                "kind": target.kind,
                "scan_generation": generation,
                "planner_identity": target.planner_identity,
                "target_state": target.target_state,
                "cache_identity": target.cache_identity,
                "diagnostic_code": _diagnostic_code(target.diagnostic),
                "diagnostic_message": _diagnostic_message(target.diagnostic),
                "work_units": target.work_units,
            },
        )

    def _plan_recording(
        self,
        recording_id: int,
        recording: RecordingScanResult,
        cache_identity_recording_id: int,
        cache_identity_relative_path: str,
    ) -> tuple[PreparationTargetPlan, ...]:
        if self.target_planner is not None:
            return self.target_planner.plan_recording(
                recording_id,
                recording,
                cache_identity_recording_id,
                cache_identity_relative_path,
            )
        return _unconfigured_targets()

    def _unavailable_targets(
        self,
        code: str,
        message: str,
    ) -> tuple[PreparationTargetPlan, ...]:
        if self.target_planner is not None:
            return self.target_planner.unavailable_targets(code, message)
        return tuple(
            PreparationTargetPlan(
                kind=kind,
                planner_identity=_unconfigured_planner_identity(kind),
                target_state="unavailable",
                cache_identity=None,
                diagnostic=SafeDiagnostic(code, message),
                work_units=None,
            )
            for kind in PREPARATION_KINDS
        )

    @staticmethod
    def _upsert_component(
        connection: Any, recording_id: int, component: SourceComponentResult
    ) -> int:
        existing = connection.execute(
            """
            SELECT id, relative_path, size_bytes, mtime_ns, condition,
                   diagnostic_code, diagnostic_message
            FROM source_components
            WHERE recording_id = %s AND role = %s
            FOR UPDATE
            """,
            (recording_id, component.role.value),
        ).fetchone()
        values = _component_values(recording_id, component)
        if existing is None:
            row = connection.execute(
                """
                INSERT INTO source_components (
                    recording_id, role, relative_path, size_bytes, mtime_ns,
                    condition, diagnostic_code, diagnostic_message
                ) VALUES (
                    %(recording_id)s, %(role)s, %(relative_path)s,
                    %(size_bytes)s, %(mtime_ns)s, %(condition)s,
                    %(diagnostic_code)s, %(diagnostic_message)s
                )
                RETURNING id
                """,
                values,
            ).fetchone()
            return int(row["id"])

        compared = {
            key: value
            for key, value in values.items()
            if key not in {"recording_id", "role"}
        }
        if any(existing[key] != value for key, value in compared.items()):
            connection.execute(
                """
                UPDATE source_components
                SET relative_path = %(relative_path)s,
                    size_bytes = %(size_bytes)s,
                    mtime_ns = %(mtime_ns)s,
                    condition = %(condition)s,
                    diagnostic_code = %(diagnostic_code)s,
                    diagnostic_message = %(diagnostic_message)s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s
                """,
                {**values, "id": existing["id"]},
            )
        return int(existing["id"])


def _load_move_candidates(
    connection: Any,
    fingerprints: tuple[str | None, ...],
    incoming_paths: tuple[str, ...],
) -> tuple[_StoredMoveCandidate, ...]:
    usable_fingerprints = tuple(
        fingerprint for fingerprint in fingerprints if fingerprint is not None
    )
    ordinary_limit = max(100, len(incoming_paths) * 4)
    ordinary_rows = connection.execute(
        """
        SELECT recording.id, recording.archive_relative_path,
               recording.cache_identity_recording_id,
               recording.cache_identity_relative_path,
               recording.source_present, recording.last_seen_generation,
               recording.start_time_ns, recording.duration_ns,
               recording.total_source_size_bytes, recording.storage_format,
               recording.metadata_version, recording.message_count,
               recording.topic_count, recording.move_fingerprint,
               EXISTS (
                   SELECT 1 FROM artifacts
                   WHERE artifacts.recording_id = recording.id
               ) AS has_artifacts,
               EXISTS (
                   SELECT 1 FROM jobs
                   WHERE jobs.recording_id = recording.id
               ) AS has_jobs
        FROM recordings AS recording
        WHERE recording.source_present = TRUE
           OR recording.archive_relative_path = ANY (%s)
           OR recording.move_fingerprint = ANY (%s)
        ORDER BY recording.source_present DESC,
                 recording.last_seen_generation DESC, recording.id
        LIMIT %s
        """,
        (list(incoming_paths), list(usable_fingerprints), ordinary_limit + 1),
    ).fetchall()
    if len(ordinary_rows) > ordinary_limit:
        raise RuntimeError(
            "Catalog move reconciliation exceeded its bounded candidate set."
        )

    legacy_limit = max(100, len(incoming_paths) * 2)
    legacy_rows = connection.execute(
        """
        SELECT recording.id, recording.archive_relative_path,
               recording.cache_identity_recording_id,
               recording.cache_identity_relative_path,
               recording.source_present, recording.last_seen_generation,
               recording.start_time_ns, recording.duration_ns,
               recording.total_source_size_bytes, recording.storage_format,
               recording.metadata_version, recording.message_count,
               recording.topic_count, recording.move_fingerprint,
               EXISTS (
                   SELECT 1 FROM artifacts
                   WHERE artifacts.recording_id = recording.id
               ) AS has_artifacts,
               EXISTS (
                   SELECT 1 FROM jobs
                   WHERE jobs.recording_id = recording.id
               ) AS has_jobs
        FROM recordings AS recording
        WHERE recording.source_present = FALSE
          AND recording.move_fingerprint IS NULL
          AND (
              EXISTS (
                  SELECT 1 FROM artifacts
                  WHERE artifacts.recording_id = recording.id
              )
              OR EXISTS (
                  SELECT 1 FROM jobs
                  WHERE jobs.recording_id = recording.id
              )
          )
        ORDER BY recording.last_seen_generation DESC, recording.id
        LIMIT %s
        """,
        (legacy_limit + 1,),
    ).fetchall()
    if len(legacy_rows) > legacy_limit:
        legacy_rows = []

    rows_by_id = {
        int(row["id"]): row for row in (*ordinary_rows, *legacy_rows)
    }
    if not rows_by_id:
        return ()
    component_rows = connection.execute(
        """
        SELECT recording_id, role, relative_path, size_bytes, mtime_ns,
               condition, diagnostic_code, diagnostic_message
        FROM source_components
        WHERE recording_id = ANY (%s)
        ORDER BY recording_id, role
        """,
        (list(rows_by_id),),
    ).fetchall()
    components_by_recording: dict[int, list[dict[str, object]]] = {}
    for component in component_rows:
        components_by_recording.setdefault(
            int(component["recording_id"]), []
        ).append(component)

    fingerprint_updates: list[tuple[str, int]] = []
    candidates: list[_StoredMoveCandidate] = []
    for recording_id, row in rows_by_id.items():
        fingerprint = _optional_str(row["move_fingerprint"])
        if fingerprint is None:
            fingerprint = _stored_move_fingerprint(
                row,
                components_by_recording.get(recording_id, []),
            )
            if fingerprint is not None:
                fingerprint_updates.append((fingerprint, recording_id))
        candidates.append(
            _StoredMoveCandidate(
                id=recording_id,
                archive_relative_path=str(row["archive_relative_path"]),
                cache_identity_recording_id=int(
                    row["cache_identity_recording_id"]
                ),
                cache_identity_relative_path=str(
                    row["cache_identity_relative_path"]
                ),
                source_present=bool(row["source_present"]),
                has_history=bool(row["has_artifacts"] or row["has_jobs"]),
                move_fingerprint=fingerprint,
            )
        )
    if fingerprint_updates:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE recordings
                SET move_fingerprint = %s
                WHERE id = %s AND move_fingerprint IS NULL
                """,
                fingerprint_updates,
            )
    return tuple(candidates)


def _scan_move_fingerprint(recording: RecordingScanResult) -> str | None:
    components = [
        {
            "role": component.role.value,
            "relative_path": component.relative_path,
            "size_bytes": component.size_bytes,
            "mtime_ns": component.mtime_ns,
            "condition": component.condition.value,
            "diagnostic_code": _diagnostic_code(component.diagnostic),
            "diagnostic_message": _diagnostic_message(component.diagnostic),
        }
        for component in recording.components
    ]
    return _move_fingerprint(
        recording.archive_relative_path,
        recording.start_time_ns,
        recording.duration_ns,
        recording.total_source_size_bytes,
        recording.storage_format,
        recording.metadata_version,
        recording.message_count,
        recording.topic_count,
        components,
    )


def _stored_move_fingerprint(
    recording: dict[str, object],
    components: list[dict[str, object]],
) -> str | None:
    return _move_fingerprint(
        str(recording["archive_relative_path"]),
        _optional_int(recording["start_time_ns"]),
        _optional_int(recording["duration_ns"]),
        _optional_int(recording["total_source_size_bytes"]),
        _optional_str(recording["storage_format"]),
        _optional_int(recording["metadata_version"]),
        _optional_int(recording["message_count"]),
        _optional_int(recording["topic_count"]),
        components,
    )


def _move_fingerprint(
    recording_path: str,
    start_time_ns: int | None,
    duration_ns: int | None,
    total_source_size_bytes: int | None,
    storage_format: str | None,
    metadata_version: int | None,
    message_count: int | None,
    topic_count: int | None,
    components: list[dict[str, object]],
) -> str | None:
    required_recording_facts = (
        start_time_ns,
        duration_ns,
        total_source_size_bytes,
        storage_format,
        metadata_version,
        message_count,
        topic_count,
    )
    if any(value is None for value in required_recording_facts):
        return None

    normalized_components: list[dict[str, object]] = []
    required_roles: dict[str, dict[str, object]] = {}
    for component in components:
        role = str(component["role"])
        relative_path = _optional_str(component.get("relative_path"))
        local_path = _component_local_path(recording_path, relative_path)
        normalized = {
            "role": role,
            "local_path": local_path,
            "size_bytes": _optional_int(component.get("size_bytes")),
            "mtime_ns": _optional_int(component.get("mtime_ns")),
            "condition": str(component["condition"]),
            "diagnostic_code": _optional_str(component.get("diagnostic_code")),
            "diagnostic_message": _optional_str(
                component.get("diagnostic_message")
            ),
        }
        normalized_components.append(normalized)
        required_roles[role] = normalized
    for role in ("metadata", "ros_database"):
        component = required_roles.get(role)
        if (
            component is None
            or component["local_path"] is None
            or component["size_bytes"] is None
            or component["mtime_ns"] is None
        ):
            return None

    document = {
        "version": 1,
        "recording": {
            "start_time_ns": start_time_ns,
            "duration_ns": duration_ns,
            "total_source_size_bytes": total_source_size_bytes,
            "storage_format": storage_format,
            "metadata_version": metadata_version,
            "message_count": message_count,
            "topic_count": topic_count,
        },
        "components": sorted(
            normalized_components,
            key=lambda item: str(item["role"]),
        ),
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _component_local_path(
    recording_path: str,
    component_path: str | None,
) -> str | None:
    if component_path is None:
        return None
    try:
        local = PurePosixPath(component_path).relative_to(
            PurePosixPath(recording_path)
        )
    except ValueError:
        return None
    if not local.parts:
        return None
    return local.as_posix()


def _persisted_identity_from_row(row: dict[str, object]) -> _PersistedRecordingIdentity:
    return _PersistedRecordingIdentity(
        id=int(row["id"]),
        cache_identity_recording_id=int(row["cache_identity_recording_id"]),
        cache_identity_relative_path=str(row["cache_identity_relative_path"]),
    )


def _recording_values(
    recording: RecordingScanResult,
    generation: int,
    move_fingerprint: str | None,
) -> dict[str, object]:
    return {
        "archive_relative_path": recording.archive_relative_path,
        "display_name": recording.display_name,
        "start_time_ns": recording.start_time_ns,
        "duration_ns": recording.duration_ns,
        "total_source_size_bytes": recording.total_source_size_bytes,
        "storage_format": recording.storage_format,
        "metadata_version": recording.metadata_version,
        "message_count": recording.message_count,
        "topic_count": recording.topic_count,
        "ros_health": recording.ros_health.value,
        "diagnostic_code": _diagnostic_code(recording.diagnostic),
        "diagnostic_message": _diagnostic_message(recording.diagnostic),
        "source_revision": recording.source_revision,
        "source_present": True,
        "last_seen_generation": generation,
        "move_fingerprint": move_fingerprint,
    }


def _component_values(
    recording_id: int, component: SourceComponentResult
) -> dict[str, object]:
    return {
        "recording_id": recording_id,
        "role": component.role.value,
        "relative_path": component.relative_path,
        "size_bytes": component.size_bytes,
        "mtime_ns": component.mtime_ns,
        "condition": component.condition.value,
        "diagnostic_code": _diagnostic_code(component.diagnostic),
        "diagnostic_message": _diagnostic_message(component.diagnostic),
    }


def _recording_from_row(row: dict[str, object]) -> CatalogRecording:
    return CatalogRecording(
        id=int(row["id"]),
        archive_relative_path=str(row["archive_relative_path"]),
        display_name=str(row["display_name"]),
        start_time_ns=_optional_int(row["start_time_ns"]),
        duration_ns=_optional_int(row["duration_ns"]),
        total_source_size_bytes=_optional_int(row["total_source_size_bytes"]),
        storage_format=_optional_str(row["storage_format"]),
        metadata_version=_optional_int(row["metadata_version"]),
        message_count=_optional_int(row["message_count"]),
        topic_count=_optional_int(row["topic_count"]),
        ros_health=str(row["ros_health"]),
        diagnostic=_diagnostic_from_row(row),
        source_present=bool(row["source_present"]),
        last_seen_generation=int(row["last_seen_generation"]),
    )


def _component_from_row(row: dict[str, object]) -> CatalogComponent:
    relative_path = _optional_str(row["relative_path"])
    return CatalogComponent(
        role=str(row["role"]),
        condition=str(row["condition"]),
        display_name=(
            None if relative_path is None else PurePosixPath(relative_path).name
        ),
        size_bytes=_optional_int(row["size_bytes"]),
        mtime_ns=_optional_int(row["mtime_ns"]),
        diagnostic=_diagnostic_from_row(row),
    )


def _diagnostic_from_row(row: dict[str, object]) -> SafeDiagnostic | None:
    code = _optional_str(row["diagnostic_code"])
    message = _optional_str(row["diagnostic_message"])
    if code is None or message is None:
        return None
    return SafeDiagnostic(code=code, message=message)


def _diagnostic_code(diagnostic: SafeDiagnostic | None) -> str | None:
    return None if diagnostic is None else diagnostic.code


def _diagnostic_message(diagnostic: SafeDiagnostic | None) -> str | None:
    return None if diagnostic is None else diagnostic.message[:500]


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _catalog_state_from_row(row: dict[str, object]) -> CatalogState:
    return CatalogState(
        successful_generation=int(row["successful_generation"]),
        successful_completed_at=row["successful_completed_at"],  # type: ignore[arg-type]
        duration_ms=int(row["duration_ms"]),
        recording_count=int(row["recording_count"]),
        readable_count=int(row["readable_count"]),
        damaged_count=int(row["damaged_count"]),
        missing_count=int(row["missing_count"]),
        unsupported_count=int(row["unsupported_count"]),
        uninspectable_count=int(row["uninspectable_count"]),
    )


def _unconfigured_planner_identity(kind: str) -> str:
    return hashlib.sha256(f"unconfigured:{kind}".encode("ascii")).hexdigest()


def _unconfigured_targets() -> tuple[PreparationTargetPlan, ...]:
    return tuple(
        PreparationTargetPlan(
            kind=kind,
            planner_identity=_unconfigured_planner_identity(kind),
            target_state="unavailable",
            cache_identity=None,
            diagnostic=SafeDiagnostic(
                "preparation_planner_unconfigured",
                "Preparation targets require another explicit catalog rescan.",
            ),
            work_units=None,
        )
        for kind in PREPARATION_KINDS
    )
