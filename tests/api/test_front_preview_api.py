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
from rosbag_analyser.front_preview import PreviewDisplay
from rosbag_analyser.persistence.processing_repository import ArtifactRecord


pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class UnusedCatalogService:
    pass


def _artifact() -> ArtifactRecord:
    return ArtifactRecord(
        id=3,
        recording_id=7,
        kind="front_preview",
        cache_identity="a" * 64,
        output_relative_path="derived/preview.mp4",
        mime_type="video/mp4",
        size_bytes=10,
        coverage_start_ns=100_000_000,
        coverage_end_ns=2_100_000_000,
        manifest={"cache_identity": "a" * 64},
        created_at=datetime.now(timezone.utc),
    )


class FakePreviewService:
    def __init__(
        self,
        display: PreviewDisplay,
        *,
        requested: PreviewDisplay | None = None,
        media_path: Path | None = None,
    ) -> None:
        self.display = display
        self.requested = requested or display
        self.media_path = media_path
        self.request_count = 0

    def get_state(self, recording_id: int) -> PreviewDisplay:
        del recording_id
        return self.display

    def request(self, recording_id: int) -> PreviewDisplay:
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


@asynccontextmanager
async def client_for(preview_service: FakePreviewService):
    app = create_app(
        UnusedCatalogService(),  # type: ignore[arg-type]
        preview_service,  # type: ignore[arg-type]
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_request_returns_immediately_with_poll_contract() -> None:
    service = FakePreviewService(
        PreviewDisplay(True, "not_requested", 2_500_000_000),
        requested=PreviewDisplay(True, "queued", 2_500_000_000),
    )

    async with client_for(service) as client:
        response = await client.post("/api/recordings/7/front-preview")

    assert response.status_code == 202
    assert response.json() == {
        "state": "queued",
        "global_duration_ns": "2500000000",
        "diagnostic": None,
        "artifact": None,
        "poll_after_ms": 1000,
    }
    assert service.request_count == 1


async def test_unavailable_response_has_safe_reason_and_no_poll() -> None:
    service = FakePreviewService(
        PreviewDisplay(
            True,
            "unavailable",
            2_500_000_000,
            diagnostic=SafeDiagnostic(
                "ros_source_unavailable",
                "The ROS recording is not readable enough to generate a preview.",
            ),
        )
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/front-preview")

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert response.json()["diagnostic"]["code"] == "ros_source_unavailable"
    assert response.json()["poll_after_ms"] is None


async def test_ready_metadata_uses_decimal_nanoseconds_and_no_source_path() -> None:
    artifact = _artifact()
    service = FakePreviewService(
        PreviewDisplay(True, "ready", 2_500_000_000, artifact=artifact)
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/front-preview")

    assert response.status_code == 200
    assert response.json()["artifact"] == {
        "mime_type": "video/mp4",
        "size_bytes": "10",
        "coverage_start_ns": "100000000",
        "coverage_end_ns": "2100000000",
        "timestamp_provenance": "ros_record_timestamp",
        "bounds": "measured",
        "media_url": "/api/recordings/7/front-preview/media/3",
    }
    assert "output_relative_path" not in response.text
    assert "cache_identity" not in response.text


async def test_polling_exposes_processing_failure_and_ready_transitions() -> None:
    service = FakePreviewService(
        PreviewDisplay(True, "processing", 2_500_000_000)
    )

    async with client_for(service) as client:
        processing = await client.get("/api/recordings/7/front-preview")
        service.display = PreviewDisplay(
            True,
            "failed",
            2_500_000_000,
            diagnostic=SafeDiagnostic(
                "preview_processing_failed", "Preview generation failed."
            ),
        )
        failed = await client.get("/api/recordings/7/front-preview")
        service.display = PreviewDisplay(
            True, "ready", 2_500_000_000, artifact=_artifact()
        )
        ready = await client.get("/api/recordings/7/front-preview")

    assert processing.json()["state"] == "processing"
    assert processing.json()["poll_after_ms"] == 1000
    assert failed.json()["state"] == "failed"
    assert failed.json()["poll_after_ms"] is None
    assert failed.json()["diagnostic"]["code"] == "preview_processing_failed"
    assert ready.json()["state"] == "ready"
    assert ready.json()["poll_after_ms"] is None
    assert ready.json()["artifact"]["media_url"].endswith("/media/3")


async def test_media_endpoint_supports_browser_byte_ranges(tmp_path: Path) -> None:
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"0123456789")
    artifact = _artifact()
    service = FakePreviewService(
        PreviewDisplay(True, "ready", 2_500_000_000, artifact=artifact),
        media_path=media,
    )

    async with client_for(service) as client:
        response = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=2-5"},
        )

    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["cache-control"] == "private, no-cache, must-revalidate"

    async with client_for(service) as client:
        full_response = await client.get(
            "/api/recordings/7/front-preview/media/3"
        )
        unsatisfiable = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=20-30"},
        )
    assert full_response.status_code == 200
    assert full_response.content == b"0123456789"
    assert full_response.headers["content-length"] == "10"
    assert unsatisfiable.status_code == 416
    assert unsatisfiable.headers["content-range"] == "bytes */10"


