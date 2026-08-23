from __future__ import annotations

from contextlib import asynccontextmanager
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
    EstimateView,
    InvalidProcessingCursor,
    ProcessingJobView,
    ProcessingOverview,
    ProcessingPage,
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
    def prepare_selected(self, recording_ids: tuple[int, ...]) -> PrepareSelectedResult:
        return PrepareSelectedResult(
            recordings=tuple(
                PrepareRecordingResult(
                    recording_id=recording_id,
                    outcome="accepted",
                    analysis_state="queued",
                    outputs=(
                        PrepareOutputResult(
                            "front_preview", "ready_reused", "ready", artifact_id=90
                        ),
                        PrepareOutputResult(
                            "topdown_preview", "queued", "queued", job_id=31
                        ),
                        PrepareOutputResult(
                            "imu_series", "active_reused", "queued", job_id=32
                        ),
                    ),
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
        runtime_ms=None,
        diagnostic=None,
        output_size_bytes=None,
        queue_position=None if state == "running" else 1,
        estimate=EstimateView("available", 5000, 3000, "median_rate_v1", 3)
        if state == "running"
        else None,
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
            current=_job(),
            queue=(_job("queued"),),
            recommended_poll_interval_ms=1000,
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


@asynccontextmanager
async def client_for(
    *,
    v1_catalog_service=FakeV1CatalogService(),
    preparation_service=FakePreparationService(),
    processing_service=FakeProcessingService(),
    prepare_max_recordings: int = 100,
):
    app = create_app(
        FakeCatalogService(),
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
    assert overview.json()["current"]["elapsed_ms"] == 2000
    assert overview.json()["current"]["estimate"]["remaining_ms"] == 3000
    assert page.status_code == 200
    assert page.json()["items"][0]["queue_position"] == 1
    assert invalid.status_code == 422
    assert retry.status_code == 202
    assert unknown.status_code == 404
    assert conflict.status_code == 409


async def test_database_failure_does_not_leak_private_diagnostic() -> None:
    class BrokenCatalog:
        def get_catalog(self):
            raise psycopg.OperationalError("password=secret /private/archive")

    async with client_for(v1_catalog_service=BrokenCatalog()) as client:
        response = await client.get("/api/v1/catalog")

    assert response.status_code == 503
    assert "secret" not in response.text
    assert "/private/archive" not in response.text
