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
from rosbag_analyser.imu_series import ImuSeriesDisplay
from rosbag_analyser.persistence.processing_repository import ArtifactRecord


pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class UnusedCatalogService:
    pass


def _artifact() -> ArtifactRecord:
    return ArtifactRecord(
        id=6,
        recording_id=7,
        kind="imu_series",
        cache_identity="c" * 64,
        output_relative_path="derived/series.json",
        mime_type="application/json",
        size_bytes=48,
        coverage_start_ns=100_000_000,
        coverage_end_ns=2_100_000_000,
        manifest={
            "artifact_kind": "imu_series",
            "cache_identity": "c" * 64,
            "source": {
                "topic": "/sensors/imu",
                "component": "angular_velocity.z",
            },
            "samples": {
                "source": 201,
                "delivered": 201,
                "finite": 200,
                "non_finite": 1,
                "minimum": -1.5,
                "maximum": 2.25,
            },
            "reduction": {"method": "none"},
            "warnings": ["non_finite_values_present"],
        },
        created_at=datetime.now(timezone.utc),
    )


class FakeImuService:
    def __init__(
        self,
        display: ImuSeriesDisplay,
        *,
        requested: ImuSeriesDisplay | None = None,
        data_path: Path | None = None,
    ) -> None:
        self.display = display
        self.requested = requested or display
        self.data_path = data_path
        self.request_count = 0

    def get_state(self, recording_id: int) -> ImuSeriesDisplay:
        del recording_id
        return self.display

    def request(self, recording_id: int) -> ImuSeriesDisplay:
        del recording_id
        self.request_count += 1
        return self.requested

    def resolve_series(self, recording_id: int, artifact_id: int):
        del recording_id
        if (
            self.data_path is None
            or self.display.artifact is None
            or self.display.artifact.id != artifact_id
        ):
            return None
        descriptor = os.open(self.data_path, os.O_RDONLY)
        return OpenedMedia(descriptor, os.fstat(descriptor)), self.display.artifact


@asynccontextmanager
async def client_for(service: FakeImuService):
    app = create_app(
        UnusedCatalogService(),  # type: ignore[arg-type]
        None,
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
    service = FakeImuService(
        ImuSeriesDisplay(True, "not_requested", 2_500_000_000),
        requested=ImuSeriesDisplay(True, "queued", 2_500_000_000),
    )

    async with client_for(service) as client:
        response = await client.post("/api/recordings/7/imu-series")

    assert response.status_code == 202
    assert response.json() == {
        "state": "queued",
        "global_duration_ns": "2500000000",
        "diagnostic": None,
        "artifact": None,
        "poll_after_ms": 1000,
    }
    assert service.request_count == 1


async def test_unavailable_response_has_safe_reason() -> None:
    service = FakeImuService(
        ImuSeriesDisplay(
            True,
            "unavailable",
            2_500_000_000,
            diagnostic=SafeDiagnostic(
                "imu_topic_unavailable", "The configured IMU topic is unavailable."
            ),
        )
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/imu-series")

    assert response.status_code == 200
    assert response.json()["state"] == "unavailable"
    assert response.json()["diagnostic"]["code"] == "imu_topic_unavailable"
    assert response.json()["poll_after_ms"] is None


async def test_ready_metadata_is_exact_and_does_not_expose_paths() -> None:
    service = FakeImuService(
        ImuSeriesDisplay(True, "ready", 2_500_000_000, artifact=_artifact())
    )

    async with client_for(service) as client:
        response = await client.get("/api/recordings/7/imu-series")

    artifact = response.json()["artifact"]
    assert artifact == {
        "mime_type": "application/json",
        "size_bytes": "48",
        "coverage_start_ns": "100000000",
        "coverage_end_ns": "2100000000",
        "timestamp_provenance": "ros_record_timestamp",
        "bounds": "measured",
        "display_label": "IMU angular_velocity.z (rad/s)",
        "topic": "/sensors/imu",
        "component": "angular_velocity.z",
        "units": "rad/s",
        "source_sample_count": "201",
        "delivered_sample_count": "201",
        "finite_sample_count": "200",
        "non_finite_sample_count": "1",
        "minimum_value": -1.5,
        "maximum_value": 2.25,
        "reduction_method": "none",
        "warnings": [
            {
                "code": "non_finite_values_present",
                "message": (
                    "Some IMU values are non-finite and appear as explicit graph gaps."
                ),
            }
        ],
        "data_url": "/api/recordings/7/imu-series/data/6",
    }
    assert "output_relative_path" not in response.text
    assert "cache_identity" not in response.text


async def test_data_endpoint_supports_identity_head_and_ranges(tmp_path: Path) -> None:
    data = tmp_path / "series.json"
    data.write_bytes(b'{"schema_version":1,"samples":[["0",1.0]]}')
    artifact = _artifact()
    artifact = ArtifactRecord(**{**artifact.__dict__, "size_bytes": data.stat().st_size})
    service = FakeImuService(
        ImuSeriesDisplay(True, "ready", 2_500_000_000, artifact=artifact),
        data_path=data,
    )

    async with client_for(service) as client:
        full = await client.get("/api/recordings/7/imu-series/data/6")
        ranged = await client.get(
            "/api/recordings/7/imu-series/data/6",
            headers={"Range": "bytes=2-8", "If-Range": full.headers["etag"]},
        )
        head = await client.head("/api/recordings/7/imu-series/data/6")
        stale = await client.get("/api/recordings/7/imu-series/data/5")

    assert full.status_code == 200
    assert full.headers["content-type"] == "application/json"
    assert ranged.status_code == 206
    assert ranged.content == data.read_bytes()[2:9]
    assert head.status_code == 200
    assert head.content == b""
    assert stale.status_code == 404
    assert stale.json()["detail"]["code"] == "imu_series_not_ready"


async def test_missing_recording_is_sanitized() -> None:
    service = FakeImuService(ImuSeriesDisplay(False, "not_found", None))

    async with client_for(service) as client:
        response = await client.get("/api/recordings/99/imu-series")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "recording_not_found"