async def test_media_endpoint_honors_identity_head_and_if_range(
    tmp_path: Path,
) -> None:
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"0123456789")
    artifact = _artifact()
    service = FakePreviewService(
        PreviewDisplay(True, "ready", 2_500_000_000, artifact=artifact),
        media_path=media,
    )

    async with client_for(service) as client:
        full = await client.get(
            "/api/recordings/7/front-preview/media/3"
        )
        head = await client.head(
            "/api/recordings/7/front-preview/media/3"
        )
        ranged_head = await client.head(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=2-5"},
        )
        matching = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=2-5", "If-Range": full.headers["etag"]},
        )
        stale = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=2-5", "If-Range": '"stale"'},
        )
        matching_date = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={
                "Range": "bytes=2-5",
                "If-Range": full.headers["last-modified"],
            },
        )
        future_date = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={
                "Range": "bytes=2-5",
                "If-Range": "Wed, 21 Oct 2099 07:28:00 GMT",
            },
        )
        old_identity = await client.get(
            "/api/recordings/7/front-preview/media/2"
        )

    assert head.status_code == 200
    assert head.content == b""
    assert head.headers["content-length"] == "10"
    assert ranged_head.status_code == 200
    assert ranged_head.content == b""
    assert ranged_head.headers["content-length"] == "10"
    assert "content-range" not in ranged_head.headers
    assert matching.status_code == 206
    assert matching.content == b"2345"
    assert stale.status_code == 200
    assert stale.content == b"0123456789"
    assert matching_date.status_code == 206
    assert matching_date.content == b"2345"
    assert future_date.status_code == 200
    assert future_date.content == b"0123456789"
    assert old_identity.status_code == 404


async def test_media_endpoint_ignores_unknown_units_and_rejects_bad_byte_grammar(
    tmp_path: Path,
) -> None:
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"0123456789")
    artifact = _artifact()
    service = FakePreviewService(
        PreviewDisplay(True, "ready", 2_500_000_000, artifact=artifact),
        media_path=media,
    )

    async with client_for(service) as client:
        unknown_unit = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "items=2-5"},
        )
        malformed_bytes = await client.get(
            "/api/recordings/7/front-preview/media/3",
            headers={"Range": "bytes=+2-5"},
        )

    assert unknown_unit.status_code == 200
    assert unknown_unit.content == b"0123456789"
    assert malformed_bytes.status_code == 416


async def test_missing_recording_and_not_ready_media_are_sanitized() -> None:
    missing = FakePreviewService(PreviewDisplay(False, "not_found", None))
    not_ready = FakePreviewService(PreviewDisplay(True, "queued", 1_000))

    async with client_for(missing) as client:
        missing_response = await client.get("/api/recordings/99/front-preview")
    async with client_for(not_ready) as client:
        media_response = await client.get(
            "/api/recordings/7/front-preview/media/3"
        )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"]["code"] == "recording_not_found"
    assert media_response.status_code == 404
    assert media_response.json()["detail"]["code"] == "front_preview_not_ready"
