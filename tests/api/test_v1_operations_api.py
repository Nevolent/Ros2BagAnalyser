from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import psycopg
import pytest

from rosbag_analyser.api.app import create_app
from rosbag_analyser.catalog.service import RescanResult
from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.persistence.catalog_repository import (
    CatalogComponent,
    CatalogRecording,
    CatalogRecordingDetail,
    CatalogState,
)
from rosbag_analyser.persistence.processing_repository import ArtifactRecord
from rosbag_analyser.preparation import (
    OutputFact,
    PrepareOutputResult,
    PrepareRecordingResult,
    PrepareSelectedResult,
    RecordingAnalysis,
)
from rosbag_analyser.processing_view import (
    BulkControlResult,
    ControlResult,
    EstimateView,
    InvalidProcessingCursor,
    ProcessingJobView,
    ProcessingOverview,
    ProcessingPage,
    RecordingProgress,
    RetryResult,
)
from rosbag_analyser.v1_catalog import (
    FolderNode,
    V1CatalogItem,
    V1CatalogView,
    V1RecordingDetail,
)


pytestmark = pytest.mark.anyio
NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _recording() -> CatalogRecording:
    return CatalogRecording(
        id=12,
        archive_relative_path="site/day/run-12",
        display_name="run-12",
        start_time_ns=1_700_000_000_000_000_000,
        duration_ns=3_000_000_000,
        total_source_size_bytes=45_000,
        storage_format="sqlite3",
        metadata_version=5,
        message_count=60,
        topic_count=3,
        ros_health="readable",
        diagnostic=None,
        source_present=True,
        last_seen_generation=4,
    )


def _artifact() -> ArtifactRecord:
    return ArtifactRecord(
        id=90,
        recording_id=12,
        kind="front_preview",
        cache_identity="a" * 64,
        output_relative_path="front_preview/12/private/output.mp4",
        mime_type="video/mp4",
        size_bytes=1234,
        coverage_start_ns=100,
        coverage_end_ns=200,
        manifest={
            "timing": {
                "timestamp_provenance": "ros_image_header_affine_to_record_span"
            }
        },
        created_at=NOW,
    )


def _analysis() -> RecordingAnalysis:
    return RecordingAnalysis(
        recording_id=12,
        analysis_state="failed",
        outputs=(
            OutputFact("front_preview", "ready", artifact=_artifact()),
            OutputFact("topdown_preview", "queued", job_id=22),
            OutputFact(
                "imu_series",
                "failed",
                SafeDiagnostic("imu_decode_failed", "IMU decoding failed."),
                job_id=23,
            ),
        ),
    )


class FakeCatalogService:
    def discover_new(self) -> int:
        return 2

    def rescan(self) -> RescanResult:
        return RescanResult(
            recording_count=1,
            readable_count=1,
            damaged_count=0,
            missing_count=0,
            unsupported_count=0,
            uninspectable_count=0,
            duration_ms=13,
            diagnostics=(),
            generation=5,
            completed_at=NOW,
        )


class HeldRescanService(FakeCatalogService):
    def __init__(self, *, fail=False):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.fail = fail

    def rescan(self):
        self.calls += 1
        self.started.set()
        assert self.release.wait(5)
        if self.fail:
            raise RuntimeError('/private/source/secret.db3')
        return super().rescan()


async def test_rescan_survives_request_cancellation_and_new_browsers_share_status():
    service = HeldRescanService()
    try:
        async with client_for(catalog_service=service) as client:
            initiating = asyncio.create_task(client.post('/api/catalog/rescan'))
            for _ in range(100):
                if service.started.is_set():
                    break
                await asyncio.sleep(.01)
            assert service.started.is_set()
            initiating.cancel()
            with pytest.raises(asyncio.CancelledError):
                await initiating
            async with httpx.AsyncClient(transport=client._transport,
                                         base_url='http://testserver') as other:
                assert (await other.get('/api/v1/catalog/rescan/status')).json()['running']
                repeated = await other.post('/api/v1/catalog/rescan?background=true')
                assert repeated.status_code == 202
                assert repeated.json()['running']
                waiting = asyncio.create_task(other.post('/api/v1/catalog/rescan'))
                await asyncio.sleep(.02)
                assert service.calls == 1
                assert (await other.get('/api/v1/catalog')).status_code == 200
                service.release.set()
                assert (await waiting).status_code == 200
                assert (await other.get('/api/v1/catalog/rescan/status')).json() == {
                    'running': False, 'diagnostic': None,
                }
    finally:
        service.release.set()


