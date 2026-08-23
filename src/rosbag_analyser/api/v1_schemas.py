from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from rosbag_analyser.catalog.service import RescanResult
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.catalog_repository import CatalogComponent
from rosbag_analyser.persistence.processing_repository import ArtifactRecord
from rosbag_analyser.preparation import (
    OutputFact,
    PrepareSelectedResult,
    RecordingAnalysis,
)
from rosbag_analyser.processing_view import (
    EstimateView,
    ProcessingJobView,
    ProcessingOverview,
    ProcessingPage,
    RetryResult,
)
from rosbag_analyser.v1_catalog import V1CatalogView, V1RecordingDetail


OutputKind = Literal["front_preview", "topdown_preview", "imu_series"]
OutputState = Literal[
    "unavailable", "ready", "processing", "queued", "failed", "not_requested"
]
AnalysisState = Literal["not_planned", "queued", "processing", "ready", "failed"]


class DiagnosticResponse(BaseModel):
    code: str
    message: str


class ScanCountsResponse(BaseModel):
    recordings: int
    readable: int
    damaged: int
    missing: int
    unsupported: int
    uninspectable: int


class ScanStateResponse(BaseModel):
    generation: int
    completed_at: datetime | None
    duration_ms: int
    counts: ScanCountsResponse


class CatalogSummaryResponse(BaseModel):
    recordings: int
    ready: int
    processing: int
    queued: int
    failed: int
    damaged: int


class FolderResponse(BaseModel):
    path: str
    parent_path: str
    name: str
    direct_recording_count: int
    descendant_recording_count: int


class OutputFactResponse(BaseModel):
    kind: OutputKind
    state: OutputState
    diagnostic: DiagnosticResponse | None


class CatalogRecordingResponse(BaseModel):
    id: int
    name: str
    folder_path: str
    start_time_ns: str | None
    duration_ns: str | None
    total_source_size_bytes: str | None
    storage_format: str | None
    topic_count: int | None
    ros_health: str
    presentation_health: Literal["readable", "damaged"]
    diagnostic: DiagnosticResponse | None
    analysis_state: AnalysisState
    outputs: list[OutputFactResponse]


class CatalogResponse(BaseModel):
    scan: ScanStateResponse
    summary: CatalogSummaryResponse
    folders: list[FolderResponse]
    recordings: list[CatalogRecordingResponse]


class SourceComponentResponse(BaseModel):
    role: str
    condition: str
    file_name: str | None
    size_bytes: str | None
    mtime_ns: str | None
    diagnostic: DiagnosticResponse | None


class ReadyArtifactResponse(BaseModel):
    id: int
    mime_type: str
    size_bytes: str
    coverage_start_ns: str
    coverage_end_ns: str
    timestamp_provenance: str | None
    url: str


class RecordingOutputResponse(OutputFactResponse):
    job_id: int | None
    artifact: ReadyArtifactResponse | None


class RecordingDetailResponse(CatalogRecordingResponse):
    metadata_version: int | None
    message_count: str | None
    source_present: bool
    components: list[SourceComponentResponse]
    outputs: list[RecordingOutputResponse]


class RescanDiagnosticResponse(BaseModel):
    recording_name: str
    diagnostic: DiagnosticResponse


class RescanResponse(BaseModel):
    scan: ScanStateResponse
    diagnostics: list[RescanDiagnosticResponse]


class PrepareSelectedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recording_ids: list[StrictInt] = Field(min_length=1, max_length=10_000)

    @field_validator("recording_ids")
    @classmethod
    def validate_recording_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Recording IDs must be positive integers.")
        if len(values) != len(set(values)):
            raise ValueError("Recording IDs must be unique.")
        return values


class PrepareOutputResponse(BaseModel):
    kind: OutputKind
    outcome: str
    state: str
    diagnostic: DiagnosticResponse | None
    artifact_id: int | None
    job_id: int | None


class PrepareRecordingResponse(BaseModel):
    recording_id: int
    outcome: str
    analysis_state: AnalysisState
    outputs: list[PrepareOutputResponse]


class PrepareSelectedResponse(BaseModel):
    recordings: list[PrepareRecordingResponse]


class EstimateResponse(BaseModel):
    status: Literal["available", "unavailable", "exceeded"]
    estimated_total_ms: int | None
    remaining_ms: int | None
    method: str | None
    sample_count: int | None


class ProcessingJobResponse(BaseModel):
    id: int
    recording_id: int
    recording_name: str
    kind: OutputKind
    state: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    queued_age_ms: int
    elapsed_ms: int | None
    runtime_ms: int | None
    diagnostic: DiagnosticResponse | None
    output_size_bytes: str | None
    queue_position: int | None
    estimate: EstimateResponse | None


