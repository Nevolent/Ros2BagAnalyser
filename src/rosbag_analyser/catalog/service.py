from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import threading

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
    generation: int = 0
    completed_at: datetime | None = None


class CatalogService:
    def __init__(
        self,
        scanner: CatalogScanner,
        repository: CatalogRepository,
        *,
        source_admission_check: Callable[[], SafeDiagnostic | None] | None = None,
    ) -> None:
        self.scanner = scanner
        self.repository = repository
        self.source_admission_check = source_admission_check
        self._rescan_lock = threading.Lock()

    def rescan(self) -> RescanResult:
        if not self._rescan_lock.acquire(blocking=False):
            from .types import RootScanError

            raise RootScanError(
                "catalog_scan_in_progress",
                "A catalog rescan is already in progress.",
            )
        try:
            self._require_source_admission()
            snapshot = self.scanner.scan()
            self._require_source_admission()
            summary = self.repository.apply_snapshot(snapshot)
            state = self.repository.get_catalog_state()
        finally:
            self._rescan_lock.release()
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
            generation=summary.generation,
            completed_at=state.successful_completed_at,
        )

    def _require_source_admission(self) -> None:
        if self.source_admission_check is None:
            return
        diagnostic = self.source_admission_check()
        if diagnostic is not None:
            from .types import RootScanError

            raise RootScanError(diagnostic.code, diagnostic.message)

    def list_recordings(self) -> tuple[CatalogRecording, ...]:
        return self.repository.list_recordings(include_missing=False)

    def get_recording(self, recording_id: int) -> CatalogRecordingDetail | None:
        return self.repository.get_recording(recording_id)
