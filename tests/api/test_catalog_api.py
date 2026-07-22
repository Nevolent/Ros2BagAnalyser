from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import threading
import time

import httpx
import psycopg
import pytest

from rosbag_analyser.api.app import create_app
from rosbag_analyser.catalog.service import RescanDiagnostic, RescanResult
from rosbag_analyser.catalog.types import RootScanError, SafeDiagnostic
from rosbag_analyser.persistence.catalog_repository import (
    CatalogComponent,
    CatalogRecording,
    CatalogRecordingDetail,
)


def _recording() -> CatalogRecording:
    return CatalogRecording(
        id=7,
        display_name="healthy-run",
        start_time_ns=1_700_000_000_000_000_000,
        duration_ns=2_500_000_000,
        total_source_size_bytes=12_345,
        storage_format="sqlite3",
        metadata_version=5,
        message_count=42,
        topic_count=1,
        ros_health="readable",
        diagnostic=None,
    )


class FakeService:
    def rescan(self) -> RescanResult:
        diagnostic = SafeDiagnostic("sqlite_size_mismatch", "Database is truncated.")
        return RescanResult(
            recording_count=2,
            readable_count=1,
            damaged_count=1,
            missing_count=0,
            unsupported_count=0,
            uninspectable_count=0,
            duration_ms=12,
            diagnostics=(RescanDiagnostic("damaged-run", diagnostic),),
        )

    def list_recordings(self):
        return (_recording(),)

    def get_recording(self, recording_id: int):
        if recording_id != 7:
            return None
        return CatalogRecordingDetail(
            recording=_recording(),
            components=(
                CatalogComponent(
                    role="metadata",
                    condition="readable",
                    display_name="metadata.yaml",
                    size_bytes=500,
                    mtime_ns=1_700_000_000_000_000_000,
                    diagnostic=None,
                ),
            ),
        )


pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def client_for(service):
    app = create_app(service)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_list_detail_and_static_browser_contract() -> None:
    async with client_for(FakeService()) as client:
        listing = await client.get("/api/recordings")
        detail = await client.get("/api/recordings/7")
        page = await client.get("/")
        detail_page = await client.get("/recordings/7")
        script = await client.get("/app.js")
        stylesheet = await client.get("/styles.css")

    assert listing.status_code == 200
    assert listing.json()["items"][0]["start_time_ns"] == "1700000000000000000"
    assert "archive_relative_path" not in listing.text
    assert "source_revision" not in listing.text
    assert detail.status_code == 200
    assert detail.json()["components"][0]["file_name"] == "metadata.yaml"
    assert "relative_path" not in detail.text
    assert page.status_code == 200
    assert "Recording archive" in page.text
    assert detail_page.status_code == 200
    assert script.status_code == 200
    assert "wrapper.tabIndex = 0" in script.text
    assert "current table could not be refreshed" in script.text
    assert 'renderRecordingShell("Recording details")' in script.text
    assert "document.title" in script.text
    assert "PREVIEW_RETRY_DELAY_MS" in script.text
    assert 'video.addEventListener("error", () => {' in script.text
    assert "showMediaFailure(kind);" in script.text
    assert "VIDEO_DRIFT_TOLERANCE_SECONDS" in script.text
    assert 'paneId: "front-preview-pane"' in script.text
    assert 'paneId: "topdown-preview-pane"' in script.text
    assert script.text.count('node("button", "Play")') == 1
    assert "Object.values(controller.players).forEach" in script.text
    assert "forceSeek" in script.text
    assert "playPending" in script.text
    assert "player.playAttempt !== playAttempt" in script.text
    assert "reviewController !== controller" in script.text
    end_tick = script.text.index(
        "const reachedEnd = next >= controller.durationSeconds;"
    )
    stop_clock = script.text.index("clock.playing = false;", end_tick)
    synchronize_media = script.text.index("applyGlobalTime(next);", end_tick)
    assert stop_clock < synchronize_media
    assert stylesheet.status_code == 200
    assert ".table-wrapper:focus-visible" in stylesheet.text
    assert ".preview-player video[hidden]" in stylesheet.text
    assert ".camera-grid" in stylesheet.text
    assert listing.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in listing.headers["content-security-policy"]
    assert "media-src 'self'" in listing.headers["content-security-policy"]


async def test_rescan_returns_safe_counts_and_diagnostics() -> None:
    async with client_for(FakeService()) as client:
        response = await client.post("/api/catalog/rescan")

    assert response.status_code == 200
    assert response.json()["recording_count"] == 2
    assert response.json()["damaged_count"] == 1
    assert response.json()["diagnostics"][0]["diagnostic"]["code"] == "sqlite_size_mismatch"


