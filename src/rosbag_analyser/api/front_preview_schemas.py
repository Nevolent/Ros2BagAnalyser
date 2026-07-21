from __future__ import annotations

from pydantic import BaseModel

from rosbag_analyser.front_preview import PreviewDisplay

from .schemas import DiagnosticResponse, diagnostic_response


class PreviewArtifactResponse(BaseModel):
    mime_type: str
    size_bytes: str
    coverage_start_ns: str
    coverage_end_ns: str
    timestamp_provenance: str
    bounds: str
    media_url: str


class FrontPreviewResponse(BaseModel):
    state: str
    global_duration_ns: str | None
    diagnostic: DiagnosticResponse | None
    artifact: PreviewArtifactResponse | None
    poll_after_ms: int | None


def front_preview_response(
    recording_id: int, display: PreviewDisplay
) -> FrontPreviewResponse:
    artifact = None
    if display.artifact is not None:
        artifact = PreviewArtifactResponse(
            mime_type=display.artifact.mime_type,
            size_bytes=str(display.artifact.size_bytes),
            coverage_start_ns=str(display.artifact.coverage_start_ns),
            coverage_end_ns=str(display.artifact.coverage_end_ns),
            timestamp_provenance="ros_record_timestamp",
            bounds="measured",
            media_url=(
                f"/api/recordings/{recording_id}/front-preview/media/"
                f"{display.artifact.id}"
            ),
        )
    return FrontPreviewResponse(
        state=display.state,
        global_duration_ns=(
            None if display.duration_ns is None else str(display.duration_ns)
        ),
        diagnostic=(
            None
            if display.diagnostic is None
            else diagnostic_response(display.diagnostic)
        ),
        artifact=artifact,
        poll_after_ms=1_000 if display.state in {"queued", "processing"} else None,
    )
