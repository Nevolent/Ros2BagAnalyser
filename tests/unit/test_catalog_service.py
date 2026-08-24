from __future__ import annotations

from types import SimpleNamespace

import pytest

from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.catalog.types import RootScanError, SafeDiagnostic, ScanSnapshot


class RecordingScanner:
    def __init__(self) -> None:
        self.scan_calls = 0

    def scan(self) -> ScanSnapshot:
        self.scan_calls += 1
        return ScanSnapshot(recordings=(), duration_ms=1)


class RecordingRepository:
    def __init__(self) -> None:
        self.apply_calls = 0

    def apply_snapshot(self, snapshot: ScanSnapshot) -> SimpleNamespace:
        self.apply_calls += 1
        return SimpleNamespace(generation=1)

    def get_catalog_state(self) -> SimpleNamespace:
        return SimpleNamespace(successful_completed_at=None)


def test_rescan_rejects_source_that_is_unavailable_before_scan() -> None:
    scanner = RecordingScanner()
    repository = RecordingRepository()
    service = CatalogService(
        scanner,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        source_admission_check=lambda: SafeDiagnostic(
            "source_mount_unavailable",
            "The trusted read-only source mount is unavailable.",
        ),
    )

    with pytest.raises(RootScanError, match="read-only source mount"):
        service.rescan()

    assert scanner.scan_calls == 0
    assert repository.apply_calls == 0


def test_rescan_does_not_commit_if_source_disappears_during_scan() -> None:
    scanner = RecordingScanner()
    repository = RecordingRepository()
    checks = iter(
        (
            None,
            SafeDiagnostic(
                "source_mount_unavailable",
                "The trusted read-only source mount is unavailable.",
            ),
        )
    )
    service = CatalogService(
        scanner,  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
        source_admission_check=lambda: next(checks),
    )

    with pytest.raises(RootScanError, match="read-only source mount"):
        service.rescan()

    assert scanner.scan_calls == 1
    assert repository.apply_calls == 0
