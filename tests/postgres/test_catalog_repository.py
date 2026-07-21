from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from conftest import create_recording, require_optional_prerequisite
from rosbag_analyser.api.app import create_app
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.catalog.types import (
    RecordingScanResult,
    RootScanError,
    RosHealth,
    ScanSnapshot,
    SourceComponentResult,
    SourceCondition,
    SourceRole,
)
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.database import apply_catalog_migration, open_connection


TEST_DATABASE_ENV = "ROS_BAG_ANALYSER_TEST_DATABASE_URL"
ALLOW_TEST_DATABASE_RESET_ENV = "ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET"
TEST_DATABASE_NAME = "rosbag_analyser_test"


def _is_disposable_test_database_name(database_name: str) -> bool:
    return database_name == TEST_DATABASE_NAME or database_name.startswith(
        f"{TEST_DATABASE_NAME}_"
    )


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def postgres_url(pytestconfig: pytest.Config) -> str:
    database_url = os.environ.get(TEST_DATABASE_ENV)
    require_optional_prerequisite(
        pytestconfig,
        option_name="require_postgres",
        ready=bool(database_url),
        message=f"{TEST_DATABASE_ENV} is not configured",
    )
    assert database_url is not None
    if os.environ.get(ALLOW_TEST_DATABASE_RESET_ENV) != "1":
        pytest.fail(
            f"{ALLOW_TEST_DATABASE_RESET_ENV}=1 is required before resetting "
            "the test database."
        )
    database_name = unquote(urlsplit(database_url).path.rsplit("/", 1)[-1])
    if not _is_disposable_test_database_name(database_name):
        pytest.fail(
            f"The PostgreSQL test database must be named {TEST_DATABASE_NAME} "
            f"or start with {TEST_DATABASE_NAME}_."
        )
    with open_connection(database_url) as connection:
        actual_database_name = str(
            connection.execute("SELECT current_database() AS name").fetchone()["name"]
        )
    if actual_database_name != database_name:
        pytest.fail(
            "The PostgreSQL server selected a different database than configured."
        )
    apply_catalog_migration(database_url)
    with open_connection(database_url) as connection:
        connection.execute(
            "TRUNCATE source_components, recordings RESTART IDENTITY"
        )
    return database_url


@pytest.mark.parametrize(
    "database_name",
    ["latest", "contest", "protest", "test-production", "production"],
)
def test_destructive_reset_guard_rejects_ambiguous_names(database_name: str) -> None:
    assert not _is_disposable_test_database_name(database_name)


@pytest.mark.parametrize(
    "database_name",
    ["rosbag_analyser_test", "rosbag_analyser_test_local"],
)
def test_destructive_reset_guard_accepts_dedicated_names(database_name: str) -> None:
    assert _is_disposable_test_database_name(database_name)


def _snapshot(revision: str = "a" * 64) -> ScanSnapshot:
    components = tuple(
        SourceComponentResult(
            role=role,
            condition=(
                SourceCondition.READABLE
                if role in {SourceRole.METADATA, SourceRole.ROS_DATABASE}
                else SourceCondition.PRESENT
            ),
            relative_path=f"run/{role.value}",
            size_bytes=10,
            mtime_ns=20,
        )
        for role in SourceRole
    )
    recording = RecordingScanResult(
        archive_relative_path="run",
        display_name="run",
        start_time_ns=100,
        duration_ns=200,
        total_source_size_bytes=40,
        storage_format="sqlite3",
        metadata_version=5,
        message_count=3,
        topic_count=2,
        ros_health=RosHealth.READABLE,
        diagnostic=None,
        source_revision=revision,
        components=components,
    )
    return ScanSnapshot(recordings=(recording,), duration_ms=1)


@pytest.mark.postgres
def test_migration_contains_only_two_block_one_domain_tables(postgres_url: str) -> None:
    with open_connection(postgres_url) as connection:
        rows = connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        ).fetchall()

    assert [row["table_name"] for row in rows] == ["recordings", "source_components"]