async def test_background_rescan_returns_promptly_and_reports_safe_failure():
    service = HeldRescanService(fail=True)
    try:
        async with client_for(catalog_service=service) as client:
            started = await asyncio.wait_for(client.post('/api/v1/catalog/rescan?background=true'), .5)
            assert started.status_code == 202
            service.release.set()
            for _ in range(100):
                response = await client.get('/api/v1/catalog/rescan/status')
                if not response.json()['running']:
                    break
                await asyncio.sleep(.01)
            assert response.json()['diagnostic']['code'] == 'catalog_rescan_failed'
            assert '/private' not in response.text
            assert not response.json()['running']
    finally:
        service.release.set()


class FakeV1CatalogService:
    def get_catalog(self) -> V1CatalogView:
        recording = _recording()
        return V1CatalogView(
            scan=CatalogState(4, NOW, 11, 1, 1, 0, 0, 0, 0),
            summary={
                "recordings": 1,
                "ready": 0,
                "processing": 0,
                "queued": 0,
                "failed": 1,
                "damaged": 0,
            },
            folders=(FolderNode("site", "", "site", 0, 1),),
            recordings=(
                V1CatalogItem(recording, "site/day", "readable", _analysis()),
            ),
        )

    def get_recording(self, recording_id: int) -> V1RecordingDetail | None:
        if recording_id != 12:
            return None
        return V1RecordingDetail(
            detail=CatalogRecordingDetail(
                _recording(),
                (
                    CatalogComponent(
                        "metadata",
                        "readable",
                        "metadata.yaml",
                        500,
                        1_700_000_000_000_000_001,
                        None,
                    ),
                ),
            ),
            folder_path="site/day",
            presentation_health="readable",
            analysis=_analysis(),
        )


class FakePreparationService:
    def prepare_selected(
        self,
        recording_ids: tuple[int, ...],
        output_kinds=("front_preview", "topdown_preview", "imu_series"),
    ) -> PrepareSelectedResult:
        return PrepareSelectedResult(
            recordings=tuple(
                PrepareRecordingResult(
                    recording_id=recording_id,
                    outcome="accepted",
                    analysis_state="queued",
                    outputs=tuple(output for output in (
                        PrepareOutputResult(
                            "front_preview", "ready_reused", "ready", artifact_id=90
                        ),
                        PrepareOutputResult(
                            "topdown_preview", "queued", "queued", job_id=31
                        ),
                        PrepareOutputResult(
                            "imu_series", "active_reused", "queued", job_id=32
                        ),
                    ) if output.kind in output_kinds),
                )
                for recording_id in recording_ids
            ),
            has_active_work=True,
        )


def _job(state: str = "running") -> ProcessingJobView:
    return ProcessingJobView(
        id=31,
        recording_id=12,
        recording_name="run-12",
        kind="topdown_preview",
        state=state,
        queued_at=NOW,
        started_at=NOW if state == "running" else None,
        finished_at=None,
        queued_age_ms=2000,
        elapsed_ms=2000 if state == "running" else None,
        active_elapsed_ms=2000 if state == "running" else None,
        paused_ms=0,
        runtime_ms=None,
        diagnostic=None,
        output_size_bytes=None,
        queue_position=None if state == "running" else 1,
        estimate=EstimateView("available", 5000, 3000, "median_rate_v1", 3)
        if state == "running"
        else None,
        queue_estimate=None,
        control_state="none",
        execution_phase="processing" if state == "running" else None,
        control_revision=0,
        allowed_controls=("pause", "cancel") if state == "running" else ("cancel",),
    )


