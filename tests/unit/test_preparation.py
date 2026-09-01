from __future__ import annotations

from datetime import datetime, timezone

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.processing_repository import (
    PROCESSING_KINDS,
    ArtifactRecord,
    CurrentOutputRecord,
    JobRecord,
    PreparationTargetRecord,
    PreparationSchedule,
    ScheduledOutput,
)
from rosbag_analyser.preparation import PreparationService


GENERATION = 3
IDENTITY = "a" * 64


class FakePlanner:
    planner_identities = {kind: IDENTITY for kind in PROCESSING_KINDS}

    def planner_identity(self, kind: str) -> str:
        return self.planner_identities[kind]


class ValidStore:
    def validate_media(self, *args) -> None:
        return None

    def validate_series_artifact(self, *args) -> None:
        return None


def _target(kind: str, *, state: str = "available") -> PreparationTargetRecord:
    return PreparationTargetRecord(
        recording_id=7,
        kind=kind,
        scan_generation=GENERATION,
        planner_identity=IDENTITY,
        target_state=state,
        cache_identity="b" * 64 if state == "available" else None,
        diagnostic_code=None if state == "available" else "source_unavailable",
        diagnostic_message=None if state == "available" else "Source unavailable.",
        work_units=10 if state == "available" else None,
    )


def _job(kind: str, state: str) -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        id=10,
        recording_id=7,
        kind=kind,
        cache_identity="b" * 64,
        state=state,
        queued_at=now,
        started_at=now if state != "queued" else None,
        finished_at=now if state == "failed" else None,
        error_code="failed" if state == "failed" else None,
        error_message="Processing failed." if state == "failed" else None,
    )


def _artifact(kind: str) -> ArtifactRecord:
    return ArtifactRecord(
        id=20,
        recording_id=7,
        kind=kind,
        cache_identity="b" * 64,
        output_relative_path="safe/output",
        mime_type="application/json" if kind == "imu_series" else "video/mp4",
        size_bytes=10,
        coverage_start_ns=0,
        coverage_end_ns=1,
        manifest={"cache_identity": "b" * 64},
        created_at=datetime.now(timezone.utc),
    )


def _service() -> PreparationService:
    return PreparationService(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        FakePlanner(),  # type: ignore[arg-type]
        {kind: ValidStore() for kind in PROCESSING_KINDS},  # type: ignore[dict-item]
    )


def test_per_output_precedence_starts_with_unavailable() -> None:
    current = {
        kind: CurrentOutputRecord(
            _target(kind, state="unavailable"),
            artifact=_artifact(kind),
            active_job=_job(kind, "running"),
            latest_failed_job=_job(kind, "failed"),
        )
        for kind in PROCESSING_KINDS
    }

    analysis = _service()._analysis_for_group(7, current, GENERATION)

    assert [item.state for item in analysis.outputs] == [
        "unavailable",
        "unavailable",
        "unavailable",
    ]
    assert analysis.analysis_state == "not_planned"


def test_ready_artifact_precedes_active_and_failed_attempts() -> None:
    current = {
        kind: CurrentOutputRecord(
            _target(kind),
            artifact=_artifact(kind),
            active_job=_job(kind, "running"),
            latest_failed_job=_job(kind, "failed"),
        )
        for kind in PROCESSING_KINDS
    }

    analysis = _service()._analysis_for_group(7, current, GENERATION)

    assert all(item.state == "ready" for item in analysis.outputs)
    assert analysis.analysis_state == "ready"


def test_aggregate_precedence_is_processing_queued_failed_ready_not_planned() -> None:
    group = {
        "front_preview": CurrentOutputRecord(
            _target("front_preview"), active_job=_job("front_preview", "running")
        ),
        "topdown_preview": CurrentOutputRecord(
            _target("topdown_preview"), active_job=_job("topdown_preview", "queued")
        ),
        "imu_series": CurrentOutputRecord(
            _target("imu_series"), latest_failed_job=_job("imu_series", "failed")
        ),
    }
    service = _service()

    processing = service._analysis_for_group(7, group, GENERATION)
    group["front_preview"] = CurrentOutputRecord(_target("front_preview"))
    queued = service._analysis_for_group(7, group, GENERATION)
    group["topdown_preview"] = CurrentOutputRecord(_target("topdown_preview"))
    failed = service._analysis_for_group(7, group, GENERATION)
    group["imu_series"] = CurrentOutputRecord(_target("imu_series"))
    not_planned = service._analysis_for_group(7, group, GENERATION)

    assert processing.analysis_state == "processing"
    assert queued.analysis_state == "queued"
    assert failed.analysis_state == "failed"
    assert not_planned.analysis_state == "not_planned"


