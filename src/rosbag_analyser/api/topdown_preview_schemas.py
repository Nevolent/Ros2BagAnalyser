from __future__ import annotations

from pydantic import BaseModel

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.topdown_preview import TopdownPreviewDisplay

from .schemas import DiagnosticResponse, diagnostic_response


WARNING_MESSAGES = {
    "coverage_starts_before_recording": (
        "Top-down coverage starts before the ROS recording."
    ),
    "coverage_starts_after_recording": (
        "Top-down coverage starts after the ROS recording begins."
    ),
    "coverage_ends_before_recording": (
        "Top-down coverage ends before the ROS recording ends."
    ),
    "coverage_ends_after_recording": "Top-down coverage ends after the ROS recording.",
}


class TopdownArtifactResponse(BaseModel):
    mime_type: str
    size_bytes: str
    coverage_start_ns: str
    coverage_end_ns: str
    timestamp_provenance: str
    bounds: str
    warnings: list[DiagnosticResponse]
    media_url: str


class TopdownPreviewResponse(BaseModel):
    state: str
    global_duration_ns: str | None
    diagnostic: DiagnosticResponse | None
    artifact: TopdownArtifactResponse | None
    poll_after_ms: int | None


def topdown_preview_response(
    recording_id: int, display: TopdownPreviewDisplay
) -> TopdownPreviewResponse:
    artifact = None
    if display.artifact is not None:
        raw_warnings = display.artifact.manifest.get("warnings", [])
        warnings: list[DiagnosticResponse] = []
        if isinstance(raw_warnings, list):
            warnings = [
                diagnostic_response(SafeDiagnostic(code, WARNING_MESSAGES[code]))
                for code in raw_warnings
                if isinstance(code, str) and code in WARNING_MESSAGES
            ]
        artifact = TopdownArtifactResponse(
            mime_type=display.artifact.mime_type,
            size_bytes=str(display.artifact.size_bytes),
            coverage_start_ns=str(display.artifact.coverage_start_ns),
            coverage_end_ns=str(display.artifact.coverage_end_ns),
            timestamp_provenance="csv_unix_timestamp",
            bounds="measured",
            warnings=warnings,
            media_url=(
                f"/api/recordings/{recording_id}/topdown-preview/media/"
                f"{display.artifact.id}"
            ),
        )
    return TopdownPreviewResponse(
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