class FakeProcessingService:
    def overview(self) -> ProcessingOverview:
        return ProcessingOverview(
            server_time=NOW,
            worker_online=True,
            running_count=1,
            queued_count=1,
            failed_count=0,
            succeeded_count=4,
            canceled_count=0,
            current=_job(),
            queue=(_job("queued"),),
            recommended_poll_interval_ms=1000,
            recording_progress=RecordingProgress(
                7, 7, "run", 44, 12000, 30000, "available", False,
            ),
        )

    def jobs(self, view, *, limit, cursor, search) -> ProcessingPage:
        del view, limit, search
        if cursor is not None:
            raise InvalidProcessingCursor("invalid")
        return ProcessingPage((_job("queued"),), "next-safe-cursor")

    def retry(self, failed_job_id: int) -> RetryResult:
        if failed_job_id == 404:
            return RetryResult("not_found", "unavailable")
        if failed_job_id == 409:
            return RetryResult("conflict", "unavailable")
        return RetryResult(
            "retry_queued",
            "queued",
            recording_id=12,
            kind="imu_series",
            job_id=44,
        )

    def pause(self, job_id: int) -> ControlResult:
        if job_id == 404:
            return ControlResult(job_id, "not_found", None)
        return ControlResult(
            job_id,
            "requested",
            replace(_job(), control_state="pause_requested", allowed_controls=("resume", "cancel")),
        )

    def resume(self, job_id: int) -> ControlResult:
        return ControlResult(job_id, "resumed", _job())

    def cancel(self, job_id: int) -> ControlResult:
        if job_id == 409:
            return ControlResult(job_id, "already_finalizing", _job())
        return ControlResult(
            job_id,
            "requested",
            replace(_job(), control_state="cancel_requested", allowed_controls=()),
        )

    def cancel_many(self, job_ids: tuple[int, ...]) -> BulkControlResult:
        return BulkControlResult(
            tuple(ControlResult(job_id, "canceled", None) for job_id in job_ids)
        )

    def reorder(self, job_ids: tuple[int, ...], direction: str) -> BulkControlResult:
        del direction
        return BulkControlResult(
            tuple(ControlResult(job_id, "reordered", None) for job_id in job_ids)
        )

    def retry_many(self, job_ids: tuple[int, ...]) -> tuple[RetryResult, ...]:
        return tuple(self.retry(job_id) for job_id in job_ids)


@asynccontextmanager
async def client_for(
    *,
    catalog_service=None,
    v1_catalog_service=FakeV1CatalogService(),
    preparation_service=FakePreparationService(),
    processing_service=FakeProcessingService(),
    prepare_max_recordings: int = 100,
):
    app = create_app(
        catalog_service or FakeCatalogService(),
        v1_catalog_service=v1_catalog_service,
        preparation_service=preparation_service,
        processing_view_service=processing_service,
        prepare_max_recordings=prepare_max_recordings,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            yield client


async def test_catalog_and_detail_are_saved_safe_decimal_views() -> None:
    async with client_for() as client:
        catalog = await client.get("/api/v1/catalog")
        detail = await client.get("/api/v1/recordings/12")

    assert catalog.status_code == 200
    document = catalog.json()
    assert document["scan"]["generation"] == 4
    assert document["folders"][0]["path"] == "site"
    assert document["recordings"][0]["start_time_ns"] == "1700000000000000000"
    assert [item["kind"] for item in document["recordings"][0]["outputs"]] == [
        "front_preview",
        "topdown_preview",
        "imu_series",
    ]
    assert detail.status_code == 200
    artifact = detail.json()["outputs"][0]["artifact"]
    assert artifact["coverage_start_ns"] == "100"
    assert (
        artifact["timestamp_provenance"]
        == "ros_image_header_affine_to_record_span"
    )
    assert artifact["url"] == "/api/recordings/12/front-preview/media/90"
    assert "archive_relative_path" not in catalog.text + detail.text
    assert "output_relative_path" not in detail.text
    assert "/private/" not in detail.text


async def test_rescan_returns_generation_and_safe_scan_facts() -> None:
    async with client_for() as client:
        response = await client.post("/api/v1/catalog/rescan")
    assert response.status_code == 200
    assert response.json()["scan"] == {
        "generation": 5,
        "completed_at": "2026-08-04T12:00:00Z",
        "duration_ms": 13,
        "counts": {
            "recordings": 1,
            "readable": 1,
            "damaged": 0,
            "missing": 0,
            "unsupported": 0,
            "uninspectable": 0,
        },
    }


async def test_discovery_returns_only_the_added_count() -> None:
    async with client_for() as client:
        response = await client.post("/api/v1/catalog/discover")
    assert response.status_code == 200
    assert response.json() == {"added_count": 2}


async def test_refreshes_share_discovery_without_blocking_catalog_reads() -> None:
    class BlockingDiscovery(FakeCatalogService):
        calls = 0
        started = threading.Event()
        release = threading.Event()

        def discover_new(self):
            self.calls += 1
            self.started.set()
            assert self.release.wait(3)
            return 2

    service = BlockingDiscovery()
    async with client_for(catalog_service=service) as client:
        tasks = [asyncio.create_task(client.post("/api/v1/catalog/discover")) for _ in range(3)]
        try:
            assert await asyncio.to_thread(service.started.wait, 2)
            response = await asyncio.wait_for(client.get("/api/v1/catalog"), 1)
            assert response.status_code == 200
            await asyncio.sleep(0.05)
            assert service.calls == 1
        finally:
            service.release.set()
        results = await asyncio.gather(*tasks)
        assert all(result.json() == {"added_count": 2} for result in results)


async def test_discovery_source_failure_returns_a_safe_error() -> None:
    from rosbag_analyser.catalog.types import RootScanError

    class FailedDiscovery(FakeCatalogService):
        def discover_new(self):
            raise RootScanError("archive_enumeration_failed", "An archive directory could not be enumerated completely.")

    async with client_for(catalog_service=FailedDiscovery()) as client:
        response = await client.post("/api/v1/catalog/discover")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "archive_enumeration_failed"


async def test_leaving_the_page_does_not_cancel_shared_discovery() -> None:
    class BlockingDiscovery(FakeCatalogService):
        calls = 0
        started = threading.Event()
        release = threading.Event()

        def discover_new(self):
            self.calls += 1
            self.started.set()
            assert self.release.wait(3)
            return 2

    service = BlockingDiscovery()
    async with client_for(catalog_service=service) as client:
        abandoned = asyncio.create_task(client.post("/api/v1/catalog/discover"))
        try:
            assert await asyncio.to_thread(service.started.wait, 2)
            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError):
                await abandoned
            shared = asyncio.create_task(client.post("/api/v1/catalog/discover"))
            await asyncio.sleep(0.05)
            assert service.calls == 1
        finally:
            service.release.set()
        assert (await shared).json() == {"added_count": 2}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"recording_ids": []},
        {"recording_ids": [1, 1]},
        {"recording_ids": [0]},
        {"recording_ids": [True]},
        {"recording_ids": ["1"]},
        {"recording_ids": [1], "extra": "rejected"},
    ],
)
async def test_prepare_body_validation_is_strict_and_bounded(body) -> None:
    async with client_for() as client:
        response = await client.post("/api/v1/recordings/prepare", json=body)
    assert response.status_code == 422
    assert len(response.content) < 300