def test_missing_topdown_companion_is_optional_for_aggregate_readiness() -> None:
    group = {
        "front_preview": CurrentOutputRecord(
            _target("front_preview"), artifact=_artifact("front_preview")
        ),
        "topdown_preview": CurrentOutputRecord(
            _target("topdown_preview", state="unavailable")
        ),
        "imu_series": CurrentOutputRecord(
            _target("imu_series"), artifact=_artifact("imu_series")
        ),
    }
    topdown = group["topdown_preview"].target
    group["topdown_preview"] = CurrentOutputRecord(
        PreparationTargetRecord(
            **{
                **topdown.__dict__,
                "diagnostic_code": "topdown_video_unavailable",
                "diagnostic_message": "The top-down video companion is unavailable.",
            }
        )
    )

    analysis = _service()._analysis_for_group(7, group, GENERATION)

    assert analysis.analysis_state == "ready"
    assert analysis.outputs[1].state == "unavailable"


def test_invalid_topdown_source_remains_required_for_aggregate_readiness() -> None:
    group = {
        "front_preview": CurrentOutputRecord(
            _target("front_preview"), artifact=_artifact("front_preview")
        ),
        "topdown_preview": CurrentOutputRecord(
            _target("topdown_preview", state="unavailable")
        ),
        "imu_series": CurrentOutputRecord(
            _target("imu_series"), artifact=_artifact("imu_series")
        ),
    }

    analysis = _service()._analysis_for_group(7, group, GENERATION)

    assert analysis.analysis_state == "not_planned"


def test_stale_planner_identity_requires_rescan_without_source_access() -> None:
    stale = _target("front_preview")
    stale = PreparationTargetRecord(
        **{**stale.__dict__, "planner_identity": "c" * 64}
    )
    current = {"front_preview": CurrentOutputRecord(stale)}

    analysis = _service()._analysis_for_group(7, current, GENERATION)

    front = analysis.outputs[0]
    assert front.state == "unavailable"
    assert front.diagnostic is not None
    assert front.diagnostic.code == "catalog_rescan_required"


def test_low_space_admission_returns_unavailable_without_scheduling_work() -> None:
    class CatalogRepository:
        pass

    class Repository:
        def __init__(self) -> None:
            self.diagnostic = None

        def get_current_outputs(self, recording_ids):
            del recording_ids
            return ()

        def prepare_recording(
            self, recording_id, planner_identities, *, output_kinds=PROCESSING_KINDS,
            invalid_artifact_ids=None,
            admission_diagnostic=None,
        ):
            del planner_identities, invalid_artifact_ids
            self.diagnostic = admission_diagnostic
            return PreparationSchedule(
                recording_id,
                True,
                tuple(
                    ScheduledOutput(
                        kind,
                        "unavailable",
                        "unavailable",
                        _target(kind),
                        diagnostic_code=admission_diagnostic.code,
                        diagnostic_message=admission_diagnostic.message,
                    )
                    for kind in output_kinds
                ),
            )

    repository = Repository()
    service = PreparationService(
        CatalogRepository(),  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakePlanner(),  # type: ignore[arg-type]
        {kind: ValidStore() for kind in PROCESSING_KINDS},  # type: ignore[dict-item]
        admission_check=lambda: SafeDiagnostic(
            "derived_space_low",
            "New preparation is paused because derived storage is low on space.",
        ),
    )

    result = service.prepare_selected((7,))

    assert repository.diagnostic is not None
    assert repository.diagnostic.code == "derived_space_low"
    assert not result.has_active_work
    assert [output.outcome for output in result.recordings[0].outputs] == [
        "unavailable",
        "unavailable",
        "unavailable",
    ]
    assert all(
        output.diagnostic is not None
        and output.diagnostic.code == "derived_space_low"
        for output in result.recordings[0].outputs
    )


