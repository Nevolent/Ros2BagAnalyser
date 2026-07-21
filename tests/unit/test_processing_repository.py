from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from rosbag_analyser.persistence import processing_repository


class _QueryResult:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, object] | None:
        return self.row


class _StateConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> "_StateConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> _QueryResult:
        del parameters
        normalized = " ".join(statement.split())
        self.statements.append(normalized)
        if "state IN ('queued', 'running')" in normalized:
            now = datetime.now(timezone.utc)
            return _QueryResult(
                {
                    "id": 7,
                    "recording_id": 11,
                    "kind": "front_preview",
                    "cache_identity": "a" * 64,
                    "state": "queued",
                    "queued_at": now,
                    "started_at": None,
                    "finished_at": None,
                    "error_code": None,
                    "error_message": None,
                }
            )
        return _QueryResult()


def test_visible_processing_state_uses_one_repeatable_read_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _StateConnection()
    open_count = 0

    def open_once(database_url: str) -> _StateConnection:
        nonlocal open_count
        del database_url
        open_count += 1
        return connection

    monkeypatch.setattr(processing_repository, "open_connection", open_once)

    state = processing_repository.ProcessingRepository(
        "postgresql:///catalog"
    ).get_current_state(11, "front_preview", "a" * 64)

    assert open_count == 1
    assert connection.statements[0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    )
    assert state.artifact is None
    assert state.active_job is not None
    assert state.active_job.id == 7
    assert state.latest_failed_job is None