async def test_prepare_enforces_configured_bound_and_preserves_request_order() -> None:
    async with client_for(prepare_max_recordings=2) as client:
        too_many = await client.post(
            "/api/v1/recordings/prepare", json={"recording_ids": [1, 2, 3]}
        )
        accepted = await client.post(
            "/api/v1/recordings/prepare", json={"recording_ids": [12, 9]}
        )

    assert too_many.status_code == 422
    assert len(too_many.content) < 300
    assert accepted.status_code == 202
    assert [item["recording_id"] for item in accepted.json()["recordings"]] == [
        12,
        9,
    ]
    assert [item["outcome"] for item in accepted.json()["recordings"][0]["outputs"]] == [
        "ready_reused",
        "queued",
        "active_reused",
    ]


async def test_prepare_accepts_only_a_unique_nonempty_output_subset() -> None:
    invalid_bodies = (
        {"recording_ids": [12], "output_kinds": []},
        {"recording_ids": [12], "output_kinds": ["imu_series", "imu_series"]},
        {"recording_ids": [12], "output_kinds": ["unknown"]},
    )
    async with client_for() as client:
        invalid = [
            await client.post("/api/v1/recordings/prepare", json=body)
            for body in invalid_bodies
        ]
        accepted = await client.post(
            "/api/v1/recordings/prepare",
            json={"recording_ids": [12], "output_kinds": ["imu_series"]},
        )

    assert all(response.status_code == 422 for response in invalid)
    assert accepted.status_code == 202
    assert [
        item["kind"] for item in accepted.json()["recordings"][0]["outputs"]
    ] == ["imu_series"]


async def test_processing_views_retry_and_cursor_errors() -> None:
    async with client_for() as client:
        overview = await client.get("/api/v1/processing/overview")
        page = await client.get("/api/v1/processing/jobs?view=queued")
        invalid = await client.get(
            "/api/v1/processing/jobs?view=history&cursor=tampered"
        )
        retry = await client.post("/api/v1/processing/jobs/44/retry")
        unknown = await client.post("/api/v1/processing/jobs/404/retry")
        conflict = await client.post("/api/v1/processing/jobs/409/retry")

    assert overview.status_code == 200
    assert overview.json()["current_stage"] == 1
    assert overview.json()["current_stage_count"] == 1
    assert overview.json()["recording_progress"]["elapsed_ms"] == 12000
    assert overview.json()["recording_progress"]["estimated_total_ms"] == 30000
    assert overview.json()["recording_progress"]["run_id"] == 7
    assert overview.json()["current"]["elapsed_ms"] == 2000
    assert overview.json()["current"]["estimate"]["remaining_ms"] == 3000
    assert page.status_code == 200
    assert page.json()["items"][0]["queue_position"] == 1
    assert invalid.status_code == 422
    assert retry.status_code == 202
    assert unknown.status_code == 404
    assert conflict.status_code == 409