async def test_unknown_recording_has_sanitized_404() -> None:
    async with client_for(FakeService()) as client:
        response = await client.get("/api/recordings/99")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "recording_not_found"


async def test_non_positive_recording_ids_are_rejected_consistently() -> None:
    async with client_for(FakeService()) as client:
        negative_page = await client.get("/recordings/-1")
        negative_api = await client.get("/api/recordings/-1")
        zero_page = await client.get("/recordings/0")
        zero_api = await client.get("/api/recordings/0")

    assert negative_page.status_code == 404
    assert negative_api.status_code == 404
    assert zero_page.status_code == 422
    assert zero_api.status_code == 422


async def test_noncanonical_positive_recording_ids_do_not_match_routes() -> None:
    paths = (
        "/recordings/+7",
        "/api/recordings/+7",
        "/recordings/7.0",
        "/api/recordings/7.0",
        "/recordings/%207%20",
        "/api/recordings/%207%20",
    )
    async with client_for(FakeService()) as client:
        responses = [await client.get(path) for path in paths]

    assert all(response.status_code == 404 for response in responses)


class FailingScanService(FakeService):
    def rescan(self) -> RescanResult:
        try:
            raise OSError("archive mount detail")
        except OSError as cause:
            raise RootScanError(
                "archive_enumeration_failed", "Archive scan unavailable."
            ) from cause


async def test_root_scan_failure_is_sanitized_logged_and_list_remains_available(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="rosbag_analyser.api.catalog_routes"):
        async with client_for(FailingScanService()) as client:
            failed = await client.post("/api/catalog/rescan")
            listing = await client.get("/api/recordings")

    assert failed.status_code == 503
    assert failed.json()["detail"] == {
        "code": "archive_enumeration_failed",
        "message": "Archive scan unavailable.",
    }
    assert "archive mount detail" not in failed.text
    assert "archive mount detail" in caplog.text
    assert listing.status_code == 200


class UnavailableDatabaseService(FakeService):
    def list_recordings(self):
        raise psycopg.OperationalError("server connection detail")


class InvalidCatalogOperationService(FakeService):
    def list_recordings(self):
        raise psycopg.ProgrammingError("catalog query detail")


async def test_database_unavailability_is_sanitized_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="rosbag_analyser.api.catalog_routes"):
        async with client_for(UnavailableDatabaseService()) as client:
            response = await client.get("/api/recordings")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "catalog_database_unavailable"
    assert "server connection detail" not in response.text
    assert "server connection detail" in caplog.text


async def test_catalog_programming_error_is_internal_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR, logger="rosbag_analyser.api.catalog_routes"):
        async with client_for(InvalidCatalogOperationService()) as client:
            response = await client.get("/api/recordings")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "catalog_operation_failed"
    assert "catalog query detail" not in response.text
    assert "catalog query detail" in caplog.text


class BlockingScanService(FakeService):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def rescan(self) -> RescanResult:
        self.started.set()
        self.release.wait(timeout=2)
        return super().rescan()


async def test_rescan_does_not_block_concurrent_catalog_read() -> None:
    service = BlockingScanService()
    release_timer = threading.Timer(1, service.release.set)
    release_timer.start()
    started_at = time.monotonic()
    try:
        async with client_for(service) as client:
            rescan_task = asyncio.create_task(client.post("/api/catalog/rescan"))
            while not service.started.is_set():
                await asyncio.sleep(0.01)
            listing = await client.get("/api/recordings")
            elapsed = time.monotonic() - started_at
            service.release.set()
            rescan = await rescan_task
    finally:
        service.release.set()
        release_timer.cancel()

    assert listing.status_code == 200
    assert rescan.status_code == 200
    assert elapsed < 0.5


async def test_multiple_rescans_do_not_exhaust_catalog_read_capacity() -> None:
    service = BlockingScanService()
    rescan_tasks: list[asyncio.Task[httpx.Response]] = []
    try:
        async with client_for(service) as client:
            rescan_tasks = [
                asyncio.create_task(client.post("/api/catalog/rescan"))
                for _ in range(4)
            ]
            while not service.started.is_set():
                await asyncio.sleep(0.01)

            listing = await asyncio.wait_for(
                client.get("/api/recordings"),
                timeout=0.5,
            )
            service.release.set()
            rescans = await asyncio.gather(*rescan_tasks)
    finally:
        service.release.set()
        if rescan_tasks:
            await asyncio.gather(*rescan_tasks, return_exceptions=True)

    assert listing.status_code == 200
    assert all(response.status_code == 200 for response in rescans)
