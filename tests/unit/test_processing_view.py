from __future__ import annotations

from dataclasses import replace
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
    _with_cumulative_queue_estimates,
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


def test_paused_time_is_excluded_from_active_elapsed_and_estimate() -> None:
    now = datetime.now(timezone.utc)
    running = _running(total_ms=3_000, started_ago_ms=2_000)
    paused = replace(
        running,
        job=replace(
            running.job,
            control_state="paused",
            last_pause_acknowledged_at=now - timedelta(milliseconds=300),
            accumulated_paused_ms=500,
        ),
    )

    view = _job_view(paused, now)

    assert 1_950 <= (view.elapsed_ms or 0) <= 2_050
    assert 750 <= view.paused_ms <= 850
    assert 1_150 <= (view.active_elapsed_ms or 0) <= 1_250
    assert view.estimate is not None
    assert view.estimate.status == "unavailable"


def test_cumulative_queue_estimate_stops_after_unknown_predecessor() -> None:
    now = datetime.now(timezone.utc)
    current = _job_view(_running(total_ms=2_000, started_ago_ms=500), now)

    def queued(job_id: int, total_ms: int | None, position: int):
        record = ProcessingJobViewRecord(
            JobRecord(
                id=job_id,
                recording_id=3,
                kind="front_preview",
                cache_identity=str(job_id) * 64,
                state="queued",
                queued_at=now - timedelta(seconds=job_id),
                started_at=None,
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
                queue_order=position,
            ),
            f"run-{job_id}",
            queue_position=position,
        )
        return _job_view(record, now)

    queue = _with_cumulative_queue_estimates(
        (queued(1, 1_000, 1), queued(2, None, 2), queued(3, 2_000, 3)),
        current=current,
        worker_online=True,
    )

    assert queue[0].queue_estimate is not None
    assert queue[0].queue_estimate.status == "available"
    assert 2_450 <= (queue[0].queue_estimate.ready_in_ms or 0) <= 2_550
    assert [item.queue_estimate.status for item in queue[1:]] == [
        "unavailable",
        "unavailable",
    ]


def test_cursor_round_trip_is_view_bound_and_rejects_tampering() -> None:
    timestamp = datetime.now(timezone.utc)
    cursor = _encode_cursor("history", timestamp, 42)

    decoded = _decode_cursor(cursor, "history")

    assert decoded == (timestamp, 42)
    with pytest.raises(InvalidProcessingCursor):
        _decode_cursor(cursor, "failed")
    with pytest.raises(InvalidProcessingCursor):
        _decode_cursor(cursor[:-1] + "!", "history")

    queue_cursor = _encode_cursor("queued", 17, 43)
    assert _decode_cursor(queue_cursor, "queued") == (17, 43)


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


def test_bulk_retry_isolates_one_request_failure() -> None:
    class Repository:
        def retry_failed_job(
            self, failed_job_id, planner_identities, *, admission_diagnostic=None
        ):
            del planner_identities, admission_diagnostic
            if failed_job_id == 2:
                raise RuntimeError("private database detail")
            return RetrySchedule(False, False)

    service = ProcessingViewService(
        Repository(),  # type: ignore[arg-type]
        type("Planner", (), {"planner_identities": {}})(),  # type: ignore[arg-type]
        worker_lock_name="worker",
    )

    results = service.retry_many((1, 2, 3))

    assert [item.outcome for item in results] == [
        "not_found",
        "request_failed",
        "not_found",
    ]
    assert results[1].diagnostic is not None
    assert results[1].diagnostic.code == "processing_retry_request_failed"
    assert "private" not in results[1].diagnostic.message


def test_recording_progress_spans_outputs_and_the_worker_handoff() -> None:
    from rosbag_analyser.processing_view import _recording_progress

    now = datetime.now(timezone.utc)
    first = _running(total_ms=10_000, started_ago_ms=5_000)
    first = replace(first, job=replace(first.job, started_at=now - timedelta(seconds=5)))
    second = replace(first, job=replace(
        first.job, id=8, kind="topdown_preview", state="queued",
        started_at=None, estimated_total_ms=20_000,
    ))
    third = replace(second, job=replace(
        second.job, id=9, kind="imu_series", estimated_total_ms=5_000,
    ))
    progress = _recording_progress((first, second, third), now, worker_online=True)
    assert progress is not None
    assert progress.run_id == 7
    assert progress.elapsed_ms == 5_000
    assert progress.estimated_total_ms == 35_000

    completed = replace(first, job=replace(
        first.job, state="succeeded", finished_at=now, accumulated_paused_ms=1_000,
    ))
    handoff = _recording_progress((completed, second, third), now, worker_online=True)
    assert handoff is not None and handoff.waiting
    assert handoff.run_id == progress.run_id
    assert handoff.elapsed_ms == 4_000
    assert handoff.estimated_total_ms == progress.estimated_total_ms

    running = replace(second, job=replace(second.job, state="running", started_at=now))
    resumed = _recording_progress(
        (completed, running, third), now + timedelta(seconds=2), worker_online=True,
    )
    assert resumed is not None and not resumed.waiting
    assert resumed.run_id == progress.run_id
    assert resumed.active_job_id == 8
    assert resumed.elapsed_ms == 6_000
    assert resumed.estimated_total_ms == 35_000
    unknown = replace(third, job=replace(third.job, estimated_total_ms=None))
    unestimated = _recording_progress((completed, running, unknown), now, worker_online=True)
    assert unestimated is not None and unestimated.estimate_status == "unavailable"
    assert _recording_progress((second, third), now, worker_online=True) is None
    assert _recording_progress((completed,), now, worker_online=True) is None
