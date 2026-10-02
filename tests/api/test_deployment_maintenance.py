from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from rosbag_analyser import maintenance
from rosbag_analyser.api.app import create_app


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_deployment_blocks_writes_but_keeps_reads_and_health_available(tmp_path, monkeypatch):
    marker = tmp_path / 'maintenance'
    monkeypatch.setattr(maintenance, 'MAINTENANCE_FILE', marker)
    app = create_app(SimpleNamespace())
    writes = []

    @app.post('/maintenance-test')
    async def write():
        writes.append(True)
        return {'ok': True}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            marker.touch()
            for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                response = await client.request(method, '/api/v1/catalog/rescan')
                assert response.status_code == 503
                assert response.json()['detail']['code'] == 'deployment_in_progress'
                assert response.headers['Retry-After'] == '30'
                assert response.headers['X-Content-Type-Options'] == 'nosniff'
            assert (await client.get('/health/live')).status_code == 200
            assert (await client.get('/')).status_code == 200
            assert (await client.post('/maintenance-test')).status_code == 503
            assert writes == []
            marker.unlink()
            assert (await client.post('/maintenance-test')).status_code == 200
            assert writes == [True]
