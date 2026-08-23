from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from rosbag_analyser.persistence.processing_repository import (
    JobRecord,
    ProcessingJobViewRecord,
    RetrySchedule,
    ScheduledOutput,
)
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.processing_view import (
    InvalidProcessingCursor,
    ProcessingViewService,
    _decode_cursor,
    _encode_cursor,
    _job_view,
)


def _running(*, total_ms: int | None, started_ago_ms: int) -> ProcessingJobViewRecord:
    now = datetime.now(timezone.utc)
    return ProcessingJobViewRecord(
        job=JobRecord(
            id=7,
            recording_id=3,
            kind="front_preview",
            cache_identity="a" * 64,
            state="running",
            queued_at=now - timedelta(seconds=2),
            started_at=now - timedelta(milliseconds=started_ago_ms),
            finished_at=None,
            error_code=None,
            error_message=None,
            work_units=100,
            estimate_key="b" * 64,
            estimated_total_ms=total_ms,
            estimate_method=(
                "median_rate_v1" if total_ms is not None else "insufficient_history"
            ),
            estimate_sample_count=2 if total_ms is not None else 1,
        ),
        recording_name="run",
    )


def test_running_estimate_reports_available_exceeded_and_unavailable() -> None:
    now = datetime.now(timezone.utc)

    available = _job_view(_running(total_ms=2_000, started_ago_ms=500), now)
    exceeded = _job_view(_running(total_ms=100, started_ago_ms=500), now)
    unavailable = _job_view(_running(total_ms=None, started_ago_ms=500), now)

    assert available.estimate is not None
    assert available.estimate.status == "available"
    assert available.estimate.remaining_ms is not None
    assert available.estimate.remaining_ms > 0
    assert exceeded.estimate is not None
    assert exceeded.estimate.status == "exceeded"
    assert exceeded.estimate.remaining_ms is None
    assert unavailable.estimate is not None
    assert unavailable.estimate.status == "unavailable"


def test_cursor_round_trip_is_view_bound_and_rejects_tampering() -> None:
    timestamp = datetime.now(timezone.utc)
    cursor = _encode_cursor("history", timestamp, 42)

    decoded = _decode_cursor(cursor, "history")

    assert decoded == (timestamp, 42)
    with pytest.raises(InvalidProcessingCursor):
        _decode_cursor(cursor, "failed")
    with pytest.raises(InvalidProcessingCursor):
        _decode_cursor(cursor[:-1] + "!", "history")


def test_processing_page_bounds_are_checked_before_repository_access() -> None:
    class Repository:
        def list_processing_jobs(self, *args, **kwargs):
            raise AssertionError("Invalid bounds must not reach PostgreSQL.")

    service = ProcessingViewService(
        Repository(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        worker_lock_name="worker",
    )

    with pytest.raises(ValueError, match="limit"):
        service.jobs("history", limit=101)
    with pytest.raises(ValueError, match="search"):
        service.jobs("history", search="x" * 101)
    with pytest.raises(ValueError, match="view"):
        service.jobs("unknown")


def test_retry_passes_capacity_admission_without_inventing_a_failure() -> None:
    class Repository:
        def __init__(self) -> None:
            self.diagnostic = None

        def retry_failed_job(
            self, failed_job_id, planner_identities, *, admission_diagnostic=None
        ):
            del failed_job_id, planner_identities
            self.diagnostic = admission_diagnostic
            return RetrySchedule(
                True,
                True,
                ScheduledOutput(
                    "front_preview",
                    "unavailable",
                    "unavailable",
                    diagnostic_code=admission_diagnostic.code,
                    diagnostic_message=admission_diagnostic.message,
                ),
            )

    repository = Repository()
    service = ProcessingViewService(
        repository,  # type: ignore[arg-type]
        type("Planner", (), {"planner_identities": {}})(),  # type: ignore[arg-type]
        worker_lock_name="worker",
        admission_check=lambda: SafeDiagnostic(
            "derived_space_low",
            "New preparation is paused because derived storage is low on space.",
        ),
    )

    result = service.retry(9)

    assert repository.diagnostic is not None
    assert result.outcome == "unavailable"
    assert result.state == "unavailable"
    assert result.diagnostic is not None
    assert result.diagnostic.code == "derived_space_low"
