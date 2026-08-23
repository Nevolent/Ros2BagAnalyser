from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from collections.abc import Callable

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.processing_repository import (
    ProcessingJobViewRecord,
    ProcessingRepository,
    RetrySchedule,
)
from rosbag_analyser.preparation_planner import PreparationPlanner


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
    runtime_ms: int | None
    diagnostic: SafeDiagnostic | None
    output_size_bytes: int | None
    queue_position: int | None
    estimate: EstimateView | None


@dataclass(frozen=True)
class ProcessingOverview:
    server_time: datetime
    worker_online: bool
    running_count: int
    queued_count: int
    failed_count: int
    succeeded_count: int
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
        return ProcessingOverview(
            server_time=data.server_time,
            worker_online=self.repository.worker_online(self.worker_lock_name),
            running_count=data.running_count,
            queued_count=data.queued_count,
            failed_count=data.failed_count,
            succeeded_count=data.succeeded_count,
            current=(
                None
                if data.running is None
                else _job_view(data.running, data.server_time)
            ),
            queue=tuple(_job_view(item, data.server_time) for item in data.queue),
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
        if view not in {"queued", "failed", "history"}:
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
            timestamp = last.queued_at if view == "queued" else last.finished_at
            if timestamp is not None:
                next_cursor = _encode_cursor(view, timestamp, last.id)
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


def _job_view(item: ProcessingJobViewRecord, server_time: datetime) -> ProcessingJobView:
    job = item.job
    queued_age = _duration_ms(server_time, job.queued_at)
    elapsed = (
        _duration_ms(server_time, job.started_at)
        if job.state == "running" and job.started_at is not None
        else None
    )
    runtime = (
        _duration_ms(job.finished_at, job.started_at)
        if job.finished_at is not None and job.started_at is not None
        else None
    )
    estimate = None
    if job.state == "running":
        if job.estimated_total_ms is None:
            estimate = EstimateView(
                "unavailable",
                None,
                None,
                job.estimate_method,
                job.estimate_sample_count,
            )
        elif elapsed is not None and elapsed >= job.estimated_total_ms:
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
                max(1, job.estimated_total_ms - (elapsed or 0)),
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
        runtime_ms=runtime,
        diagnostic=diagnostic,
        output_size_bytes=item.output_size_bytes,
        queue_position=item.queue_position,
        estimate=estimate,
    )


def _duration_ms(later: datetime, earlier: datetime) -> int:
    return max(0, int((later - earlier).total_seconds() * 1_000))


def _encode_cursor(view: str, timestamp: datetime, job_id: int) -> str:
    document = {
        "view": view,
        "timestamp": timestamp.isoformat(),
        "id": job_id,
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, view: str) -> tuple[datetime, int]:
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
            "timestamp",
            "id",
        }:
            raise ValueError
        if document["view"] != view:
            raise ValueError
        job_id = document["id"]
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError
        timestamp = datetime.fromisoformat(document["timestamp"])
        if timestamp.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise InvalidProcessingCursor("The processing cursor is invalid.") from error
    return timestamp, job_id


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
