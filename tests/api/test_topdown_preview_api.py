from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from pathlib import Path

import httpx
import pytest

from rosbag_analyser.api.app import create_app
from rosbag_analyser.artifact_store import OpenedMedia
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.processing_repository import ArtifactRecord
from rosbag_analyser.topdown_preview import TopdownPreviewDisplay


pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class UnusedCatalogService:
    pass


class FakeTopdownService:
    def __init__(
        self,
        display: TopdownPreviewDisplay,
        *,
        requested: TopdownPreviewDisplay | None = None,
        media_path: Path | None = None,
    ) -> None:
        self.display = display
        self.requested = requested or display
        self.media_path = media_path
        self.request_count = 0

    def get_state(self, recording_id: int) -> TopdownPreviewDisplay:
        del recording_id
        return self.display

    def request(self, recording_id: int) -> TopdownPreviewDisplay:
        del recording_id
        self.request_count += 1
        return self.requested

    def resolve_media(self, recording_id: int, artifact_id: int):
        del recording_id
        if (
            self.media_path is None
            or self.display.artifact is None
            or self.display.artifact.id != artifact_id
        ):
            return None
        descriptor = os.open(self.media_path, os.O_RDONLY)
        return OpenedMedia(descriptor, os.fstat(descriptor)), self.display.artifact


def _artifact() -> ArtifactRecord:
    return ArtifactRecord(
        id=4,
        recording_id=7,
        kind="topdown_preview",
        cache_identity="b" * 64,
        output_relative_path="derived/topdown.mp4",
        mime_type="video/mp4",
        size_bytes=10,
        coverage_start_ns=1_500_000_000,
        coverage_end_ns=3_000_000_000,
        manifest={
            "artifact_kind": "topdown_preview",
            "cache_identity": "b" * 64,
            "warnings": [
                "coverage_starts_after_recording",
                "coverage_ends_after_recording",
            ],
        },
        created_at=datetime.now(timezone.utc),
    )


@asynccontextmanager
async def client_for(service: FakeTopdownService):
    app = create_app(
        UnusedCatalogService(),  # type: ignore[arg-type]
        None,
        service,  # type: ignore[arg-type]
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_request_returns_immediately_with_poll_contract() -> None:
    service = FakeTopdownService(
        TopdownPreviewDisplay(True, "not_requested", 4_000_000_000),
        requested=TopdownPreviewDisplay(True, "queued", 4_000_000_000),
    )

    async with client_for(service) as client:
        response = await client.post("/api/recordings/7/topdown-preview")

    assert response.status_code == 202
    assert response.json() == {
        "state": "queued",
        "global_duration_ns": "4000000000",
        "diagnostic": None,
        "artifact": None,
        "poll_after_ms": 1000,
    }
    assert service.request_count == 1


async def test_unavailable_response_is_safe_and_does_not_poll() -> None:
    service = FakeTopdownService(
        TopdownPreviewDisplay(
            True,
            "unavailable",
            4_000_000_000,
            diagnostic=SafeDiagnostic(
                "bag_origin_unavailable",
                "A trustworthy ROS bag origin is unavailable for synchronization.",
            ),
        )
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/topdown-preview")

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert response.json()["poll_after_ms"] is None
    assert response.json()["diagnostic"]["code"] == "bag_origin_unavailable"


async def test_ready_response_uses_csv_provenance_without_paths() -> None:
    service = FakeTopdownService(
        TopdownPreviewDisplay(True, "ready", 4_000_000_000, artifact=_artifact())
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/topdown-preview")

    assert response.status_code == 200
    assert response.json()["artifact"] == {
        "mime_type": "video/mp4",
        "size_bytes": "10",
        "coverage_start_ns": "1500000000",
        "coverage_end_ns": "3000000000",
        "timestamp_provenance": "csv_unix_timestamp",
        "bounds": "measured",
        "warnings": [
            {
                "code": "coverage_starts_after_recording",
                "message": "Top-down coverage starts after the ROS recording begins.",
            },
            {
                "code": "coverage_ends_after_recording",
                "message": "Top-down coverage ends after the ROS recording.",
            },
        ],
        "media_url": "/api/recordings/7/topdown-preview/media/4",
    }
    assert "output_relative_path" not in response.text
    assert "cache_identity" not in response.text


async def test_media_endpoint_reuses_browser_range_delivery(tmp_path: Path) -> None:
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"0123456789")
    service = FakeTopdownService(
        TopdownPreviewDisplay(True, "ready", 4_000_000_000, artifact=_artifact()),
        media_path=media,
    )

    async with client_for(service) as client:
        full = await client.get("/api/recordings/7/topdown-preview/media/4")
        ranged = await client.get(
            "/api/recordings/7/topdown-preview/media/4",
            headers={"Range": "bytes=2-5", "If-Range": full.headers["etag"]},
        )
        head = await client.head("/api/recordings/7/topdown-preview/media/4")
        stale = await client.get("/api/recordings/7/topdown-preview/media/3")

    assert full.status_code == 200
    assert ranged.status_code == 206
    assert ranged.content == b"2345"
    assert ranged.headers["content-range"] == "bytes 2-5/10"
    assert head.status_code == 200
    assert head.content == b""
    assert stale.status_code == 404
    assert stale.json()["detail"]["code"] == "topdown_preview_not_ready"


async def test_missing_recording_is_sanitized() -> None:
    service = FakeTopdownService(TopdownPreviewDisplay(False, "not_found", None))

    async with client_for(service) as client:
        response = await client.get("/api/recordings/99/topdown-preview")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "recording_not_found"
