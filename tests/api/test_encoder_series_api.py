from dataclasses import replace
import httpx
import pytest

from rosbag_analyser.api.app import create_app
from rosbag_analyser.api.v1_schemas import PrepareSelectedRequest, _artifact_response
from rosbag_analyser.encoder_series import ENCODER_SERIES_DEFINITIONS, EncoderSeriesDisplay
from test_imu_series_api import FakeImuService, UnusedCatalogService, _artifact

pytestmark = pytest.mark.anyio

@pytest.fixture()
def anyio_backend(): return "asyncio"

def artifact():
    previous = _artifact()
    manifest = {**previous.manifest, "artifact_kind": "encoder_series",
        "source": {"topic": "/rover/encoders", "default_component": "encoder.FL", "default_series_id": "wheel_fl"},
        "series": [{**d.identity_values(), "finite": 200, "non_finite": 1,
                    "minimum": -1.5, "maximum": 2.25, "available": True} for d in ENCODER_SERIES_DEFINITIONS]}
    return replace(previous, kind="encoder_series", manifest=manifest)

async def test_encoder_routes_return_wheel_order_and_identity_bound_data(tmp_path):
    a = artifact()
    path = tmp_path / "series.json"
    path.write_bytes(b"encoder-data")
    service = FakeImuService(EncoderSeriesDisplay(True, "ready", 2_500_000_000, artifact=a), data_path=path)
    app = create_app(UnusedCatalogService(), encoder_series_service=service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/recordings/7/encoder-series")
            assert response.status_code == 200
            data = response.json()["artifact"]
            assert [s["component"] for s in data["series"]] == [d.component for d in ENCODER_SERIES_DEFINITIONS]
            assert [s["units"] for s in data["series"]] == ["RPM"] * 6
            assert data["data_url"] == "/api/recordings/7/encoder-series/data/6"
            assert data["timestamp_provenance"] == "ros_record_timestamp"
            assert _artifact_response(7, a).url == data["data_url"]
            assert (await client.get(data["data_url"], headers={"Range": "bytes=0-6"})).content == b"encoder"
            assert (await client.head(data["data_url"])).content == b""
            assert (await client.get("/api/recordings/7/encoder-series/data/999")).status_code == 404

async def test_encoder_request_has_same_queue_and_poll_contract():
    service = FakeImuService(EncoderSeriesDisplay(True, "not_requested", 100), requested=EncoderSeriesDisplay(True, "queued", 100))
    app = create_app(UnusedCatalogService(), encoder_series_service=service)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post("/api/recordings/7/encoder-series")
            assert response.status_code == 202
            assert response.json()["poll_after_ms"] == 1000
            assert service.request_count == 1
    assert "encoder_series" in PrepareSelectedRequest(recording_ids=[7]).output_kinds