def test_selective_preparation_forwards_only_chosen_kinds() -> None:
    class CatalogRepository:
        def get_catalog_state(self):
            return type("State", (), {"successful_generation": GENERATION})()

    class Repository:
        def __init__(self) -> None:
            self.selected: tuple[str, ...] | None = None

        def get_current_outputs(self, recording_ids):
            del recording_ids
            return ()

        def prepare_recording(
            self,
            recording_id,
            planner_identities,
            *,
            output_kinds,
            invalid_artifact_ids=None,
            admission_diagnostic=None,
        ):
            del planner_identities, invalid_artifact_ids, admission_diagnostic
            self.selected = output_kinds
            return PreparationSchedule(
                recording_id,
                True,
                (
                    ScheduledOutput(
                        "imu_series",
                        "queued",
                        "queued",
                        _target("imu_series"),
                        job=_job("imu_series", "queued"),
                    ),
                ),
            )

    repository = Repository()
    service = PreparationService(
        CatalogRepository(),  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        FakePlanner(),  # type: ignore[arg-type]
        {kind: ValidStore() for kind in PROCESSING_KINDS},  # type: ignore[dict-item]
    )

    result = service.prepare_selected((7,), ("imu_series",))

    assert repository.selected == ("imu_series",)
    assert [item.kind for item in result.recordings[0].outputs] == ["imu_series"]
    assert result.recordings[0].analysis_state == "queued"


def test_one_scheduling_failure_keeps_sibling_output_results() -> None:
    class Repository:
        def get_current_outputs(self, recording_ids):
            del recording_ids
            return ()

        def prepare_recording(self, recording_id, planner_identities, **kwargs):
            del planner_identities, kwargs
            return PreparationSchedule(
                recording_id,
                True,
                (
                    ScheduledOutput(
                        "front_preview",
                        "queued",
                        "queued",
                        _target("front_preview"),
                        job=_job("front_preview", "queued"),
                    ),
                    ScheduledOutput(
                        "topdown_preview",
                        "request_failed",
                        "unavailable",
                        _target("topdown_preview"),
                        diagnostic_code="preparation_schedule_failed",
                        diagnostic_message="Top-down scheduling failed.",
                    ),
                    ScheduledOutput(
                        "imu_series",
                        "ready_reused",
                        "ready",
                        _target("imu_series"),
                        artifact=_artifact("imu_series"),
                    ),
                ),
            )

    service = PreparationService(
        object(),  # type: ignore[arg-type]
        Repository(),  # type: ignore[arg-type]
        FakePlanner(),  # type: ignore[arg-type]
        {kind: ValidStore() for kind in PROCESSING_KINDS},  # type: ignore[dict-item]
    )

    result = service.prepare_selected((7,))

    prepared = result.recordings[0]
    assert prepared.outcome == "accepted"
    assert prepared.analysis_state == "queued"
    assert [item.outcome for item in prepared.outputs] == [
        "queued",
        "request_failed",
        "ready_reused",
    ]
    assert result.has_active_work


def test_selective_not_found_response_contains_only_requested_kinds() -> None:
    class CatalogRepository:
        def get_catalog_state(self):
            return type("State", (), {"successful_generation": GENERATION})()

    class Repository:
        def get_current_outputs(self, recording_ids):
            del recording_ids
            return ()

        def prepare_recording(self, recording_id, planner_identities, **kwargs):
            del planner_identities, kwargs
            return PreparationSchedule(recording_id, False, ())

    service = PreparationService(
        CatalogRepository(),  # type: ignore[arg-type]
        Repository(),  # type: ignore[arg-type]
        FakePlanner(),  # type: ignore[arg-type]
        {kind: ValidStore() for kind in PROCESSING_KINDS},  # type: ignore[dict-item]
    )

    result = service.prepare_selected((404,), ("imu_series",))

    assert result.recordings[0].outcome == "not_found"
    assert [item.kind for item in result.recordings[0].outputs] == ["imu_series"]
