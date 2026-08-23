from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from conftest import inventory, require_optional_prerequisite
from rosbag_analyser.api.app import create_app
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.config import AppConfig
from rosbag_analyser.front_preview import encoder_identity
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.database import apply_catalog_migration, open_connection
from rosbag_analyser.persistence.processing_repository import (
    FRONT_PREVIEW_KIND,
    IMU_SERIES_KIND,
    TOPDOWN_PREVIEW_KIND,
    ProcessingRepository,
    WORKER_LOCK_NAME,
)
from rosbag_analyser.preparation import PreparationService
from rosbag_analyser.preparation_planner import PreparationPlanner
from rosbag_analyser.processing_view import ProcessingViewService
from rosbag_analyser.v1_catalog import V1CatalogService


TEST_DATABASE_ENV = "ROS_BAG_ANALYSER_TEST_DATABASE_URL"
ALLOW_TEST_DATABASE_RESET_ENV = "ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET"


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


class _NoArtifactStore:
    def validate_media(self, *args) -> None:
        raise AssertionError("The final real catalog read must find no test artifact.")

    def validate_series_artifact(self, *args) -> None:
        raise AssertionError("The final real catalog read must find no test artifact.")


@asynccontextmanager
async def _client_for(app):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield client


@pytest.mark.real_archive
@pytest.mark.postgres
@pytest.mark.anyio
async def test_opt_in_v1_real_rescan_api_reads_and_source_inventory_are_unchanged(
    pytestconfig: pytest.Config,
) -> None:
    require_optional_prerequisite(
        pytestconfig,
        option_name="require_real_archive",
        ready=os.environ.get("RUN_REAL_ARCHIVE_TESTS") == "1",
        message="Real-archive checks require RUN_REAL_ARCHIVE_TESTS=1",
    )
    root_value = os.environ.get("ROS_BAG_ANALYSER_ARCHIVE_ROOT")
    if not root_value:
        pytest.fail("ROS_BAG_ANALYSER_ARCHIVE_ROOT must be configured explicitly")
    expected_damaged_database = os.environ.get(
        "ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE"
    )
    if not expected_damaged_database:
        pytest.fail(
            "ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE must identify the "
            "acceptance case"
        )
    database_url = os.environ.get(TEST_DATABASE_ENV)
    if not database_url:
        pytest.fail(f"{TEST_DATABASE_ENV} must select a disposable database")
    database_name = unquote(urlsplit(database_url).path.rsplit("/", 1)[-1])
    if not database_name.startswith("rosbag_analyser_test_"):
        pytest.fail("The real acceptance database must have the disposable test prefix.")
    if os.environ.get(ALLOW_TEST_DATABASE_RESET_ENV) != "1":
        pytest.fail(f"{ALLOW_TEST_DATABASE_RESET_ENV}=1 is required")

    config = AppConfig.from_environment()
    archive_root = Path(root_value).resolve(strict=True)
    assert config.archive_root == archive_root
    assert config.archive_root != config.derived_root
    assert config.archive_root not in config.derived_root.parents
    assert config.derived_root not in config.archive_root.parents

    apply_catalog_migration(database_url)
    with open_connection(database_url) as connection:
        connection.execute(
            """
            TRUNCATE preparation_targets, jobs, artifacts,
                     source_components, recordings RESTART IDENTITY
            """
        )
        connection.execute(
            """
            UPDATE catalog_state
            SET successful_generation = 0,
                successful_completed_at = NULL,
                duration_ms = 0,
                recording_count = 0,
                readable_count = 0,
                damaged_count = 0,
                missing_count = 0,
                unsupported_count = 0,
                uninspectable_count = 0
            WHERE singleton = TRUE
            """
        )

    planner = PreparationPlanner(
        front_topic=config.front_topic,
        imu_topic=config.imu_topic,
        imu_component=config.imu_component,
        profile=config.preview_profile,
        encoder_identity=encoder_identity(),
    )
    catalog_repository = CatalogRepository(database_url, planner)
    processing_repository = ProcessingRepository(database_url)
    catalog_service = CatalogService(
        CatalogScanner(archive_root, limits=config.catalog_scan_limits),
        catalog_repository,
    )
    no_artifact_store = _NoArtifactStore()
    preparation_service = PreparationService(
        catalog_repository,
        processing_repository,
        planner,
        {
            FRONT_PREVIEW_KIND: no_artifact_store,
            TOPDOWN_PREVIEW_KIND: no_artifact_store,
            IMU_SERIES_KIND: no_artifact_store,
        },
    )
    v1_catalog_service = V1CatalogService(
        catalog_repository,
        preparation_service,
        max_recordings=config.catalog_scan_limits.max_recordings,
    )
    processing_view_service = ProcessingViewService(
        processing_repository,
        planner,
        worker_lock_name=WORKER_LOCK_NAME,
    )
    app = create_app(
        catalog_service,
        v1_catalog_service=v1_catalog_service,
        preparation_service=preparation_service,
        processing_view_service=processing_view_service,
        prepare_max_recordings=config.prepare_max_recordings,
    )

    before = inventory(archive_root)
    rescan = catalog = detail = damaged_detail_response = overview = None
    try:
        async with _client_for(app) as client:
            rescan = await client.post("/api/v1/catalog/rescan")
            catalog = await client.get("/api/v1/catalog")
            first_id = catalog.json()["recordings"][0]["id"]
            detail = await client.get(f"/api/v1/recordings/{first_id}")
            damaged_id = next(
                item["id"]
                for item in catalog.json()["recordings"]
                if item["ros_health"] == "damaged"
            )
            damaged_detail_response = await client.get(
                f"/api/v1/recordings/{damaged_id}"
            )
            overview = await client.get("/api/v1/processing/overview")
    finally:
        after = inventory(archive_root)

    assert after == before
    assert rescan is not None and rescan.status_code == 200
    assert catalog is not None and catalog.status_code == 200
    assert detail is not None and detail.status_code == 200
    assert overview is not None and overview.status_code == 200
    scan = rescan.json()["scan"]
    assert scan["generation"] == 1
    assert scan["counts"] == {
        "recordings": 6,
        "readable": 5,
        "damaged": 1,
        "missing": 0,
        "unsupported": 0,
        "uninspectable": 0,
    }
    document = catalog.json()
    assert document["scan"]["generation"] == 1
    assert len(document["recordings"]) == 6
    assert all(len(item["outputs"]) == 3 for item in document["recordings"])
    assert "archive_relative_path" not in catalog.text + detail.text
    assert str(archive_root) not in catalog.text + detail.text
    assert damaged_detail_response is not None
    database_component = next(
        item
        for item in damaged_detail_response.json()["components"]
        if item["role"] == "ros_database"
    )
    assert database_component["file_name"] == expected_damaged_database
    assert database_component["diagnostic"]["code"] == "sqlite_size_mismatch"
    assert overview.json()["running_count"] == 0
    assert overview.json()["queued_count"] == 0
    assert overview.json()["failed_count"] == 0
    assert overview.json()["succeeded_count"] == 0

    with open_connection(database_url) as connection:
        counts = connection.execute(
            """
            SELECT (SELECT count(*) FROM recordings) AS recordings,
                   (SELECT count(*) FROM preparation_targets) AS targets,
                   (SELECT count(*) FROM jobs) AS jobs,
                   (SELECT count(*) FROM artifacts) AS artifacts
            """
        ).fetchone()
    assert counts == {"recordings": 6, "targets": 18, "jobs": 0, "artifacts": 0}
