from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Any

from rosbag_analyser.persistence.catalog_repository import (
    CatalogRecording,
    CatalogRecordingDetail,
    CatalogRepository,
)

from .scanner import CatalogScanner
from .types import RootScanError, SafeDiagnostic


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
        rescan_scheduler: Callable[[Any], None] | None = None,
    ) -> None:
        self.scanner = scanner
        self.repository = repository
        self.source_admission_check = source_admission_check
        self.rescan_scheduler = rescan_scheduler
        self._rescan_lock = threading.Lock()

    def discover_new(self) -> int:
        # Refreshes share the existing scan boundary; an active scan will
        # discover new sources itself. Never queue a backlog of refresh scans.
        if not self._rescan_lock.acquire(blocking=False):
            return 0
        try:
            with self.repository.source_scan(full=False) as connection:
                self._require_source_admission()
                known = self.repository.known_recording_paths()
                snapshot = self.scanner.scan(known_recordings=known)
                self._require_source_admission()
                if connection is not None:
                    connection.execute("SELECT 1")  # Confirm ownership before publication.
                return self.repository.apply_discovery(snapshot).recording_count
        except RootScanError as error:
            if error.diagnostic.code == "catalog_scan_in_progress":
                return 0
            raise
        finally:
            self._rescan_lock.release()

    def rescan(self) -> RescanResult:
        if not self._rescan_lock.acquire(blocking=False):
            raise RootScanError(
                "catalog_scan_in_progress",
                "A catalog rescan is already in progress.",
            )
        try:
            with self.repository.source_scan(full=True) as connection:
                self._require_source_admission()
                snapshot = self.scanner.scan(timing_cache=self.repository.load_timing_cache())
                self._require_source_admission()
                if connection is not None:
                    connection.execute("SELECT 1")
                summary = (
                    self.repository.apply_snapshot(snapshot)
                    if self.rescan_scheduler is None
                    else self.repository.apply_snapshot(
                        snapshot, schedule_outputs=self.rescan_scheduler
                    )
                )
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

    def rescan_running(self) -> bool:
        return self.repository.rescan_running()

    def _require_source_admission(self) -> None:
        if self.source_admission_check is None:
            return
        diagnostic = self.source_admission_check()
        if diagnostic is not None:
            raise RootScanError(diagnostic.code, diagnostic.message)

    def list_recordings(self) -> tuple[CatalogRecording, ...]:
        return self.repository.list_recordings(include_missing=False)

    def get_recording(self, recording_id: int) -> CatalogRecordingDetail | None:
        return self.repository.get_recording(recording_id)
