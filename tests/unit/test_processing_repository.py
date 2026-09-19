from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
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


def test_worker_checkpoint_reuses_worker_session_and_commits_each_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction_count = 0

    class WorkerConnection:
        @contextmanager
        def transaction(self):
            nonlocal transaction_count
            yield self
            transaction_count += 1

    connection = WorkerConnection()
    repository = processing_repository.ProcessingRepository("unused")
    repository.set_worker_control_connection(connection)  # type: ignore[arg-type]
    monkeypatch.setattr(
        processing_repository,
        "open_connection",
        lambda _: pytest.fail("worker checkpoint opened another database session"),
    )
    monkeypatch.setattr(
        processing_repository,
        "_select_job_for_update",
        lambda selected_connection, _job_id: (
            {"state": "running"} if selected_connection is connection else None
        ),
    )
    monkeypatch.setattr(
        processing_repository,
        "_job_from_row",
        lambda _row: SimpleNamespace(
            state="running", control_state="cancel_requested", execution_phase="processing"
        ),
    )

    assert repository.worker_checkpoint(7, "processing").state == "running"
    assert repository.worker_checkpoint(7, "processing").state == "running"
    assert transaction_count == 2


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


@pytest.mark.parametrize(
    ("selected", "direction", "expected"),
    [
        ((4, 5, 6), "earlier", [4, 5, 6, 1, 2, 3, 7]),
        ((1, 2, 3), "later", [4, 5, 6, 1, 2, 3, 7]),
        ((4,), "earlier", [4, 5, 6, 1, 2, 3, 7]),
    ],
)
def test_queue_move_crosses_a_whole_recording(monkeypatch, selected, direction, expected):
    rows = [
        {"id": job_id, "recording_id": recording_id, "queue_order": job_id}
        for job_id, recording_id in [(1, 10), (2, 10), (3, 10), (4, 20), (5, 20), (6, 20), (7, 30)]
    ]
    updates = []

    class Result:
        def __init__(self, data):
            self.data = data

        def fetchall(self):
            return self.data

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, statement, parameters=None):
            if "SELECT * FROM jobs" in statement:
                return Result(rows)
            if "UPDATE jobs" in statement:
                updates.append(parameters[1])
            return Result([])

    monkeypatch.setattr(processing_repository, "open_connection", lambda _: Connection())
    result = processing_repository.ProcessingRepository("unused").reorder_jobs(selected, direction)
    assert result.outcome == "reordered"
    assert updates == expected