class ProcessingOverviewResponse(BaseModel):
    server_time: datetime
    worker_online: bool
    running_count: int
    queued_count: int
    failed_count: int
    succeeded_count: int
    current: ProcessingJobResponse | None
    queue: list[ProcessingJobResponse]
    recommended_poll_interval_ms: int


class ProcessingJobsResponse(BaseModel):
    items: list[ProcessingJobResponse]
    next_cursor: str | None


class RetryResponse(BaseModel):
    outcome: str
    state: str
    recording_id: int | None
    kind: OutputKind | None
    job_id: int | None
    artifact_id: int | None
    diagnostic: DiagnosticResponse | None


def catalog_response(view: V1CatalogView) -> CatalogResponse:
    return CatalogResponse(
        scan=_scan_response(view.scan),
        summary=CatalogSummaryResponse(**view.summary),
        folders=[
            FolderResponse(
                path=item.path,
                parent_path=item.parent_path,
                name=item.name,
                direct_recording_count=item.direct_recording_count,
                descendant_recording_count=item.descendant_recording_count,
            )
            for item in view.folders
        ],
        recordings=[
            CatalogRecordingResponse(
                id=item.recording.id,
                name=item.recording.display_name,
                folder_path=item.folder_path,
                start_time_ns=_number_string(item.recording.start_time_ns),
                duration_ns=_number_string(item.recording.duration_ns),
                total_source_size_bytes=_number_string(
                    item.recording.total_source_size_bytes
                ),
                storage_format=item.recording.storage_format,
                topic_count=item.recording.topic_count,
                ros_health=item.recording.ros_health,
                presentation_health=item.presentation_health,
                diagnostic=_diagnostic(item.recording.diagnostic),
                analysis_state=item.analysis.analysis_state,
                outputs=[_output_fact(output) for output in item.analysis.outputs],
            )
            for item in view.recordings
        ],
    )


def recording_detail_response(detail: V1RecordingDetail) -> RecordingDetailResponse:
    recording = detail.detail.recording
    return RecordingDetailResponse(
        id=recording.id,
        name=recording.display_name,
        folder_path=detail.folder_path,
        start_time_ns=_number_string(recording.start_time_ns),
        duration_ns=_number_string(recording.duration_ns),
        total_source_size_bytes=_number_string(recording.total_source_size_bytes),
        storage_format=recording.storage_format,
        topic_count=recording.topic_count,
        ros_health=recording.ros_health,
        presentation_health=detail.presentation_health,
        diagnostic=_diagnostic(recording.diagnostic),
        analysis_state=detail.analysis.analysis_state,
        metadata_version=recording.metadata_version,
        message_count=_number_string(recording.message_count),
        source_present=recording.source_present,
        components=[_component(item) for item in detail.detail.components],
        outputs=[
            RecordingOutputResponse(
                **_output_fact(output).model_dump(),
                job_id=output.job_id,
                artifact=(
                    None
                    if output.artifact is None
                    else _artifact_response(recording.id, output.artifact)
                ),
            )
            for output in detail.analysis.outputs
        ],
    )


def rescan_response(result: RescanResult) -> RescanResponse:
    counts = ScanCountsResponse(
        recordings=result.recording_count,
        readable=result.readable_count,
        damaged=result.damaged_count,
        missing=result.missing_count,
        unsupported=result.unsupported_count,
        uninspectable=result.uninspectable_count,
    )
    return RescanResponse(
        scan=ScanStateResponse(
            generation=result.generation,
            completed_at=result.completed_at,
            duration_ms=result.duration_ms,
            counts=counts,
        ),
        diagnostics=[
            RescanDiagnosticResponse(
                recording_name=item.recording_name,
                diagnostic=DiagnosticResponse(
                    code=item.diagnostic.code,
                    message=item.diagnostic.message,
                ),
            )
            for item in result.diagnostics
        ],
    )


def prepare_response(result: PrepareSelectedResult) -> PrepareSelectedResponse:
    return PrepareSelectedResponse(
        recordings=[
            PrepareRecordingResponse(
                recording_id=item.recording_id,
                outcome=item.outcome,
                analysis_state=item.analysis_state,
                outputs=[
                    PrepareOutputResponse(
                        kind=output.kind,
                        outcome=output.outcome,
                        state=output.state,
                        diagnostic=_diagnostic(output.diagnostic),
                        artifact_id=output.artifact_id,
                        job_id=output.job_id,
                    )
                    for output in item.outputs
                ],
            )
            for item in result.recordings
        ]
    )


