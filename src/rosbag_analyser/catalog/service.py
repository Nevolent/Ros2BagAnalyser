from __future__ import annotations

from dataclasses import dataclass

from rosbag_analyser.persistence.catalog_repository import (
    CatalogRecording,
    CatalogRecordingDetail,
    CatalogRepository,
)

from .scanner import CatalogScanner
from .types import SafeDiagnostic


@dataclass(frozen=True)
class RescanDiagnostic:
    recording_name: str
    diagnostic: SafeDiagnostic


@dataclass(frozen=True)
class RescanResult:
    recording_count: int
    readable_count: int
    damaged_count: int
    missing_count: int
    unsupported_count: int
    uninspectable_count: int
    duration_ms: int
    diagnostics: tuple[RescanDiagnostic, ...]


class CatalogService:
    def __init__(self, scanner: CatalogScanner, repository: CatalogRepository) -> None:
        self.scanner = scanner
        self.repository = repository

    def rescan(self) -> RescanResult:
        snapshot = self.scanner.scan()
        self.repository.apply_snapshot(snapshot)
        health_values = [recording.ros_health.value for recording in snapshot.recordings]
        diagnostics = tuple(
            RescanDiagnostic(recording.display_name, recording.diagnostic)
            for recording in snapshot.recordings
            if recording.diagnostic is not None
        )
        return RescanResult(
            recording_count=len(snapshot.recordings),
            readable_count=health_values.count("readable"),
            damaged_count=health_values.count("damaged"),
            missing_count=health_values.count("missing"),
            unsupported_count=health_values.count("unsupported"),
            uninspectable_count=health_values.count("uninspectable"),
            duration_ms=snapshot.duration_ms,
            diagnostics=diagnostics,
        )

    def list_recordings(self) -> tuple[CatalogRecording, ...]:
        return self.repository.list_recordings()

    def get_recording(self, recording_id: int) -> CatalogRecordingDetail | None:
        return self.repository.get_recording(recording_id)
