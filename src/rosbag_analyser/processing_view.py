from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import logging
from collections.abc import Callable

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.processing_repository import (
    BulkJobControlResult,
    JobControlResult,
    ProcessingJobViewRecord,
    ProcessingRepository,
    QueueReorderResult,
    RetrySchedule,
)
from rosbag_analyser.preparation_planner import PreparationPlanner


logger = logging.getLogger(__name__)


DEFAULT_PROCESSING_LIMIT = 25
MAX_PROCESSING_LIMIT = 100
MAX_PROCESSING_SEARCH = 100
OVERVIEW_QUEUE_LIMIT = 20
RECOMMENDED_POLL_INTERVAL_MS = 1_000


@dataclass(frozen=True)
class EstimateView:
    status: str
    estimated_total_ms: int | None
    remaining_ms: int | None
    method: str | None
    sample_count: int | None


@dataclass(frozen=True)
class QueueEstimateView:
    status: str
    ready_in_ms: int | None
    method: str | None
    sample_count: int | None


@dataclass(frozen=True)
class ProcessingJobView:
    id: int
    recording_id: int
    recording_name: str
    kind: str
    state: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    queued_age_ms: int
    elapsed_ms: int | None
    active_elapsed_ms: int | None
    paused_ms: int
    runtime_ms: int | None
    diagnostic: SafeDiagnostic | None
    output_size_bytes: int | None
    queue_position: int | None
    estimate: EstimateView | None
    queue_estimate: QueueEstimateView | None
    control_state: str
    execution_phase: str | None
    control_revision: int
    allowed_controls: tuple[str, ...]


@dataclass(frozen=True)
class ProcessingOverview:
    server_time: datetime
    worker_online: bool
    running_count: int
    queued_count: int
    failed_count: int
    succeeded_count: int
    canceled_count: int
    current: ProcessingJobView | None
    queue: tuple[ProcessingJobView, ...]
    recommended_poll_interval_ms: int


