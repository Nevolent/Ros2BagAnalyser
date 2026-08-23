from __future__ import annotations

from typing import Any

from psycopg import IsolationLevel
import pytest

from rosbag_analyser.persistence import catalog_repository


class _QueryResult:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.row = row
        self.rows = [] if rows is None else rows

    def fetchone(self) -> dict[str, object] | None:
        return self.row

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class _DetailConnection:
    def __init__(self) -> None:
        self.isolation_level: IsolationLevel | None = None

    def __enter__(self) -> "_DetailConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> _QueryResult:
        assert self.isolation_level is IsolationLevel.REPEATABLE_READ
        if "FROM recordings" in statement:
            return _QueryResult(
                row={
                    "id": 1,
                    "archive_relative_path": "folder/recording",
                    "display_name": "recording",
                    "start_time_ns": 100,
                    "duration_ns": 200,
                    "total_source_size_bytes": 300,
                    "storage_format": "sqlite3",
                    "metadata_version": 5,
                    "message_count": 4,
                    "topic_count": 2,
                    "ros_health": "readable",
                    "diagnostic_code": None,
                    "diagnostic_message": None,
                    "source_present": True,
                    "last_seen_generation": 2,
                }
            )
        return _QueryResult(
            rows=[
                {
                    "role": "metadata",
                    "relative_path": "recording/metadata.yaml",
                    "size_bytes": 10,
                    "mtime_ns": 20,
                    "condition": "readable",
                    "diagnostic_code": None,
                    "diagnostic_message": None,
                }
            ]
        )


def test_detail_read_uses_one_repeatable_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _DetailConnection()
    monkeypatch.setattr(
        catalog_repository,
        "open_connection",
        lambda database_url: connection,
    )

    detail = catalog_repository.CatalogRepository(
        "postgresql:///catalog"
    ).get_recording(1)

    assert detail is not None
    assert detail.recording.ros_health == "readable"
    assert connection.isolation_level is IsolationLevel.REPEATABLE_READ
