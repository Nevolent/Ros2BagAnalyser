from __future__ import annotations

from pydantic import BaseModel

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.imu_series import (
    IMU_SERIES_BY_COMPONENT,
    IMU_SERIES_DEFINITIONS,
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


class ImuSeriesOptionResponse(BaseModel):
    id: str
    component: str
    display_label: str
    units: str
    column_index: int
    finite_sample_count: str
    non_finite_sample_count: str
    minimum_value: float | None
    maximum_value: float | None
    available: bool


class ImuArtifactResponse(BaseModel):
    mime_type: str
    size_bytes: str
    coverage_start_ns: str
    coverage_end_ns: str
    timestamp_provenance: str
    bounds: str
    topic: str
    default_series_id: str
    source_sample_count: str
    delivered_sample_count: str
    duplicate_timestamp_count: str
    series: list[ImuSeriesOptionResponse]
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
        series = _series_responses(manifest.get("series"))
        default_component = _text(
            source.get("default_component"), "angular_velocity.z"
        )
        default_definition = IMU_SERIES_BY_COMPONENT.get(
            default_component,
            IMU_SERIES_BY_COMPONENT["angular_velocity.z"],
        )
        default_series_id = _text(
            source.get("default_series_id"), default_definition.id
        )
        available_series_ids = {
            option.id for option in series if option.available
        }
        if default_series_id not in available_series_ids:
            default_series_id = next(
                (
                    option.id
                    for option in series
                    if option.id in available_series_ids
                ),
                default_series_id,
            )
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
            topic=_text(source.get("topic"), "Configured IMU topic"),
            default_series_id=default_series_id,
            source_sample_count=str(_integer(samples.get("source"))),
            delivered_sample_count=str(_integer(samples.get("delivered"))),
            duplicate_timestamp_count=str(
                _integer(samples.get("duplicate_timestamps"))
            ),
            series=series,
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


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _series_responses(value: object) -> list[ImuSeriesOptionResponse]:
    raw_items = value if isinstance(value, list) else []
    by_id = {
        item.get("id"): item
        for item in raw_items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    responses: list[ImuSeriesOptionResponse] = []
    for definition in IMU_SERIES_DEFINITIONS:
        item = by_id.get(definition.id, {})
        finite_count = _integer(item.get("finite"))
        non_finite_count = _integer(item.get("non_finite"))
        responses.append(
            ImuSeriesOptionResponse(
                id=definition.id,
                component=definition.component,
                display_label=definition.display_label,
                units=definition.units,
                column_index=definition.column_index,
                finite_sample_count=str(finite_count),
                non_finite_sample_count=str(non_finite_count),
                minimum_value=_optional_number(item.get("minimum")),
                maximum_value=_optional_number(item.get("maximum")),
                available=item.get("available") is True and finite_count > 0,
            )
        )
    return responses