@dataclass(frozen=True)
class ProcessingPage:
    items: tuple[ProcessingJobView, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class RetryResult:
    outcome: str
    state: str
    recording_id: int | None = None
    kind: str | None = None
    job_id: int | None = None
    artifact_id: int | None = None
    diagnostic: SafeDiagnostic | None = None


@dataclass(frozen=True)
class ControlResult:
    requested_job_id: int
    outcome: str
    job: ProcessingJobView | None


@dataclass(frozen=True)
class BulkControlResult:
    items: tuple[ControlResult, ...]


class InvalidProcessingCursor(ValueError):
    pass


class ProcessingViewService:
    def __init__(
        self,
        repository: ProcessingRepository,
        planner: PreparationPlanner,
        *,
        worker_lock_name: str,
        admission_check: Callable[[], SafeDiagnostic | None] | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.worker_lock_name = worker_lock_name
        self.admission_check = admission_check

    def overview(self) -> ProcessingOverview:
        data = self.repository.processing_overview(queue_limit=OVERVIEW_QUEUE_LIMIT)
        worker_online = self.repository.worker_online(self.worker_lock_name)
        current = (
            None
            if data.running is None
            else _job_view(data.running, data.server_time, worker_online=worker_online)
        )
        queue = tuple(
            _job_view(item, data.server_time, worker_online=worker_online)
            for item in data.queue
        )
        queue = _with_cumulative_queue_estimates(
            queue,
            current=current,
            worker_online=worker_online,
        )
        return ProcessingOverview(
            server_time=data.server_time,
            worker_online=worker_online,
            running_count=data.running_count,
            queued_count=data.queued_count,
            failed_count=data.failed_count,
            succeeded_count=data.succeeded_count,
            canceled_count=data.canceled_count,
            current=current,
            queue=queue,
            recommended_poll_interval_ms=RECOMMENDED_POLL_INTERVAL_MS,
        )

    def jobs(
        self,
        view: str,
        *,
        limit: int = DEFAULT_PROCESSING_LIMIT,
        cursor: str | None = None,
        search: str = "",
    ) -> ProcessingPage:
        if view not in {"queued", "failed", "history", "canceled"}:
            raise ValueError("The processing view is invalid.")
        if limit <= 0 or limit > MAX_PROCESSING_LIMIT:
            raise ValueError("The processing page limit is outside the accepted range.")
        if len(search) > MAX_PROCESSING_SEARCH:
            raise ValueError("The processing search is too long.")
        decoded = None if cursor is None else _decode_cursor(cursor, view)
        rows = self.repository.list_processing_jobs(
            view,
            limit=limit + 1,
            cursor=decoded,
            search=search,
        )
        delivered = rows[:limit]
        server_time = datetime.now(timezone.utc)
        next_cursor = None
        if len(rows) > limit and delivered:
            last = delivered[-1].job
            cursor_value = last.queue_order if view == "queued" else last.finished_at
            if cursor_value is not None:
                next_cursor = _encode_cursor(view, cursor_value, last.id)
        return ProcessingPage(
            tuple(_job_view(item, server_time) for item in delivered),
            next_cursor,
        )

    def retry(self, failed_job_id: int) -> RetryResult:
        admission_diagnostic = (
            None if self.admission_check is None else self.admission_check()
        )
        schedule = self.repository.retry_failed_job(
            failed_job_id,
            self.planner.planner_identities,
            admission_diagnostic=admission_diagnostic,
        )
        return _retry_result(schedule)

    def pause(self, job_id: int) -> ControlResult:
        return _control_result(job_id, self.repository.request_pause(job_id))

    def resume(self, job_id: int) -> ControlResult:
        return _control_result(job_id, self.repository.request_resume(job_id))

    def cancel(self, job_id: int) -> ControlResult:
        return _control_result(job_id, self.repository.cancel_job(job_id))

    def cancel_many(self, job_ids: tuple[int, ...]) -> BulkControlResult:
        result = self.repository.cancel_jobs(job_ids)
        return BulkControlResult(
            tuple(
                _control_result(job_id, item)
                for job_id, item in zip(job_ids, result.items, strict=True)
            )
        )

    def reorder(self, job_ids: tuple[int, ...], direction: str) -> BulkControlResult:
        result = self.repository.reorder_jobs(job_ids, direction)
        if result.outcome != "reordered":
            return BulkControlResult(
                tuple(ControlResult(job_id, "conflict", None) for job_id in job_ids)
            )
        views = {
            item.job.id: _job_view(item, datetime.now(timezone.utc))
            for item in result.jobs
        }
        return BulkControlResult(
            tuple(
                ControlResult(job_id, "reordered", views.get(job_id))
                for job_id in job_ids
            )
        )

    def retry_many(self, job_ids: tuple[int, ...]) -> tuple[RetryResult, ...]:
        results: list[RetryResult] = []
        for job_id in job_ids:
            try:
                results.append(self.retry(job_id))
            except Exception:
                logger.exception("Bulk retry item %s could not be resolved.", job_id)
                results.append(
                    RetryResult(
                        "request_failed",
                        "unavailable",
                        diagnostic=SafeDiagnostic(
                            "processing_retry_request_failed",
                            "This processing retry could not be resolved. The request can be repeated safely.",
                        ),
                    )
                )
        return tuple(results)


def _job_view(
    item: ProcessingJobViewRecord,
    server_time: datetime,
    *,
    worker_online: bool = True,
) -> ProcessingJobView:
    job = item.job
    queued_age = _duration_ms(server_time, job.queued_at)
    elapsed = (
        _duration_ms(server_time, job.started_at)
        if job.state == "running" and job.started_at is not None
        else None
    )
    live_paused_ms = 0
    if (
        job.state == "running"
        and job.control_state == "paused"
        and job.last_pause_acknowledged_at is not None
    ):
        live_paused_ms = _duration_ms(server_time, job.last_pause_acknowledged_at)
    paused_ms = job.accumulated_paused_ms + live_paused_ms
    active_elapsed = None if elapsed is None else max(0, elapsed - paused_ms)
    runtime = (
        _duration_ms(job.finished_at, job.started_at)
        if job.finished_at is not None and job.started_at is not None
        else None
    )
    estimate = None
    if job.state in {"running", "queued"}:
        if (
            job.state == "running"
            and (
                not worker_online
                or job.control_state in {
                    "pause_requested",
                    "paused",
                    "cancel_requested",
                }
            )
        ):
            estimate = EstimateView(
                "unavailable",
                job.estimated_total_ms,
                None,
                job.estimate_method,
                job.estimate_sample_count,
            )
        elif job.estimated_total_ms is None:
            estimate = EstimateView(
                "unavailable",
                None,
                None,
                job.estimate_method,
                job.estimate_sample_count,
            )
        elif job.state == "queued":
            estimate = EstimateView(
                "available",
                job.estimated_total_ms,
                None,
                job.estimate_method,
                job.estimate_sample_count,
            )
        elif active_elapsed is not None and active_elapsed >= job.estimated_total_ms:
            estimate = EstimateView(
                "exceeded",
                job.estimated_total_ms,
                None,
                job.estimate_method,
                job.estimate_sample_count,
            )
        else:
            estimate = EstimateView(
                "available",
                job.estimated_total_ms,
                max(1, job.estimated_total_ms - (active_elapsed or 0)),
                job.estimate_method,
                job.estimate_sample_count,
            )
    diagnostic = None
    if job.state == "failed":
        diagnostic = SafeDiagnostic(
            job.error_code or "processing_failed",
            job.error_message or "Processing failed.",
        )
    return ProcessingJobView(
        id=job.id,
        recording_id=job.recording_id,
        recording_name=item.recording_name,
        kind=job.kind,
        state=job.state,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        queued_age_ms=queued_age,
        elapsed_ms=elapsed,
        active_elapsed_ms=active_elapsed,
        paused_ms=paused_ms,
        runtime_ms=runtime,
        diagnostic=diagnostic,
        output_size_bytes=item.output_size_bytes,
        queue_position=item.queue_position,
        estimate=estimate,
        queue_estimate=None,
        control_state=job.control_state,
        execution_phase=job.execution_phase,
        control_revision=job.control_revision,
        allowed_controls=_allowed_controls(job),
    )


def _duration_ms(later: datetime, earlier: datetime) -> int:
    return max(0, int((later - earlier).total_seconds() * 1_000))


def _encode_cursor(view: str, value: datetime | int, job_id: int) -> str:
    document = {
        "view": view,
        "value": value.isoformat() if isinstance(value, datetime) else value,
        "id": job_id,
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, view: str) -> tuple[datetime | int, int]:
    if len(cursor) > 512:
        raise InvalidProcessingCursor("The processing cursor is invalid.")
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.b64decode(
            cursor + padding,
            altchars=b"-_",
            validate=True,
        )
        document = json.loads(raw.decode("utf-8"))
        if not isinstance(document, dict) or set(document) != {
            "view",
            "value",
            "id",
        }:
            raise ValueError
        if document["view"] != view:
            raise ValueError
        job_id = document["id"]
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError
        raw_value = document["value"]
        if view == "queued":
            if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value <= 0:
                raise ValueError
            value: datetime | int = raw_value
        else:
            value = datetime.fromisoformat(raw_value)
            if value.tzinfo is None:
                raise ValueError
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidProcessingCursor("The processing cursor is invalid.") from error
    return value, job_id


def _allowed_controls(job) -> tuple[str, ...]:
    if job.state == "queued":
        return ("cancel", "move_earlier", "move_later")
    if job.state != "running" or job.execution_phase == "publishing":
        return ()
    if job.control_state == "none":
        return ("pause", "cancel")
    if job.control_state in {"pause_requested", "paused"}:
        return ("resume", "cancel")
    return ()


def _with_cumulative_queue_estimates(
    queue: tuple[ProcessingJobView, ...],
    *,
    current: ProcessingJobView | None,
    worker_online: bool,
) -> tuple[ProcessingJobView, ...]:
    cumulative = 0
    available = worker_online
    confidence: int | None = None
    if current is not None:
        estimate = current.estimate
        if (
            current.control_state != "none"
            or estimate is None
            or estimate.status != "available"
            or estimate.remaining_ms is None
        ):
            available = False
        else:
            cumulative = estimate.remaining_ms
            confidence = estimate.sample_count
    result: list[ProcessingJobView] = []
    for item in queue:
        estimate = item.estimate
        if (
            not available
            or estimate is None
            or estimate.status != "available"
            or estimate.estimated_total_ms is None
        ):
            available = False
            queue_estimate = QueueEstimateView("unavailable", None, None, None)
        else:
            cumulative += estimate.estimated_total_ms
            confidence = (
                estimate.sample_count
                if confidence is None
                else min(confidence, estimate.sample_count or 0)
            )
            queue_estimate = QueueEstimateView(
                "available", cumulative, "cumulative_median_rate_v1", confidence
            )
        result.append(replace(item, queue_estimate=queue_estimate))
    return tuple(result)


def _control_result(requested_job_id: int, result: JobControlResult) -> ControlResult:
    if result.job is None:
        return ControlResult(requested_job_id, result.outcome, None)
    view = _job_view(
        ProcessingJobViewRecord(
            result.job, result.recording_name, queue_position=None
        ),
        datetime.now(timezone.utc),
    )
    return ControlResult(requested_job_id, result.outcome, view)


def _retry_result(schedule: RetrySchedule) -> RetryResult:
    if not schedule.job_found:
        return RetryResult("not_found", "unavailable")
    if not schedule.job_failed:
        return RetryResult("conflict", "unavailable")
    output = schedule.output
    if output is None:
        return RetryResult("request_failed", "unavailable")
    diagnostic = None
    if output.diagnostic_code is not None and output.diagnostic_message is not None:
        diagnostic = SafeDiagnostic(
            output.diagnostic_code,
            output.diagnostic_message,
        )
    elif (
        output.target is not None
        and output.target.diagnostic_code is not None
        and output.target.diagnostic_message is not None
    ):
        diagnostic = SafeDiagnostic(
            output.target.diagnostic_code,
            output.target.diagnostic_message,
        )
    return RetryResult(
        outcome=output.outcome,
        state=output.state,
        recording_id=None if output.target is None else output.target.recording_id,
        kind=output.kind,
        job_id=None if output.job is None else output.job.id,
        artifact_id=None if output.artifact is None else output.artifact.id,
        diagnostic=diagnostic,
    )


__all__ = [
    "InvalidProcessingCursor",
    "ProcessingViewService",
    "ProcessingOverview",
    "ProcessingPage",
    "RetryResult",
]
