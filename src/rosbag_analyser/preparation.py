from __future__ import annotations

from dataclasses import dataclass
import logging
from collections.abc import Callable
from typing import Mapping

from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.processing_repository import (
    FRONT_PREVIEW_KIND,
    IMU_SERIES_KIND,
    PROCESSING_KINDS,
    TOPDOWN_PREVIEW_KIND,
    ArtifactRecord,
    CurrentOutputRecord,
    PreparationSchedule,
    ProcessingRepository,
)
from rosbag_analyser.preparation_planner import PreparationPlanner


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutputFact:
    kind: str
    state: str
    diagnostic: SafeDiagnostic | None = None
    artifact: ArtifactRecord | None = None
    job_id: int | None = None


@dataclass(frozen=True)
class RecordingAnalysis:
    recording_id: int
    analysis_state: str
    outputs: tuple[OutputFact, ...]


@dataclass(frozen=True)
class PrepareOutputResult:
    kind: str
    outcome: str
    state: str
    diagnostic: SafeDiagnostic | None = None
    artifact_id: int | None = None
    job_id: int | None = None


@dataclass(frozen=True)
class PrepareRecordingResult:
    recording_id: int
    outcome: str
    analysis_state: str
    outputs: tuple[PrepareOutputResult, ...]


@dataclass(frozen=True)
class PrepareSelectedResult:
    recordings: tuple[PrepareRecordingResult, ...]
    has_active_work: bool


