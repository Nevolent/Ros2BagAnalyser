from __future__ import annotations

from pydantic import BaseModel

from rosbag_analyser.catalog.service import RescanResult
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.catalog_repository import (
    CatalogComponent,
    CatalogRecording,
    CatalogRecordingDetail,
)


class DiagnosticResponse(BaseModel):
    code: str
    message: str


class RescanDiagnosticResponse(BaseModel):
    recording_name: str
    diagnostic: DiagnosticResponse


class RescanResponse(BaseModel):
    recording_count: int
    readable_count: int
    damaged_count: int
    missing_count: int
    unsupported_count: int
    uninspectable_count: int
    duration_ms: int
    diagnostics: list[RescanDiagnosticResponse]


class RecordingListItemResponse(BaseModel):
    id: int
    name: str
    start_time_ns: str | None
    duration_ns: str | None
    total_source_size_bytes: str | None
    storage_format: str | None
    topic_count: int | None
    ros_health: str
    diagnostic: DiagnosticResponse | None


class RecordingListResponse(BaseModel):
    items: list[RecordingListItemResponse]


class SourceComponentResponse(BaseModel):
    role: str
    condition: str
    file_name: str | None
    size_bytes: str | None
    mtime_ns: str | None
    diagnostic: DiagnosticResponse | None


class RecordingDetailResponse(RecordingListItemResponse):
    metadata_version: int | None
    message_count: str | None
    components: list[SourceComponentResponse]


def rescan_response(result: RescanResult) -> RescanResponse:
    return RescanResponse(
        recording_count=result.recording_count,
        readable_count=result.readable_count,
        damaged_count=result.damaged_count,
        missing_count=result.missing_count,
        unsupported_count=result.unsupported_count,
        uninspectable_count=result.uninspectable_count,
        duration_ms=result.duration_ms,
        diagnostics=[
            RescanDiagnosticResponse(
                recording_name=item.recording_name,
                diagnostic=diagnostic_response(item.diagnostic),
            )
            for item in result.diagnostics
        ],
    )


def recording_list_response(
    recordings: tuple[CatalogRecording, ...],
) -> RecordingListResponse:
    return RecordingListResponse(items=[recording_response(item) for item in recordings])


def recording_response(recording: CatalogRecording) -> RecordingListItemResponse:
    return RecordingListItemResponse(
        id=recording.id,
        name=recording.display_name,
        start_time_ns=_number_string(recording.start_time_ns),
        duration_ns=_number_string(recording.duration_ns),
        total_source_size_bytes=_number_string(recording.total_source_size_bytes),
        storage_format=recording.storage_format,
        topic_count=recording.topic_count,
        ros_health=recording.ros_health,
        diagnostic=_optional_diagnostic(recording.diagnostic),
    )


def recording_detail_response(
    detail: CatalogRecordingDetail,
) -> RecordingDetailResponse:
    recording = detail.recording
    return RecordingDetailResponse(
        **recording_response(recording).model_dump(),
        metadata_version=recording.metadata_version,
        message_count=_number_string(recording.message_count),
        components=[component_response(item) for item in detail.components],
    )


def component_response(component: CatalogComponent) -> SourceComponentResponse:
    return SourceComponentResponse(
        role=component.role,
        condition=component.condition,
        file_name=component.display_name,
        size_bytes=_number_string(component.size_bytes),
        mtime_ns=_number_string(component.mtime_ns),
        diagnostic=_optional_diagnostic(component.diagnostic),
    )


def diagnostic_response(diagnostic: SafeDiagnostic) -> DiagnosticResponse:
    return DiagnosticResponse(code=diagnostic.code, message=diagnostic.message)


def _optional_diagnostic(
    diagnostic: SafeDiagnostic | None,
) -> DiagnosticResponse | None:
    return None if diagnostic is None else diagnostic_response(diagnostic)


def _number_string(value: int | None) -> str | None:
    return None if value is None else str(value)