async def test_processing_control_routes_are_strict_and_truthful() -> None:
    async with client_for() as client:
        pause = await client.post("/api/v1/processing/jobs/31/pause")
        resume = await client.post("/api/v1/processing/jobs/31/resume")
        cancel = await client.post("/api/v1/processing/jobs/31/cancel")
        unknown = await client.post("/api/v1/processing/jobs/404/pause")
        finalizing = await client.post("/api/v1/processing/jobs/409/cancel")
        bulk_cancel = await client.post(
            "/api/v1/processing/jobs/cancel", json={"job_ids": [31, 32]}
        )
        reorder = await client.post(
            "/api/v1/processing/jobs/reorder",
            json={"job_ids": [31, 32], "direction": "earlier"},
        )
        bulk_retry = await client.post(
            "/api/v1/processing/jobs/retry", json={"job_ids": [44, 404]}
        )
        invalid = await client.post(
            "/api/v1/processing/jobs/reorder",
            json={"job_ids": [31, 31], "direction": "sideways"},
        )

    assert pause.status_code == 202
    assert pause.json()["server_time"].endswith("Z")
    assert pause.json()["job"]["control_state"] == "pause_requested"
    assert resume.status_code == 200
    assert cancel.status_code == 202
    assert cancel.json()["job"]["allowed_controls"] == []
    assert unknown.status_code == 404
    assert finalizing.status_code == 409
    assert bulk_cancel.status_code == 200
    assert bulk_cancel.json()["server_time"].endswith("Z")
    assert [item["requested_job_id"] for item in bulk_cancel.json()["items"]] == [
        31,
        32,
    ]
    assert reorder.status_code == 200
    assert reorder.json()["server_time"].endswith("Z")
    assert bulk_retry.status_code == 202
    assert bulk_retry.json()["server_time"].endswith("Z")
    assert [item["outcome"] for item in bulk_retry.json()["items"]] == [
        "retry_queued",
        "not_found",
    ]
    assert invalid.status_code == 422


async def test_database_failure_does_not_leak_private_diagnostic() -> None:
    class BrokenCatalog:
        def get_catalog(self):
            raise psycopg.OperationalError("password=secret /private/archive")

    async with client_for(v1_catalog_service=BrokenCatalog()) as client:
        response = await client.get("/api/v1/catalog")

    assert response.status_code == 503
    assert "secret" not in response.text
    assert "/private/archive" not in response.text


def test_detail_exposes_saved_topic_inventory_gaps_and_identity_bound_camera_streams():
    from rosbag_analyser.api.v1_schemas import recording_detail_response
    inspection = {
        "topics": [{"name": "/unusual/image", "message_type": "sensor_msgs/msg/Image",
                    "serialization_format": "cdr", "message_count": "9007199254740993"}],
        "timing": {"status": "partial", "messages_checked": 2000000, "origin_ns": "1700000000000000000",
                   "gap_limit": 24, "gaps": [{"topic": "/unusual/image", "start_ns": "10",
                   "end_ns": "6000000010", "duration_ns": "6000000000"}]},
    }
    recording = replace(_recording(), scan_details=inspection)
    artifact = _artifact()
    manifest = dict(artifact.manifest, streams=[
        {"topic": "/unusual/image", "timing": {"coverage_start_ns": "100", "coverage_end_ns": "200"}},
        {"topic": "/second/image", "timing": {"coverage_start_ns": "110", "coverage_end_ns": "190"}},
    ])
    analysis = _analysis()
    analysis = replace(analysis, outputs=tuple(
        replace(output, artifact=replace(artifact, manifest=manifest))
        if output.kind == "front_preview" else output for output in analysis.outputs))
    response = recording_detail_response(V1RecordingDetail(
        detail=CatalogRecordingDetail(recording, ()), folder_path="site/day",
        presentation_health="review", analysis=analysis)).model_dump()
    assert response["topics"] == inspection["topics"]
    assert response["timing"] == inspection["timing"]
    streams = response["outputs"][0]["artifact"]["streams"]
    assert streams[1]["url"] == "/api/recordings/12/front-preview/media/90/streams/1"
    assert streams[1]["coverage_start_ns"] == "110"
