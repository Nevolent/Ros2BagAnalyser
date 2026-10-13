import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from rosbag_analyser.api import app as api
from rosbag_analyser.api.v1_routes import discovery_future
from rosbag_analyser.catalog.types import RootScanError


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_monitor_discovers_without_browser_and_recovers_after_source_failure(monkeypatch):
    calls = []
    def discover():
        calls.append(True)
        if len(calls) == 1:
            raise RootScanError('source_unavailable', 'Synthetic unavailable source.')
        return 1
    monkeypatch.setattr(api, 'deployment_in_progress', lambda: False)
    with ThreadPoolExecutor(max_workers=1) as executor:
        application = SimpleNamespace(state=SimpleNamespace(catalog_scan_executor=executor,
            catalog_service=SimpleNamespace(discover_new=discover)))
        monitor = asyncio.create_task(api._monitor_recordings(application, interval=0.01))
        try:
            async def wait_for_discovery():
                while len(calls) < 2:
                    await asyncio.sleep(0.01)
            await asyncio.wait_for(wait_for_discovery(), timeout=2)
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
    assert len(calls) >= 2


@pytest.mark.anyio
async def test_browser_and_monitor_share_discovery_and_maintenance_blocks_new_scans(monkeypatch):
    calls = []
    monkeypatch.setattr(api, 'deployment_in_progress', lambda: True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        application = SimpleNamespace(state=SimpleNamespace(catalog_scan_executor=executor,
            catalog_service=SimpleNamespace(discover_new=lambda: calls.append(True) or 1)))
        monitor = asyncio.create_task(api._monitor_recordings(application, interval=0.01))
        await asyncio.sleep(0.03)
        assert calls == []
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        first = discovery_future(application)
        assert discovery_future(application) is first
        assert await first == 1 and calls == [True]
