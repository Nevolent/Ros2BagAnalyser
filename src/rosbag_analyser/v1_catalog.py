from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from rosbag_analyser.persistence.catalog_repository import (
    CatalogRecording,
    CatalogRecordingDetail,
    CatalogRepository,
    CatalogState,
)
from rosbag_analyser.preparation import PreparationService, RecordingAnalysis


@dataclass(frozen=True)
class FolderNode:
    path: str
    parent_path: str
    name: str
    direct_recording_count: int
    descendant_recording_count: int


@dataclass(frozen=True)
class V1CatalogItem:
    recording: CatalogRecording
    folder_path: str
    presentation_health: str
    analysis: RecordingAnalysis


@dataclass(frozen=True)
class V1CatalogView:
    scan: CatalogState
    summary: dict[str, int]
    folders: tuple[FolderNode, ...]
    recordings: tuple[V1CatalogItem, ...]


@dataclass(frozen=True)
class V1RecordingDetail:
    detail: CatalogRecordingDetail
    folder_path: str
    presentation_health: str
    analysis: RecordingAnalysis


class V1CatalogService:
    def __init__(
        self,
        repository: CatalogRepository,
        preparation: PreparationService,
        *,
        max_recordings: int,
    ) -> None:
        if max_recordings <= 0:
            raise ValueError("The V1 catalog response bound must be positive.")
        self.repository = repository
        self.preparation = preparation
        self.max_recordings = max_recordings

    def get_catalog(self) -> V1CatalogView:
        scan = self.repository.get_catalog_state()
        recordings = self.repository.list_recordings(
            self.max_recordings,
            include_missing=False,
        )
        analyses = self.preparation.states_for_recordings(
            tuple(recording.id for recording in recordings),
            generation=scan.successful_generation,
        )
        by_id = {analysis.recording_id: analysis for analysis in analyses}
        items = tuple(
            V1CatalogItem(
                recording=recording,
                folder_path=_folder_path(recording.archive_relative_path),
                presentation_health=(
                    "readable" if recording.ros_health == "readable" else "damaged"
                ),
                analysis=by_id[recording.id],
            )
            for recording in recordings
        )
        summary = {
            "recordings": len(items),
            "ready": sum(item.analysis.analysis_state == "ready" for item in items),
            "processing": sum(
                item.analysis.analysis_state == "processing" for item in items
            ),
            "queued": sum(item.analysis.analysis_state == "queued" for item in items),
            "failed": sum(item.analysis.analysis_state == "failed" for item in items),
            "damaged": sum(item.presentation_health == "damaged" for item in items),
        }
        return V1CatalogView(
            scan=scan,
            summary=summary,
            folders=_folder_nodes(items),
            recordings=items,
        )

    def get_recording(self, recording_id: int) -> V1RecordingDetail | None:
        detail = self.repository.get_recording(recording_id)
        if detail is None:
            return None
        scan = self.repository.get_catalog_state()
        analysis = self.preparation.states_for_recordings(
            (recording_id,),
            generation=scan.successful_generation,
        )[0]
        recording = detail.recording
        return V1RecordingDetail(
            detail=detail,
            folder_path=_folder_path(recording.archive_relative_path),
            presentation_health=(
                "readable" if recording.ros_health == "readable" else "damaged"
            ),
            analysis=analysis,
        )


def _folder_path(recording_path: str) -> str:
    parent = PurePosixPath(recording_path).parent.as_posix()
    return "" if parent == "." else parent


def _folder_nodes(items: tuple[V1CatalogItem, ...]) -> tuple[FolderNode, ...]:
    direct: dict[str, int] = {}
    descendants: dict[str, int] = {}
    for item in items:
        folder = item.folder_path
        if not folder:
            continue
        direct[folder] = direct.get(folder, 0) + 1
        parts = PurePosixPath(folder).parts
        for index in range(1, len(parts) + 1):
            ancestor = PurePosixPath(*parts[:index]).as_posix()
            descendants[ancestor] = descendants.get(ancestor, 0) + 1
    return tuple(
        FolderNode(
            path=path,
            parent_path=_folder_path(path),
            name=PurePosixPath(path).name,
            direct_recording_count=direct.get(path, 0),
            descendant_recording_count=count,
        )
        for path, count in sorted(descendants.items())
    )


__all__ = ["V1CatalogService", "V1CatalogView", "V1RecordingDetail"]
