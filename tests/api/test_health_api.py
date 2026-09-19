from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import time

import httpx
import pytest

from rosbag_analyser.api.app import create_app
from rosbag_analyser.health import Capability, HealthService, ReadinessReport


pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class NoSourceCatalogService:
    def list_recordings(self):
        raise AssertionError("health must not read the catalog")


class FakeHealthService(HealthService):
    def __init__(self) -> None:
        super().__init__("release-test")
        self.readiness_calls = 0

    def readiness(self) -> ReadinessReport:
        self.readiness_calls += 1
        return ReadinessReport(
            ready=False,
            release_id="release-test",
            capabilities={
                "database": Capability(False, "database_unavailable"),
                "catalog": Capability(False, "database_unavailable"),
                "artifact_delivery": Capability(True),
                "source_access": Capability(False, "source_mount_unavailable"),
                "new_preparation": Capability(False, "source_mount_unavailable"),
                "worker_observation": Capability(False, "database_unavailable"),
            },
        )


@pytest.mark.anyio
async def test_liveness_and_readiness_are_separate_and_sanitized() -> None:
    health = FakeHealthService()
    app = create_app(NoSourceCatalogService(), health_service=health)

    @asynccontextmanager
    async def lifespan():
        async with app.router.lifespan_context(app):
            yield

    transport = httpx.ASGITransport(app=app)
    async with lifespan(), httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive", "release_id": "release-test"}
    assert health.readiness_calls == 1
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["platform_support_end"] == "2027-05"
    assert ready.json()["capabilities"]["source_access"] == {
        "available": False,
        "code": "source_mount_unavailable",
    }
    serialized = ready.text
    assert "/srv/" not in serialized
    assert "postgresql://" not in serialized
    assert "traceback" not in serialized.lower()


def test_slow_readiness_does_not_block_other_requests() -> None:
    class SlowHealth(HealthService):
        def readiness(self) -> ReadinessReport:
            time.sleep(0.25)
            return super().readiness()

    app = create_app(NoSourceCatalogService(), health_service=SlowHealth("test"))
    ready_route = next(route for route in app.router.routes if route.path == "/health/ready")
    live_route = next(route for route in app.router.routes if route.path == "/health/live")
    async def check() -> None:
        async with app.router.lifespan_context(app):
            ready = asyncio.create_task(ready_route.endpoint())
            await asyncio.sleep(0.01)
            started = time.monotonic()
            live = await live_route.endpoint()
            elapsed = time.monotonic() - started
            assert live.status_code == 200
            assert elapsed < 0.2
            assert (await ready).status_code == 200

    asyncio.run(check())