@pytest.mark.postgres
def test_root_scan_failure_preserves_last_catalog_snapshot(postgres_url: str) -> None:
    repository = CatalogRepository(postgres_url)
    repository.apply_snapshot(_snapshot())
    before = repository.list_recordings()

    class FailingScanner:
        def scan(self):
            raise RootScanError(
                "archive_enumeration_failed",
                "The archive root could not be enumerated.",
            )

    service = CatalogService(FailingScanner(), repository)  # type: ignore[arg-type]

    with pytest.raises(RootScanError):
        service.rescan()

    assert repository.list_recordings() == before


@pytest.mark.postgres
def test_identical_snapshot_preserves_ids_counts_and_timestamps(postgres_url: str) -> None:
    repository = CatalogRepository(postgres_url)
    repository.apply_snapshot(_snapshot())
    with open_connection(postgres_url) as connection:
        first_recording = connection.execute(
            "SELECT id, updated_at FROM recordings"
        ).fetchone()
        first_components = connection.execute(
            "SELECT id, updated_at FROM source_components ORDER BY role"
        ).fetchall()

    repository.apply_snapshot(_snapshot())
    with open_connection(postgres_url) as connection:
        second_recording = connection.execute(
            "SELECT id, updated_at FROM recordings"
        ).fetchone()
        second_components = connection.execute(
            "SELECT id, updated_at FROM source_components ORDER BY role"
        ).fetchall()

    assert second_recording == first_recording
    assert second_components == first_components
    assert len(repository.list_recordings()) == 1


@pytest.mark.postgres
def test_changed_snapshot_updates_existing_row_in_place(postgres_url: str) -> None:
    repository = CatalogRepository(postgres_url)
    repository.apply_snapshot(_snapshot())
    first = repository.list_recordings()[0]

    repository.apply_snapshot(_snapshot("b" * 64))
    second = repository.list_recordings()[0]

    assert first.id == second.id
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM recordings").fetchone()["count"] == 1
        assert connection.execute("SELECT count(*) AS count FROM source_components").fetchone()["count"] == 4


@pytest.mark.postgres
def test_transaction_rolls_back_when_later_recording_is_invalid(postgres_url: str) -> None:
    repository = CatalogRepository(postgres_url)
    valid = _snapshot().recordings[0]
    invalid = RecordingScanResult(
        **{
            **valid.__dict__,
            "archive_relative_path": "invalid",
            "display_name": "invalid",
            "components": (valid.components[0], valid.components[0]),
        }
    )
    snapshot = ScanSnapshot(recordings=(valid, invalid), duration_ms=1)

    with pytest.raises(ValueError, match="duplicate component"):
        repository.apply_snapshot(snapshot)

    assert repository.list_recordings() == ()


@pytest.mark.postgres
@pytest.mark.anyio
async def test_real_api_scanner_and_postgres_vertical_slice(
    postgres_url: str, tmp_path
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    create_recording(archive, "damaged", damaged=True)
    service = CatalogService(CatalogScanner(archive), CatalogRepository(postgres_url))
    app = create_app(service)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            rescan = await client.post("/api/catalog/rescan")
            listing = await client.get("/api/recordings")
            damaged_item = next(
                item
                for item in listing.json()["items"]
                if item["ros_health"] == "damaged"
            )
            detail = await client.get(f"/api/recordings/{damaged_item['id']}")

    assert rescan.status_code == 200
    assert rescan.json()["recording_count"] == 2
    assert rescan.json()["readable_count"] == 1
    assert rescan.json()["damaged_count"] == 1
    assert listing.status_code == 200
    components = {item["role"]: item for item in detail.json()["components"]}
    assert components["ros_database"]["condition"] == "damaged"
    assert components["topdown_video"]["condition"] == "present"
    assert components["topdown_timestamps"]["condition"] == "present"