class PreparationService:
    def __init__(
        self,
        catalog_repository: CatalogRepository,
        processing_repository: ProcessingRepository,
        planner: PreparationPlanner,
        artifact_stores: Mapping[str, ArtifactStore],
        *,
        admission_check: Callable[[], SafeDiagnostic | None] | None = None,
    ) -> None:
        self.catalog_repository = catalog_repository
        self.processing_repository = processing_repository
        self.planner = planner
        self.artifact_stores = dict(artifact_stores)
        self.admission_check = admission_check

    def states_for_recordings(
        self,
        recording_ids: tuple[int, ...],
        *,
        generation: int | None = None,
    ) -> tuple[RecordingAnalysis, ...]:
        if not recording_ids:
            return ()
        selected_generation = (
            self.catalog_repository.get_catalog_state().successful_generation
            if generation is None
            else generation
        )
        current = self.processing_repository.get_current_outputs(recording_ids)
        grouped: dict[int, dict[str, CurrentOutputRecord]] = {
            recording_id: {} for recording_id in recording_ids
        }
        for item in current:
            grouped.setdefault(item.target.recording_id, {})[item.target.kind] = item
        return tuple(
            self._analysis_for_group(
                recording_id,
                grouped.get(recording_id, {}),
                selected_generation,
            )
            for recording_id in recording_ids
        )

    def prepare_selected(
        self,
        recording_ids: tuple[int, ...],
        output_kinds: tuple[str, ...] = PROCESSING_KINDS,
    ) -> PrepareSelectedResult:
        selected_kinds = tuple(kind for kind in PROCESSING_KINDS if kind in output_kinds)
        if (
            not selected_kinds
            or len(output_kinds) != len(set(output_kinds))
            or set(selected_kinds) != set(output_kinds)
        ):
            raise ValueError("Select a unique non-empty set of supported outputs.")
        existing = self.processing_repository.get_current_outputs(recording_ids)
        invalid_by_recording: dict[int, dict[str, int]] = {}
        baseline_states: dict[int, dict[str, str]] = {
            recording_id: {kind: "unavailable" for kind in PROCESSING_KINDS}
            for recording_id in recording_ids
        }
        for current in existing:
            state = "not_requested"
            target = current.target
            if target.target_state != "available" or target.cache_identity is None:
                state = "unavailable"
            elif current.artifact is not None:
                diagnostic = self._validate_artifact(current.artifact)
                if diagnostic is None:
                    state = "ready"
                else:
                    state = "failed"
                    invalid_by_recording.setdefault(target.recording_id, {})[
                        target.kind
                    ] = current.artifact.id
            elif current.active_job is not None:
                state = (
                    "processing"
                    if current.active_job.state == "running"
                    else "queued"
                )
            elif current.latest_failed_job is not None:
                state = "failed"
            baseline_states.setdefault(target.recording_id, {})[target.kind] = state

        results: list[PrepareRecordingResult] = []
        has_active_work = False
        for recording_id in recording_ids:
            try:
                admission_diagnostic = (
                    None if self.admission_check is None else self.admission_check()
                )
                schedule = self.processing_repository.prepare_recording(
                    recording_id,
                    self.planner.planner_identities,
                    output_kinds=selected_kinds,
                    invalid_artifact_ids=invalid_by_recording.get(recording_id),
                    admission_diagnostic=admission_diagnostic,
                )
            except Exception:
                logger.exception(
                    "Preparation scheduling failed for recording %s.", recording_id
                )
                outputs = tuple(
                    PrepareOutputResult(
                        kind=kind,
                        outcome="request_failed",
                        state="unavailable",
                        diagnostic=SafeDiagnostic(
                            "preparation_request_failed",
                            "This recording could not be scheduled. The request can be repeated safely.",
                        ),
                    )
                    for kind in selected_kinds
                )
                results.append(
                    PrepareRecordingResult(
                        recording_id,
                        "request_failed",
                        "not_planned",
                        outputs,
                    )
                )
                continue
            result = self._result_from_schedule(schedule, selected_kinds)
            current_states = baseline_states[recording_id]
            for output in result.outputs:
                current_states[output.kind] = output.state
            result = PrepareRecordingResult(
                result.recording_id,
                result.outcome,
                _aggregate_state(
                    tuple(current_states[kind] for kind in PROCESSING_KINDS)
                ),
                result.outputs,
            )
            has_active_work = has_active_work or any(
                output.state in {"queued", "processing"} for output in result.outputs
            )
            results.append(result)
        return PrepareSelectedResult(tuple(results), has_active_work)

    def _analysis_for_group(
        self,
        recording_id: int,
        grouped: Mapping[str, CurrentOutputRecord],
        generation: int,
    ) -> RecordingAnalysis:
        outputs: list[OutputFact] = []
        for kind in PROCESSING_KINDS:
            current = grouped.get(kind)
            if current is None:
                outputs.append(
                    OutputFact(
                        kind,
                        "unavailable",
                        SafeDiagnostic(
                            "preparation_target_missing",
                            "Preparation targets require an explicit catalog rescan.",
                        ),
                    )
                )
                continue
            target = current.target
            if (
                target.scan_generation != generation
                or target.planner_identity != self.planner.planner_identity(kind)
            ):
                outputs.append(
                    OutputFact(
                        kind,
                        "unavailable",
                        SafeDiagnostic(
                            "catalog_rescan_required",
                            "Preparation settings changed. Rescan the archive before requesting work.",
                        ),
                    )
                )
                continue
            if target.target_state != "available" or target.cache_identity is None:
                outputs.append(
                    OutputFact(
                        kind,
                        "unavailable",
                        _target_diagnostic(current),
                    )
                )
                continue
            if current.artifact is not None:
                diagnostic = self._validate_artifact(current.artifact)
                if diagnostic is None:
                    outputs.append(
                        OutputFact(kind, "ready", artifact=current.artifact)
                    )
                else:
                    outputs.append(OutputFact(kind, "failed", diagnostic))
                continue
            if current.active_job is not None:
                outputs.append(
                    OutputFact(
                        kind,
                        "processing"
                        if current.active_job.state == "running"
                        else "queued",
                        job_id=current.active_job.id,
                    )
                )
                continue
            if current.latest_failed_job is not None:
                failed = current.latest_failed_job
                outputs.append(
                    OutputFact(
                        kind,
                        "failed",
                        SafeDiagnostic(
                            failed.error_code or "processing_failed",
                            failed.error_message or "Processing failed.",
                        ),
                        job_id=failed.id,
                    )
                )
                continue
            outputs.append(OutputFact(kind, "not_requested"))
        return RecordingAnalysis(
            recording_id,
            _aggregate_state(tuple(output.state for output in outputs)),
            tuple(outputs),
        )

    def _validate_artifact(self, artifact: ArtifactRecord) -> SafeDiagnostic | None:
        store = self.artifact_stores.get(artifact.kind)
        if store is None:
            return SafeDiagnostic(
                "artifact_validator_unavailable",
                "The generated output cannot be validated by this application instance.",
            )
        try:
            if artifact.kind == IMU_SERIES_KIND:
                store.validate_series_artifact(
                    artifact.output_relative_path,
                    artifact.size_bytes,
                    artifact.cache_identity,
                    artifact.manifest,
                )
            else:
                store.validate_media(
                    artifact.output_relative_path,
                    artifact.size_bytes,
                    artifact.cache_identity,
                    artifact.manifest,
                )
        except ArtifactStoreError as error:
            return SafeDiagnostic(error.code, error.safe_message)
        return None

    @staticmethod
    def _result_from_schedule(
        schedule: PreparationSchedule,
        output_kinds: tuple[str, ...] = PROCESSING_KINDS,
    ) -> PrepareRecordingResult:
        if not schedule.recording_found:
            outputs = tuple(
                PrepareOutputResult(kind, "not_found", "unavailable")
                for kind in output_kinds
            )
            return PrepareRecordingResult(
                schedule.recording_id,
                "not_found",
                "not_planned",
                outputs,
            )
        outputs = tuple(
            PrepareOutputResult(
                kind=item.kind,
                outcome=item.outcome,
                state=item.state,
                diagnostic=(
                    SafeDiagnostic(item.diagnostic_code, item.diagnostic_message)
                    if item.diagnostic_code is not None
                    and item.diagnostic_message is not None
                    else (
                        None
                        if item.target is None
                        or item.target.diagnostic_code is None
                        or item.target.diagnostic_message is None
                        else SafeDiagnostic(
                            item.target.diagnostic_code,
                            item.target.diagnostic_message,
                        )
                    )
                ),
                artifact_id=None if item.artifact is None else item.artifact.id,
                job_id=None if item.job is None else item.job.id,
            )
            for item in schedule.outputs
        )
        analysis_state = _aggregate_state(tuple(item.state for item in outputs))
        outcome = (
            "unavailable"
            if outputs and all(item.outcome == "unavailable" for item in outputs)
            else "accepted"
        )
        return PrepareRecordingResult(
            schedule.recording_id,
            outcome,
            analysis_state,
            outputs,
        )


def _target_diagnostic(current: CurrentOutputRecord) -> SafeDiagnostic:
    target = current.target
    if target.diagnostic_code is not None and target.diagnostic_message is not None:
        return SafeDiagnostic(target.diagnostic_code, target.diagnostic_message)
    return SafeDiagnostic(
        "preparation_unavailable",
        "This output is unavailable for preparation.",
    )


def _aggregate_state(states: tuple[str, ...]) -> str:
    if "processing" in states:
        return "processing"
    if "queued" in states:
        return "queued"
    if "failed" in states:
        return "failed"
    if states and all(state == "ready" for state in states):
        return "ready"
    return "not_planned"


__all__ = [
    "OutputFact",
    "PreparationService",
    "PrepareSelectedResult",
    "RecordingAnalysis",
]
