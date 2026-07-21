from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from psycopg import IsolationLevel

from rosbag_analyser.catalog.types import (
    RecordingScanResult,
    SafeDiagnostic,
    ScanSnapshot,
    SourceComponentResult,
)

from .database import open_connection


@dataclass(frozen=True)
class ApplySummary:
    recording_count: int
    component_count: int


@dataclass(frozen=True)
class CatalogRecording:
    id: int
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


class CatalogRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

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
            for recording in snapshot.recordings:
                roles = [component.role.value for component in recording.components]
                if len(roles) != len(set(roles)):
                    raise ValueError("A recording contains duplicate component roles.")
                recording_id = self._upsert_recording(connection, recording)
                for component in recording.components:
                    self._upsert_component(connection, recording_id, component)
                    component_count += 1
        return ApplySummary(
            recording_count=len(snapshot.recordings),
            component_count=component_count,
        )

    def list_recordings(self) -> tuple[CatalogRecording, ...]:
        with open_connection(self.database_url) as connection:
            rows = connection.execute(
                """
                SELECT id, display_name, start_time_ns, duration_ns,
                       total_source_size_bytes, storage_format, metadata_version,
                       message_count, topic_count, ros_health,
                       diagnostic_code, diagnostic_message
                FROM recordings
                ORDER BY start_time_ns DESC NULLS LAST, display_name, id
                """
            ).fetchall()
        return tuple(_recording_from_row(row) for row in rows)

    def get_recording(self, recording_id: int) -> CatalogRecordingDetail | None:
        with open_connection(self.database_url) as connection:
            connection.isolation_level = IsolationLevel.REPEATABLE_READ
            row = connection.execute(
                """
                SELECT id, display_name, start_time_ns, duration_ns,
                       total_source_size_bytes, storage_format, metadata_version,
                       message_count, topic_count, ros_health,
                       diagnostic_code, diagnostic_message
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
        connection: Any, recording: RecordingScanResult
    ) -> int:
        existing = connection.execute(
            """
            SELECT id, display_name, start_time_ns, duration_ns,
                   total_source_size_bytes, storage_format, metadata_version,
                   message_count, topic_count, ros_health,
                   diagnostic_code, diagnostic_message, source_revision
            FROM recordings
            WHERE archive_relative_path = %s
            FOR UPDATE
            """,
            (recording.archive_relative_path,),
        ).fetchone()
        values = _recording_values(recording)
        if existing is None:
            row = connection.execute(
                """
                INSERT INTO recordings (
                    archive_relative_path, display_name, start_time_ns,
                    duration_ns, total_source_size_bytes, storage_format,
                    metadata_version, message_count, topic_count, ros_health,
                    diagnostic_code, diagnostic_message, source_revision
                ) VALUES (
                    %(archive_relative_path)s, %(display_name)s, %(start_time_ns)s,
                    %(duration_ns)s, %(total_source_size_bytes)s,
                    %(storage_format)s, %(metadata_version)s, %(message_count)s,
                    %(topic_count)s, %(ros_health)s, %(diagnostic_code)s,
                    %(diagnostic_message)s, %(source_revision)s
                )
                RETURNING id
                """,
                values,
            ).fetchone()
            return int(row["id"])

        if any(existing[key] != value for key, value in values.items() if key != "archive_relative_path"):
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
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %(id)s
                """,
                {**values, "id": existing["id"]},
            )
        return int(existing["id"])

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


def _recording_values(recording: RecordingScanResult) -> dict[str, object]:
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
