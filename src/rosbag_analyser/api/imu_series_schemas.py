from __future__ import annotations

from pydantic import BaseModel

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.imu_series import (
    IMU_COMPONENT,
    IMU_DISPLAY_LABEL,
    IMU_UNITS,
    ImuSeriesDisplay,
)

from .schemas import DiagnosticResponse, diagnostic_response


WARNING_MESSAGES = {
    "coverage_starts_before_recording": "IMU coverage starts before the ROS recording.",
    "coverage_starts_after_recording": "IMU coverage starts after the ROS recording begins.",
    "coverage_ends_before_recording": "IMU coverage ends before the ROS recording ends.",
    "coverage_ends_after_recording": "IMU coverage ends after the ROS recording.",
    "non_finite_values_present": (
        "Some IMU values are non-finite and appear as explicit graph gaps."
    ),
}


class ImuArtifactResponse(BaseModel):
    mime_type: str
    size_bytes: str
    coverage_start_ns: str
    coverage_end_ns: str
    timestamp_provenance: str
    bounds: str
    display_label: str
    topic: str
    component: str
    units: str
    source_sample_count: str
    delivered_sample_count: str
    finite_sample_count: str
    non_finite_sample_count: str
    minimum_value: float
    maximum_value: float
    reduction_method: str
    warnings: list[DiagnosticResponse]
    data_url: str


class ImuSeriesResponse(BaseModel):
    state: str
    global_duration_ns: str | None
    diagnostic: DiagnosticResponse | None
    artifact: ImuArtifactResponse | None
    poll_after_ms: int | None


def imu_series_response(
    recording_id: int, display: ImuSeriesDisplay
) -> ImuSeriesResponse:
    artifact = None
    if display.artifact is not None:
        manifest = display.artifact.manifest
        source = _mapping(manifest.get("source"))
        samples = _mapping(manifest.get("samples"))
        reduction = _mapping(manifest.get("reduction"))
        raw_warnings = manifest.get("warnings", [])
        warnings: list[DiagnosticResponse] = []
        if isinstance(raw_warnings, list):
            warnings = [
                diagnostic_response(SafeDiagnostic(code, WARNING_MESSAGES[code]))
                for code in raw_warnings
                if isinstance(code, str) and code in WARNING_MESSAGES
            ]
        artifact = ImuArtifactResponse(
            mime_type=display.artifact.mime_type,
            size_bytes=str(display.artifact.size_bytes),
            coverage_start_ns=str(display.artifact.coverage_start_ns),
            coverage_end_ns=str(display.artifact.coverage_end_ns),
            timestamp_provenance="ros_record_timestamp",
            bounds="measured",
            display_label=IMU_DISPLAY_LABEL,
            topic=_text(source.get("topic"), "Configured IMU topic"),
            component=_text(source.get("component"), IMU_COMPONENT),
            units=IMU_UNITS,
            source_sample_count=str(_integer(samples.get("source"))),
            delivered_sample_count=str(_integer(samples.get("delivered"))),
            finite_sample_count=str(_integer(samples.get("finite"))),
            non_finite_sample_count=str(_integer(samples.get("non_finite"))),
            minimum_value=_number(samples.get("minimum")),
            maximum_value=_number(samples.get("maximum")),
            reduction_method=_text(reduction.get("method"), "none"),
            warnings=warnings,
            data_url=(
                f"/api/recordings/{recording_id}/imu-series/data/"
                f"{display.artifact.id}"
            ),
        )
    return ImuSeriesResponse(
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


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _text(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)
