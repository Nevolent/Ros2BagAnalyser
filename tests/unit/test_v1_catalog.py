from __future__ import annotations

from datetime import datetime, timezone

from rosbag_analyser.persistence.catalog_repository import (
    CatalogRecording,
    CatalogRecordingDetail,
    CatalogState,
)
from rosbag_analyser.preparation import OutputFact, RecordingAnalysis
from rosbag_analyser.v1_catalog import V1CatalogService


def _recording(recording_id: int, path: str, health: str = "readable") -> CatalogRecording:
    return CatalogRecording(
        id=recording_id,
        archive_relative_path=path,
        display_name=path.rsplit("/", 1)[-1],
        start_time_ns=recording_id,
        duration_ns=10,
        total_source_size_bytes=20,
        storage_format="sqlite3",
        metadata_version=5,
        message_count=1,
        topic_count=1,
        ros_health=health,
        diagnostic=None,
        source_present=True,
        last_seen_generation=7,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.state_calls = 0
        self.list_limits: list[int] = []
        self.detail_calls: list[int] = []
        self.recordings = (
            _recording(1, "alpha/run-one"),
            _recording(2, "alpha/beta/run-two", "unsupported"),
            _recording(3, "root-run"),
        )

    def get_catalog_state(self) -> CatalogState:
        self.state_calls += 1
        return CatalogState(
            7,
            datetime(2026, 8, 4, tzinfo=timezone.utc),
            12,
            3,
            2,
            0,
            0,
            1,
            0,
        )

    def list_recordings(self, limit: int, *, include_missing: bool = False):
        self.list_limits.append(limit)
        assert include_missing is False
        return self.recordings[:limit]

    def get_recording(self, recording_id: int):
        self.detail_calls.append(recording_id)
        match = next((item for item in self.recordings if item.id == recording_id), None)
        return None if match is None else CatalogRecordingDetail(match, ())


class FakePreparation:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[int, ...], int | None]] = []

    def states_for_recordings(self, recording_ids, *, generation=None):
        self.calls.append((recording_ids, generation))
        state_by_id = {1: "ready", 2: "failed", 3: "not_planned"}
        return tuple(
            RecordingAnalysis(
                recording_id,
                state_by_id[recording_id],
                (
                    OutputFact("front_preview", "not_requested"),
                    OutputFact("topdown_preview", "not_requested"),
                    OutputFact("imu_series", "not_requested"),
                ),
            )
            for recording_id in recording_ids
        )


def test_saved_catalog_uses_one_bounded_list_and_one_bulk_analysis_call() -> None:
    repository = FakeRepository()
    preparation = FakePreparation()
    service = V1CatalogService(repository, preparation, max_recordings=5000)  # type: ignore[arg-type]

    view = service.get_catalog()

    assert repository.state_calls == 1
    assert repository.list_limits == [5000]
    assert preparation.calls == [((1, 2, 3), 7)]
    assert view.summary == {
        "recordings": 3,
        "ready": 1,
        "processing": 0,
        "queued": 0,
        "failed": 1,
        "damaged": 1,
    }
    assert [item.folder_path for item in view.recordings] == [
        "alpha",
        "alpha/beta",
        "",
    ]
    assert [item.presentation_health for item in view.recordings] == [
        "readable",
        "damaged",
        "readable",
    ]
    assert [item.path for item in view.folders] == ["alpha", "alpha/beta"]
    assert view.folders[0].direct_recording_count == 1
    assert view.folders[0].descendant_recording_count == 2
    assert view.folders[1].parent_path == "alpha"


def test_detail_uses_saved_row_and_one_bulk_output_lookup() -> None:
    repository = FakeRepository()
    preparation = FakePreparation()
    service = V1CatalogService(repository, preparation, max_recordings=10)  # type: ignore[arg-type]

    detail = service.get_recording(2)

    assert detail is not None
    assert repository.detail_calls == [2]
    assert repository.state_calls == 1
    assert preparation.calls == [((2,), 7)]
    assert detail.folder_path == "alpha/beta"
    assert detail.presentation_health == "damaged"