def processing_overview_response(
    view: ProcessingOverview,
) -> ProcessingOverviewResponse:
    return ProcessingOverviewResponse(
        server_time=view.server_time,
        worker_online=view.worker_online,
        running_count=view.running_count,
        queued_count=view.queued_count,
        failed_count=view.failed_count,
        succeeded_count=view.succeeded_count,
        current=None if view.current is None else _job_response(view.current),
        queue=[_job_response(item) for item in view.queue],
        recommended_poll_interval_ms=view.recommended_poll_interval_ms,
    )


def processing_jobs_response(view: ProcessingPage) -> ProcessingJobsResponse:
    return ProcessingJobsResponse(
        items=[_job_response(item) for item in view.items],
        next_cursor=view.next_cursor,
    )


def retry_response(result: RetryResult) -> RetryResponse:
    return RetryResponse(
        outcome=result.outcome,
        state=result.state,
        recording_id=result.recording_id,
        kind=result.kind,
        job_id=result.job_id,
        artifact_id=result.artifact_id,
        diagnostic=_diagnostic(result.diagnostic),
    )


def _scan_response(scan) -> ScanStateResponse:
    return ScanStateResponse(
        generation=scan.successful_generation,
        completed_at=scan.successful_completed_at,
        duration_ms=scan.duration_ms,
        counts=ScanCountsResponse(
            recordings=scan.recording_count,
            readable=scan.readable_count,
            damaged=scan.damaged_count,
            missing=scan.missing_count,
            unsupported=scan.unsupported_count,
            uninspectable=scan.uninspectable_count,
        ),
    )


def _output_fact(output: OutputFact) -> OutputFactResponse:
    return OutputFactResponse(
        kind=output.kind,
        state=output.state,
        diagnostic=_diagnostic(output.diagnostic),
    )


def _component(component: CatalogComponent) -> SourceComponentResponse:
    return SourceComponentResponse(
        role=component.role,
        condition=component.condition,
        file_name=component.display_name,
        size_bytes=_number_string(component.size_bytes),
        mtime_ns=_number_string(component.mtime_ns),
        diagnostic=_diagnostic(component.diagnostic),
    )


def _artifact_response(
    recording_id: int, artifact: ArtifactRecord
) -> ReadyArtifactResponse:
    if artifact.kind == "front_preview":
        url = f"/api/recordings/{recording_id}/front-preview/media/{artifact.id}"
    elif artifact.kind == "topdown_preview":
        url = f"/api/recordings/{recording_id}/topdown-preview/media/{artifact.id}"
    else:
        url = f"/api/recordings/{recording_id}/imu-series/data/{artifact.id}"
    timing = artifact.manifest.get("timing")
    provenance = None
    if isinstance(timing, dict):
        value = timing.get("timestamp_provenance")
        if isinstance(value, str) and 0 < len(value) <= 100:
            provenance = value
    return ReadyArtifactResponse(
        id=artifact.id,
        mime_type=artifact.mime_type,
        size_bytes=str(artifact.size_bytes),
        coverage_start_ns=str(artifact.coverage_start_ns),
        coverage_end_ns=str(artifact.coverage_end_ns),
        timestamp_provenance=provenance,
        url=url,
    )


def _job_response(item: ProcessingJobView) -> ProcessingJobResponse:
    return ProcessingJobResponse(
        id=item.id,
        recording_id=item.recording_id,
        recording_name=item.recording_name,
        kind=item.kind,
        state=item.state,
        queued_at=item.queued_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
        queued_age_ms=item.queued_age_ms,
        elapsed_ms=item.elapsed_ms,
        runtime_ms=item.runtime_ms,
        diagnostic=_diagnostic(item.diagnostic),
        output_size_bytes=_number_string(item.output_size_bytes),
        queue_position=item.queue_position,
        estimate=None if item.estimate is None else _estimate(item.estimate),
    )


def _estimate(item: EstimateView) -> EstimateResponse:
    return EstimateResponse(
        status=item.status,
        estimated_total_ms=item.estimated_total_ms,
        remaining_ms=item.remaining_ms,
        method=item.method,
        sample_count=item.sample_count,
    )


def _diagnostic(value: SafeDiagnostic | None) -> DiagnosticResponse | None:
    if value is None:
        return None
    return DiagnosticResponse(code=value.code, message=value.message)


def _number_string(value: int | None) -> str | None:
    return None if value is None else str(value)
