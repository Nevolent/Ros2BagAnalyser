from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import shutil
import threading
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import httpx
import psycopg
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
from rosbag_analyser.persistence.processing_repository import (
    ArtifactWrite,
    ProcessingRepository,
)
from rosbag_analyser.processors.front_preview import FrontPreviewProcessingError
from rosbag_analyser.worker import SerialWorker


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
            "TRUNCATE jobs, artifacts, source_components, recordings RESTART IDENTITY"
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
def test_migration_contains_exactly_four_v0_domain_tables(postgres_url: str) -> None:
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

    assert [row["table_name"] for row in rows] == [
        "artifacts",
        "jobs",
        "recordings",
        "source_components",
    ]


@pytest.mark.postgres
def test_front_topdown_and_imu_kinds_are_allowed_and_isolated(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    identity = "c" * 64

    front = repository.request_job(recording_id, "front_preview", identity)
    topdown = repository.request_job(recording_id, "topdown_preview", identity)
    imu = repository.request_job(recording_id, "imu_series", identity)

    assert front.job is not None
    assert topdown.job is not None
    assert imu.job is not None
    assert front.job.id != topdown.job.id
    assert imu.job.id not in {front.job.id, topdown.job.id}
    with pytest.raises(psycopg.errors.CheckViolation):
        with open_connection(postgres_url) as connection:
            connection.execute(
                """
                INSERT INTO jobs (recording_id, kind, cache_identity, state)
                VALUES (%s, 'unknown', %s, 'queued')
                """,
                (recording_id, "f" * 64),
            )


@pytest.mark.postgres
def test_processing_request_reuses_one_active_job_and_one_ready_artifact(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    identity = "d" * 64

    first = repository.request_job(recording_id, "front_preview", identity)
    repeated = repository.request_job(recording_id, "front_preview", identity)
    assert first.job is not None
    assert repeated.job is not None
    assert repeated.job.id == first.job.id

    running = repository.claim_next_job()
    assert running is not None
    assert running.id == first.job.id
    while_running = repository.request_job(recording_id, "front_preview", identity)
    assert while_running.job is not None
    assert while_running.job.id == running.id

    ready = repository.complete_job(
        running.id,
        ArtifactWrite(
            recording_id=recording_id,
            kind="front_preview",
            cache_identity=identity,
            output_relative_path="rosbag-analyser/artifacts/front_preview/dd/preview.mp4",
            mime_type="video/mp4",
            size_bytes=123,
            coverage_start_ns=10,
            coverage_end_ns=20,
            manifest={"cache_identity": identity},
        ),
    )
    after_ready = repository.request_job(recording_id, "front_preview", identity)

    assert after_ready.artifact == ready
    assert after_ready.job is None
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ] == 1
        assert connection.execute(
            "SELECT count(*) AS count FROM artifacts"
        ).fetchone()["count"] == 1


@pytest.mark.postgres
def test_request_racing_job_completion_reuses_one_ready_artifact(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    identity = "9" * 64
    requested = repository.request_job(recording_id, "front_preview", identity)
    running = repository.claim_next_job()
    assert requested.job is not None
    assert running is not None
    artifact = ArtifactWrite(
        recording_id=recording_id,
        kind="front_preview",
        cache_identity=identity,
        output_relative_path="rosbag-analyser/artifacts/front_preview/99/preview.mp4",
        mime_type="video/mp4",
        size_bytes=123,
        coverage_start_ns=10,
        coverage_end_ns=20,
        manifest={"cache_identity": identity},
    )
    start = threading.Barrier(2)

    def complete():
        start.wait()
        return repository.complete_job(running.id, artifact)

    def request():
        start.wait()
        return repository.request_job(recording_id, "front_preview", identity)

    with ThreadPoolExecutor(max_workers=2) as executor:
        completed_future = executor.submit(complete)
        requested_future = executor.submit(request)
        completed = completed_future.result(timeout=10)
        raced_request = requested_future.result(timeout=10)

    assert completed.cache_identity == identity
    if raced_request.artifact is not None:
        assert raced_request.artifact.id == completed.id
    else:
        assert raced_request.job is not None
        assert raced_request.job.id == running.id
    after_race = repository.request_job(recording_id, "front_preview", identity)
    assert after_race.artifact is not None
    assert after_race.artifact.id == completed.id
    assert after_race.job is None
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ] == 1
        assert connection.execute(
            "SELECT count(*) AS count FROM artifacts"
        ).fetchone()["count"] == 1


@pytest.mark.postgres
def test_interrupted_job_fails_without_artifact_and_explicit_retry_succeeds(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    identity = "e" * 64

    requested = repository.request_job(recording_id, "front_preview", identity)
    running = repository.claim_next_job()
    assert requested.job is not None
    assert running is not None
    assert repository.mark_running_jobs_interrupted() == (running.id,)
    assert repository.get_artifact(recording_id, "front_preview", identity) is None

    retry = repository.request_job(recording_id, "front_preview", identity)
    assert retry.job is not None
    assert retry.job.id != running.id
    rerun = repository.claim_next_job()
    assert rerun is not None
    repository.complete_job(
        rerun.id,
        ArtifactWrite(
            recording_id=recording_id,
            kind="front_preview",
            cache_identity=identity,
            output_relative_path="rosbag-analyser/artifacts/front_preview/ee/preview.mp4",
            mime_type="video/mp4",
            size_bytes=321,
            coverage_start_ns=0,
            coverage_end_ns=30,
            manifest={"cache_identity": identity},
        ),
    )

    with open_connection(postgres_url) as connection:
        states = connection.execute(
            "SELECT state FROM jobs ORDER BY id"
        ).fetchall()
        artifact_count = connection.execute(
            "SELECT count(*) AS count FROM artifacts"
        ).fetchone()["count"]
    assert [row["state"] for row in states] == ["failed", "succeeded"]
    assert artifact_count == 1


@pytest.mark.postgres
def test_explicit_retry_retires_only_the_observed_invalid_artifact(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    identity = "f" * 64
    requested = repository.request_job(recording_id, "front_preview", identity)
    running = repository.claim_next_job()
    assert requested.job is not None
    assert running is not None
    ready = repository.complete_job(
        running.id,
        ArtifactWrite(
            recording_id=recording_id,
            kind="front_preview",
            cache_identity=identity,
            output_relative_path="rosbag-analyser/artifacts/front_preview/ff/preview.mp4",
            mime_type="video/mp4",
            size_bytes=123,
            coverage_start_ns=10,
            coverage_end_ns=20,
            manifest={"cache_identity": identity},
        ),
    )

    unchanged = repository.request_job(
        recording_id,
        "front_preview",
        identity,
        invalid_artifact_id=ready.id + 1,
    )
    assert unchanged.artifact == ready

    replacement = repository.request_job(
        recording_id,
        "front_preview",
        identity,
        invalid_artifact_id=ready.id,
    )
    assert replacement.artifact is None
    assert replacement.job is not None
    assert replacement.job.id != running.id
    assert repository.get_artifact(recording_id, "front_preview", identity) is None


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
        recording_count = connection.execute(
            "SELECT count(*) AS count FROM recordings"
        ).fetchone()["count"]
        component_count = connection.execute(
            "SELECT count(*) AS count FROM source_components"
        ).fetchone()["count"]
        assert recording_count == 1
        assert component_count == 4


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


@pytest.mark.postgres
@pytest.mark.anyio
async def test_catalog_reads_complete_while_serial_worker_job_is_processing(
    postgres_url: str,
    tmp_path: Path,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    processing = ProcessingRepository(postgres_url)
    cache_identity = "8" * 64
    requested = processing.request_job(
        recording_id,
        "front_preview",
        cache_identity,
    )
    assert requested.job is not None

    processor_started = threading.Event()
    release_processor = threading.Event()

    class BlockingResolver:
        def resolve(self, selected_recording_id: int):
            assert selected_recording_id == recording_id
            return SimpleNamespace(
                descriptor=SimpleNamespace(
                    cache_identity=cache_identity,
                    topic=SimpleNamespace(
                        message_type="sensor_msgs/msg/Image",
                        serialization_format="cdr",
                    ),
                ),
                diagnostic=None,
            )

    class BlockingProcessor:
        def process(self, descriptor, output_path: Path):
            del descriptor, output_path
            processor_started.set()
            if not release_processor.wait(timeout=10):
                raise AssertionError("The test did not release the worker processor.")
            raise FrontPreviewProcessingError(
                "synthetic_processing_stopped",
                "Synthetic processing stopped after the responsiveness check.",
            )

    class TemporaryWorkspaceStore:
        def create_workspace(self, job_id: int) -> Path:
            workspace = tmp_path / "derived" / f"job-{job_id}"
            workspace.mkdir(parents=True)
            return workspace

        def clean_workspace(self, workspace: Path, job_id: int) -> None:
            assert workspace == tmp_path / "derived" / f"job-{job_id}"
            shutil.rmtree(workspace)

    worker = SerialWorker(
        processing,
        BlockingResolver(),  # type: ignore[arg-type]
        BlockingProcessor(),  # type: ignore[arg-type]
        TemporaryWorkspaceStore(),  # type: ignore[arg-type]
        "/camera/image_raw",
        "synthetic-encoder",
    )
    archive = tmp_path / "archive"
    archive.mkdir()
    app = create_app(CatalogService(CatalogScanner(archive), catalog))
    worker_task = asyncio.create_task(asyncio.to_thread(worker.run_once))

    try:
        started = await asyncio.wait_for(
            asyncio.to_thread(processor_started.wait, 5),
            timeout=6,
        )
        assert started
        assert not worker_task.done()
        running = processing.get_active_job(
            recording_id,
            "front_preview",
            cache_identity,
        )
        assert running is not None
        assert running.state == "running"

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                listing, detail = await asyncio.wait_for(
                    asyncio.gather(
                        client.get("/api/recordings"),
                        client.get(f"/api/recordings/{recording_id}"),
                    ),
                    timeout=5,
                )

        assert listing.status_code == 200
        assert detail.status_code == 200
        assert listing.json()["items"][0]["id"] == recording_id
        assert detail.json()["id"] == recording_id
        assert not worker_task.done()
    finally:
        release_processor.set()
        await asyncio.wait_for(worker_task, timeout=5)

    state = processing.get_current_state(
        recording_id,
        "front_preview",
        cache_identity,
    )
    assert state.artifact is None
    assert state.active_job is None
    assert state.latest_failed_job is not None
    assert state.latest_failed_job.error_code == "synthetic_processing_stopped"
    assert not (tmp_path / "derived" / f"job-{requested.job.id}").exists()
