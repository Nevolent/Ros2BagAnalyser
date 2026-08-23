from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import threading
from time import perf_counter
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import httpx
import psycopg
import pytest
import yaml

from conftest import create_recording, require_optional_prerequisite
from rosbag_analyser.api.app import create_app
from rosbag_analyser.api.v1_schemas import catalog_response
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
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.database import apply_catalog_migration, open_connection
from rosbag_analyser.persistence.processing_repository import (
    ArtifactWrite,
    PROCESSING_KINDS,
    ProcessingRepository,
    WORKER_LOCK_NAME,
)
from rosbag_analyser.processors.front_preview import FrontPreviewProcessingError
from rosbag_analyser.preparation import (
    OutputFact,
    PreparationService,
    RecordingAnalysis,
)
from rosbag_analyser.preparation_planner import PreparationPlanner
from rosbag_analyser.processing_view import ProcessingViewService
from rosbag_analyser.v1_catalog import V1CatalogService
from rosbag_analyser.worker import SerialWorker


TEST_DATABASE_ENV = "ROS_BAG_ANALYSER_TEST_DATABASE_URL"
ALLOW_TEST_DATABASE_RESET_ENV = "ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET"
TEST_DATABASE_NAME = "rosbag_analyser_test"
PLANNER_IDENTITIES = {
    "front_preview": "1" * 64,
    "topdown_preview": "2" * 64,
    "imu_series": "3" * 64,
}
TARGET_IDENTITIES = {
    "front_preview": "a" * 64,
    "topdown_preview": "b" * 64,
    "imu_series": "c" * 64,
}


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
                uninspectable_count = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE singleton = TRUE
            """
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


def _planner_archive(tmp_path: Path) -> tuple[Path, Path, PreparationPlanner]:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording_root = create_recording(archive, "run")
    metadata_path = recording_root / "metadata.yaml"
    document = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    information = document["rosbag2_bagfile_information"]
    information["message_count"] += 25
    information["topics_with_message_count"].append(
        {
            "topic_metadata": {
                "name": "/imu/data",
                "type": "sensor_msgs/msg/Imu",
                "serialization_format": "cdr",
                "offered_qos_profiles": "",
            },
            "message_count": 25,
        }
    )
    metadata_path.write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    planner = PreparationPlanner(
        front_topic="/camera/image_raw",
        imu_topic="/imu/data",
        imu_component="angular_velocity.z",
        profile=V0_PREVIEW_PROFILE,
        encoder_identity="synthetic-encoder",
    )
    return archive, recording_root, planner


def _insert_current_artifact_history(
    postgres_url: str,
    recording_id: int,
) -> dict[str, str]:
    identities: dict[str, str] = {}
    with open_connection(postgres_url) as connection:
        targets = connection.execute(
            """
            SELECT kind, cache_identity
            FROM preparation_targets
            WHERE recording_id = %s AND target_state = 'available'
            ORDER BY kind
            """,
            (recording_id,),
        ).fetchall()
        assert len(targets) == 3
        for target in targets:
            kind = str(target["kind"])
            cache_identity = str(target["cache_identity"])
            identities[kind] = cache_identity
            connection.execute(
                """
                INSERT INTO artifacts (
                    recording_id, kind, cache_identity,
                    output_relative_path, mime_type, size_bytes,
                    coverage_start_ns, coverage_end_ns, manifest
                ) VALUES (
                    %s, %s, %s, %s, %s, 100, 0, 1000, %s::jsonb
                )
                """,
                (
                    recording_id,
                    kind,
                    cache_identity,
                    f"{kind}/{cache_identity}/output",
                    "application/json" if kind == "imu_series" else "video/mp4",
                    json.dumps({"cache_identity": cache_identity}),
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    recording_id, kind, cache_identity, state,
                    started_at, finished_at
                ) VALUES (
                    %s, %s, %s, 'succeeded',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """,
                (recording_id, kind, cache_identity),
            )
    return identities


def _make_targets_available(
    postgres_url: str,
    recording_id: int,
    *,
    target_identities: dict[str, str] | None = None,
) -> None:
    identities = TARGET_IDENTITIES if target_identities is None else target_identities
    with open_connection(postgres_url) as connection:
        generation = connection.execute(
            "SELECT successful_generation FROM catalog_state WHERE singleton = TRUE"
        ).fetchone()["successful_generation"]
        for index, kind in enumerate(PROCESSING_KINDS, start=1):
            connection.execute(
                """
                UPDATE preparation_targets
                SET scan_generation = %s,
                    planner_identity = %s,
                    target_state = 'available',
                    cache_identity = %s,
                    diagnostic_code = NULL,
                    diagnostic_message = NULL,
                    work_units = %s
                WHERE recording_id = %s AND kind = %s
                """,
                (
                    generation,
                    PLANNER_IDENTITIES[kind],
                    identities[kind],
                    index * 100,
                    recording_id,
                    kind,
                ),
            )


@pytest.mark.postgres
def test_migration_contains_exactly_six_v1_domain_tables(postgres_url: str) -> None:
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
        "catalog_state",
        "jobs",
        "preparation_targets",
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
def test_identical_snapshot_preserves_ids_and_components_while_advancing_generation(
    postgres_url: str,
) -> None:
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
            "SELECT id, updated_at, last_seen_generation FROM recordings"
        ).fetchone()
        second_components = connection.execute(
            "SELECT id, updated_at FROM source_components ORDER BY role"
        ).fetchall()

    assert second_recording["id"] == first_recording["id"]
    assert second_recording["updated_at"] >= first_recording["updated_at"]
    assert second_recording["last_seen_generation"] == 2
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


@pytest.mark.postgres
def test_v1_migration_backfills_faithful_v0_rows_without_changing_identity(
    postgres_url: str,
) -> None:
    migration_root = (
        Path(__file__).parents[2]
        / "src"
        / "rosbag_analyser"
        / "persistence"
        / "migrations"
    )
    schema = "v1_backfill_contract"
    with open_connection(postgres_url) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        connection.execute(f"CREATE SCHEMA {schema}")
        connection.execute(f"SET search_path TO {schema}")
        try:
            for name in (
                "0001_catalog.sql",
                "0002_front_preview.sql",
                "0003_topdown_preview.sql",
                "0004_imu_series.sql",
            ):
                connection.execute((migration_root / name).read_text(encoding="utf-8"))
            connection.execute(
                """
                INSERT INTO recordings (
                    id, archive_relative_path, display_name, ros_health,
                    source_revision
                ) OVERRIDING SYSTEM VALUE
                VALUES (42, 'legacy/run', 'run', 'readable', %s)
                """,
                ("d" * 64,),
            )
            connection.execute(
                """
                INSERT INTO source_components (
                    id, recording_id, role, relative_path, condition
                ) OVERRIDING SYSTEM VALUE
                VALUES (52, 42, 'metadata', 'legacy/run/metadata.yaml', 'readable')
                """
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    id, recording_id, kind, cache_identity, state
                ) OVERRIDING SYSTEM VALUE
                VALUES (62, 42, 'front_preview', %s, 'queued')
                """,
                ("e" * 64,),
            )
            connection.execute(
                (migration_root / "0005_v1_operations.sql").read_text(
                    encoding="utf-8"
                )
            )
            connection.execute(
                (migration_root / "0006_move_reconciliation.sql").read_text(
                    encoding="utf-8"
                )
            )

            recording = connection.execute(
                """
                SELECT id, source_present, last_seen_generation,
                       cache_identity_recording_id,
                       cache_identity_relative_path, move_fingerprint
                FROM recordings WHERE id = 42
                """
            ).fetchone()
            component = connection.execute(
                "SELECT id, recording_id FROM source_components WHERE id = 52"
            ).fetchone()
            legacy_job = connection.execute(
                """
                SELECT id, work_units, estimate_key, estimated_total_ms,
                       estimate_method, estimate_sample_count
                FROM jobs WHERE id = 62
                """
            ).fetchone()
            state = connection.execute(
                "SELECT * FROM catalog_state WHERE singleton = TRUE"
            ).fetchone()
            targets = connection.execute(
                """
                SELECT kind, target_state, diagnostic_code
                FROM preparation_targets
                WHERE recording_id = 42 ORDER BY kind
                """
            ).fetchall()
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(f"DROP SCHEMA {schema} CASCADE")

    assert recording == {
        "id": 42,
        "source_present": True,
        "last_seen_generation": 0,
        "cache_identity_recording_id": 42,
        "cache_identity_relative_path": "legacy/run",
        "move_fingerprint": None,
    }
    assert component == {"id": 52, "recording_id": 42}
    assert legacy_job == {
        "id": 62,
        "work_units": None,
        "estimate_key": None,
        "estimated_total_ms": None,
        "estimate_method": None,
        "estimate_sample_count": None,
    }
    assert state["successful_generation"] == 0
    assert state["successful_completed_at"] is None
    assert state["recording_count"] == 1
    assert state["readable_count"] == 1
    assert [(row["kind"], row["target_state"], row["diagnostic_code"]) for row in targets] == [
        ("front_preview", "unavailable", "catalog_rescan_required"),
        ("imu_series", "unavailable", "catalog_rescan_required"),
        ("topdown_preview", "unavailable", "catalog_rescan_required"),
    ]


@pytest.mark.postgres
def test_generation_missing_and_reappearing_preserves_identity_and_history(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    first_summary = catalog.apply_snapshot(_snapshot())
    first = catalog.list_recordings()[0]
    processing = ProcessingRepository(postgres_url)
    attempt = processing.request_job(first.id, "front_preview", "7" * 64)
    assert attempt.job is not None

    missing_summary = catalog.apply_snapshot(ScanSnapshot((), duration_ms=2))
    assert catalog.list_recordings() == ()
    missing = catalog.list_recordings(include_missing=True)[0]
    missing_state = catalog.get_catalog_state()

    reappeared_summary = catalog.apply_snapshot(_snapshot())
    reappeared = catalog.list_recordings()[0]
    with open_connection(postgres_url) as connection:
        job_count = connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ]
        targets = connection.execute(
            """
            SELECT count(*) AS count, min(scan_generation) AS minimum,
                   max(scan_generation) AS maximum
            FROM preparation_targets WHERE recording_id = %s
            """,
            (first.id,),
        ).fetchone()

    assert (first_summary.generation, missing_summary.generation, reappeared_summary.generation) == (
        1,
        2,
        3,
    )
    assert missing.id == first.id
    assert missing.source_present is False
    assert missing.ros_health == "missing"
    assert missing.last_seen_generation == 1
    assert missing_state.recording_count == 0
    assert missing_state.missing_count == 0
    assert reappeared.id == first.id
    assert reappeared.source_present is True
    assert reappeared.ros_health == "readable"
    assert reappeared.last_seen_generation == 3
    assert job_count == 1
    assert targets == {"count": 3, "minimum": 3, "maximum": 3}


@pytest.mark.postgres
@pytest.mark.anyio
async def test_path_move_preserves_recording_identity_and_current_catalog_is_singular(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    original = catalog.list_recordings()[0]
    processing = ProcessingRepository(postgres_url)
    attempt = processing.request_job(original.id, "front_preview", "7" * 64)
    assert attempt.job is not None

    original_scan = _snapshot().recordings[0]
    moved_path = "site/day/run"
    moved = replace(
        original_scan,
        archive_relative_path=moved_path,
        components=tuple(
            replace(
                component,
                relative_path=f"{moved_path}/{component.role.value}",
            )
            for component in original_scan.components
        ),
    )
    catalog.apply_snapshot(ScanSnapshot((moved,), duration_ms=2))

    current = catalog.list_recordings()
    history = catalog.list_recordings(include_missing=True)
    state = catalog.get_catalog_state()
    with open_connection(postgres_url) as connection:
        job = connection.execute(
            "SELECT recording_id, state FROM jobs WHERE id = %s",
            (attempt.job.id,),
        ).fetchone()

    assert len(current) == 1
    assert current[0].archive_relative_path == moved_path
    assert current[0].source_present is True
    assert current[0].id == original.id
    assert history == current
    assert state.recording_count == 1
    assert state.readable_count == 1
    assert state.damaged_count == 0
    assert state.missing_count == 0
    assert job == {"recording_id": current[0].id, "state": "queued"}

    class CurrentOnlyPreparation:
        def states_for_recordings(self, recording_ids, *, generation=None):
            assert generation == 2
            return tuple(
                RecordingAnalysis(
                    recording_id,
                    "not_planned",
                    tuple(
                        OutputFact(kind, "unavailable")
                        for kind in PROCESSING_KINDS
                    ),
                )
                for recording_id in recording_ids
            )

    catalog_service = CatalogService(SimpleNamespace(), catalog)  # type: ignore[arg-type]
    v1_catalog_service = V1CatalogService(
        catalog,
        CurrentOnlyPreparation(),  # type: ignore[arg-type]
        max_recordings=100,
    )
    app = create_app(
        catalog_service,
        v1_catalog_service=v1_catalog_service,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            response = await client.get("/api/v1/catalog")
            legacy_response = await client.get("/api/recordings")

    assert response.status_code == 200
    assert legacy_response.status_code == 200
    assert [item["id"] for item in legacy_response.json()["items"]] == [
        current[0].id
    ]
    document = response.json()
    assert document["scan"]["counts"] == {
        "recordings": 1,
        "readable": 1,
        "damaged": 0,
        "missing": 0,
        "unsupported": 0,
        "uninspectable": 0,
    }
    assert document["summary"] == {
        "recordings": 1,
        "ready": 0,
        "processing": 0,
        "queued": 0,
        "failed": 0,
        "damaged": 0,
    }
    assert document["folders"] == [
        {
            "path": "site",
            "parent_path": "",
            "name": "site",
            "direct_recording_count": 0,
            "descendant_recording_count": 1,
        },
        {
            "path": "site/day",
            "parent_path": "site",
            "name": "day",
            "direct_recording_count": 1,
            "descendant_recording_count": 1,
        },
    ]
    assert [item["id"] for item in document["recordings"]] == [current[0].id]


@pytest.mark.postgres
def test_physical_parent_move_preserves_ready_targets_and_history(
    postgres_url: str,
    tmp_path: Path,
) -> None:
    archive, recording_root, planner = _planner_archive(tmp_path)
    catalog = CatalogRepository(postgres_url, planner)
    catalog.apply_snapshot(CatalogScanner(archive).scan())
    original = catalog.list_recordings()[0]
    identities = _insert_current_artifact_history(postgres_url, original.id)

    moved_parent = archive / "site" / "day"
    moved_parent.mkdir(parents=True)
    moved_root = moved_parent / recording_root.name
    recording_root.rename(moved_root)
    catalog.apply_snapshot(CatalogScanner(archive).scan())

    current = catalog.list_recordings()
    source = ProcessingRepository(postgres_url).get_source(original.id)
    with open_connection(postgres_url) as connection:
        targets = connection.execute(
            """
            SELECT kind, cache_identity
            FROM preparation_targets
            WHERE recording_id = %s AND target_state = 'available'
            ORDER BY kind
            """,
            (original.id,),
        ).fetchall()
        current_ready = connection.execute(
            """
            SELECT count(*) AS count
            FROM preparation_targets AS target
            JOIN artifacts AS artifact
              ON artifact.recording_id = target.recording_id
             AND artifact.kind = target.kind
             AND artifact.cache_identity = target.cache_identity
            WHERE target.recording_id = %s
            """,
            (original.id,),
        ).fetchone()["count"]
        job_recording_ids = connection.execute(
            "SELECT DISTINCT recording_id FROM jobs"
        ).fetchall()

    assert len(current) == 1
    assert current[0].id == original.id
    assert current[0].archive_relative_path == "site/day/run"
    assert source is not None
    assert source.archive_relative_path == "site/day/run"
    assert source.identity_recording_id == original.id
    assert source.identity_relative_path == "run"
    assert {str(row["kind"]): str(row["cache_identity"]) for row in targets} == identities
    assert current_ready == 3
    assert job_recording_ids == [{"recording_id": original.id}]


@pytest.mark.postgres
def test_rescan_repairs_one_unambiguous_pre_feature_split_without_file_rewrite(
    postgres_url: str,
    tmp_path: Path,
) -> None:
    archive, recording_root, planner = _planner_archive(tmp_path)
    catalog = CatalogRepository(postgres_url, planner)
    catalog.apply_snapshot(CatalogScanner(archive).scan())
    historical_id = catalog.list_recordings()[0].id
    identities = _insert_current_artifact_history(postgres_url, historical_id)
    with open_connection(postgres_url) as connection:
        connection.execute(
            "UPDATE recordings SET source_present = FALSE WHERE id = %s",
            (historical_id,),
        )

    moved_parent = archive / "site" / "day"
    moved_parent.mkdir(parents=True)
    recording_root.rename(moved_parent / recording_root.name)
    moved_snapshot = CatalogScanner(archive).scan()
    catalog.apply_snapshot(moved_snapshot)
    split_current_id = catalog.list_recordings()[0].id
    assert split_current_id != historical_id

    catalog.apply_snapshot(moved_snapshot)

    current = catalog.list_recordings()[0]
    with open_connection(postgres_url) as connection:
        anchors = connection.execute(
            """
            SELECT cache_identity_recording_id, cache_identity_relative_path
            FROM recordings WHERE id = %s
            """,
            (split_current_id,),
        ).fetchone()
        targets = connection.execute(
            """
            SELECT kind, cache_identity
            FROM preparation_targets
            WHERE recording_id = %s AND target_state = 'available'
            ORDER BY kind
            """,
            (split_current_id,),
        ).fetchall()
        artifact_owners = connection.execute(
            "SELECT DISTINCT recording_id FROM artifacts"
        ).fetchall()
        job_owners = connection.execute(
            "SELECT DISTINCT recording_id FROM jobs"
        ).fetchall()
        matching_ready = connection.execute(
            """
            SELECT count(*) AS count
            FROM preparation_targets AS target
            JOIN artifacts AS artifact
              ON artifact.recording_id = target.recording_id
             AND artifact.kind = target.kind
             AND artifact.cache_identity = target.cache_identity
            WHERE target.recording_id = %s
            """,
            (split_current_id,),
        ).fetchone()["count"]

    assert current.id == split_current_id
    assert anchors == {
        "cache_identity_recording_id": historical_id,
        "cache_identity_relative_path": "run",
    }
    assert {str(row["kind"]): str(row["cache_identity"]) for row in targets} == identities
    assert artifact_owners == [{"recording_id": split_current_id}]
    assert job_owners == [{"recording_id": split_current_id}]
    assert matching_ready == 3


@pytest.mark.postgres
def test_ambiguous_identical_candidates_are_not_merged(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    original_id = catalog.list_recordings()[0].id
    first = _snapshot().recordings[0]

    def at_path(path: str) -> RecordingScanResult:
        return replace(
            first,
            archive_relative_path=path,
            components=tuple(
                replace(
                    component,
                    relative_path=f"{path}/{component.display_name}",
                )
                for component in first.components
            ),
        )

    catalog.apply_snapshot(
        ScanSnapshot(
            (at_path("site/a/run"), at_path("site/b/run")),
            duration_ms=2,
        )
    )

    current = catalog.list_recordings()
    history = catalog.list_recordings(include_missing=True)
    assert len(current) == 2
    assert all(item.id != original_id for item in current)
    assert len(history) == 3
    retained = next(item for item in history if item.id == original_id)
    assert retained.source_present is False


@pytest.mark.postgres
def test_prepare_all_three_preflight_order_and_concurrent_idempotency(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)

    with open_connection(postgres_url) as connection:
        connection.execute(
            """
            UPDATE preparation_targets
            SET target_state = 'unavailable', cache_identity = NULL,
                work_units = NULL, diagnostic_code = 'source_unavailable',
                diagnostic_message = 'The source is unavailable.'
            WHERE recording_id = %s AND kind = 'imu_series'
            """,
            (recording_id,),
        )
    rejected = repository.prepare_recording(recording_id, PLANNER_IDENTITIES)
    assert [item.state for item in rejected.outputs] == [
        "unavailable",
        "unavailable",
        "unavailable",
    ]
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ] == 0

    _make_targets_available(postgres_url, recording_id)
    start = threading.Barrier(2)

    def prepare():
        start.wait()
        return repository.prepare_recording(recording_id, PLANNER_IDENTITIES)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(prepare)
        second_future = executor.submit(prepare)
        first = first_future.result(timeout=10)
        second = second_future.result(timeout=10)

    with open_connection(postgres_url) as connection:
        jobs = connection.execute(
            "SELECT id, kind FROM jobs ORDER BY id"
        ).fetchall()
    assert [row["kind"] for row in jobs] == list(PROCESSING_KINDS)
    assert len(jobs) == 3
    outcomes = [
        [item.outcome for item in result.outputs] for result in (first, second)
    ]
    assert sorted(outcomes) == sorted(
        [["queued", "queued", "queued"], ["active_reused"] * 3]
    )


@pytest.mark.postgres
def test_prepare_transaction_rolls_back_and_is_safely_repeatable(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)
    with open_connection(postgres_url) as connection:
        connection.execute(
            """
            CREATE FUNCTION reject_synthetic_imu_job() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.kind = 'imu_series' THEN
                    RAISE EXCEPTION 'synthetic scheduling failure';
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_synthetic_imu_job
            BEFORE INSERT ON jobs
            FOR EACH ROW EXECUTE FUNCTION reject_synthetic_imu_job()
            """
        )

    try:
        with pytest.raises(psycopg.errors.RaiseException):
            repository.prepare_recording(recording_id, PLANNER_IDENTITIES)
        with open_connection(postgres_url) as connection:
            assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
                "count"
            ] == 0
    finally:
        with open_connection(postgres_url) as connection:
            connection.execute("DROP TRIGGER reject_synthetic_imu_job ON jobs")
            connection.execute("DROP FUNCTION reject_synthetic_imu_job()")

    repeated = repository.prepare_recording(recording_id, PLANNER_IDENTITIES)
    assert [item.outcome for item in repeated.outputs] == ["queued"] * 3
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ] == 3


@pytest.mark.postgres
def test_capacity_admission_creates_no_stale_jobs(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)

    paused = repository.prepare_recording(
        recording_id,
        PLANNER_IDENTITIES,
        admission_diagnostic=SimpleNamespace(
            code="derived_space_low",
            message="New preparation is paused because derived storage is low on space.",
        ),
    )

    assert [output.outcome for output in paused.outputs] == ["unavailable"] * 3
    assert [output.diagnostic_code for output in paused.outputs] == [
        "derived_space_low"
    ] * 3
    with open_connection(postgres_url) as connection:
        assert connection.execute("SELECT count(*) AS count FROM jobs").fetchone()[
            "count"
        ] == 0

    resumed = repository.prepare_recording(recording_id, PLANNER_IDENTITIES)
    assert [output.outcome for output in resumed.outputs] == ["queued"] * 3


@pytest.mark.postgres
def test_retry_failed_attempt_resolves_current_target_identity(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)
    requested = repository.request_job(
        recording_id,
        "front_preview",
        TARGET_IDENTITIES["front_preview"],
        work_units=100,
        estimate_key=PLANNER_IDENTITIES["front_preview"],
    )
    running = repository.claim_next_job()
    assert requested.job is not None and running is not None
    repository.fail_job(running.id, "decode_failed", "Decoding failed.")

    current_identity = "9" * 64
    with open_connection(postgres_url) as connection:
        connection.execute(
            """
            UPDATE preparation_targets
            SET cache_identity = %s
            WHERE recording_id = %s AND kind = 'front_preview'
            """,
            (current_identity, recording_id),
        )
    retry = repository.retry_failed_job(running.id, PLANNER_IDENTITIES)

    assert retry.job_found and retry.job_failed
    assert retry.output is not None
    assert retry.output.outcome == "retry_queued"
    assert retry.output.job is not None
    assert retry.output.job.cache_identity == current_identity
    assert retry.output.job.cache_identity != running.cache_identity


@pytest.mark.postgres
def test_concurrent_claim_is_fifo_and_global_single_running_with_worker_probe(
    postgres_url: str,
) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)
    schedule = repository.prepare_recording(recording_id, PLANNER_IDENTITIES)
    queued_ids = [item.job.id for item in schedule.outputs if item.job is not None]
    assert len(queued_ids) == 3
    start = threading.Barrier(2)

    def claim():
        start.wait()
        return repository.claim_next_job()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            executor.submit(claim),
            executor.submit(claim),
        ]
        claims = [future.result(timeout=10) for future in results]
    claimed = [item for item in claims if item is not None]
    assert len(claimed) == 1
    assert claimed[0].id == queued_ids[0]

    overview = repository.processing_overview(queue_limit=10)
    assert overview.running_count == 1
    assert [item.job.id for item in overview.queue] == queued_ids[1:]
    assert [item.queue_position for item in overview.queue] == [1, 2]
    assert repository.worker_online(WORKER_LOCK_NAME) is False
    assert repository.worker_online(WORKER_LOCK_NAME) is False

    with open_connection(postgres_url) as held_lock:
        held_lock.execute(
            "SELECT pg_advisory_lock(hashtext(%s))", (WORKER_LOCK_NAME,)
        )
        assert repository.worker_online(WORKER_LOCK_NAME) is True
        held_lock.execute(
            "SELECT pg_advisory_unlock(hashtext(%s))", (WORKER_LOCK_NAME,)
        )


@pytest.mark.postgres
def test_claim_freezes_bounded_compatible_median_estimate(postgres_url: str) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    repository = ProcessingRepository(postgres_url)
    estimate_key = "6" * 64
    now = datetime.now(timezone.utc)
    samples = ((100, 1_000), (100, 3_000))
    with open_connection(postgres_url) as connection:
        for index, (work_units, runtime_ms) in enumerate(samples, start=1):
            cache_identity = f"{index:x}" * 64
            started = now - timedelta(minutes=index, milliseconds=runtime_ms)
            finished = started + timedelta(milliseconds=runtime_ms)
            connection.execute(
                """
                INSERT INTO artifacts (
                    recording_id, kind, cache_identity, output_relative_path,
                    mime_type, size_bytes, coverage_start_ns, coverage_end_ns,
                    manifest
                ) VALUES (%s, 'front_preview', %s, %s, 'video/mp4', 10, 0, 1, %s::jsonb)
                """,
                (
                    recording_id,
                    cache_identity,
                    f"front_preview/{index}/preview.mp4",
                    json.dumps({"cache_identity": cache_identity}),
                ),
            )
            connection.execute(
                """
                INSERT INTO jobs (
                    recording_id, kind, cache_identity, state, queued_at,
                    started_at, finished_at, work_units, estimate_key
                ) VALUES (
                    %s, 'front_preview', %s, 'succeeded', %s, %s, %s, %s, %s
                )
                """,
                (
                    recording_id,
                    cache_identity,
                    started,
                    started,
                    finished,
                    work_units,
                    estimate_key,
                ),
            )

    request = repository.request_job(
        recording_id,
        "front_preview",
        "f" * 64,
        work_units=200,
        estimate_key=estimate_key,
    )
    claimed = repository.claim_next_job()
    assert request.job is not None and claimed is not None
    assert claimed.estimated_total_ms == 4_000
    assert claimed.estimate_method == "median_rate_v1"
    assert claimed.estimate_sample_count == 2
    with open_connection(postgres_url) as connection:
        frozen = connection.execute(
            """
            SELECT estimated_total_ms, estimate_method, estimate_sample_count
            FROM jobs WHERE id = %s
            """,
            (claimed.id,),
        ).fetchone()
    assert frozen == {
        "estimated_total_ms": 4_000,
        "estimate_method": "median_rate_v1",
        "estimate_sample_count": 2,
    }


@pytest.mark.postgres
def test_actionable_failures_history_join_and_stable_cursor(postgres_url: str) -> None:
    catalog = CatalogRepository(postgres_url)
    catalog.apply_snapshot(_snapshot())
    recording_id = catalog.list_recordings()[0].id
    _make_targets_available(postgres_url, recording_id)
    repository = ProcessingRepository(postgres_url)

    requested = repository.request_job(
        recording_id, "front_preview", TARGET_IDENTITIES["front_preview"]
    )
    failed = repository.claim_next_job()
    assert requested.job is not None and failed is not None
    repository.fail_job(failed.id, "decode_failed", "Decoding failed.")
    actionable = repository.list_processing_jobs("failed", limit=10)
    assert [item.job.id for item in actionable] == [failed.id]

    retry = repository.retry_failed_job(failed.id, PLANNER_IDENTITIES)
    assert retry.output is not None and retry.output.job is not None
    assert repository.list_processing_jobs("failed", limit=10) == ()
    rerun = repository.claim_next_job()
    assert rerun is not None
    ready = repository.complete_job(
        rerun.id,
        ArtifactWrite(
            recording_id=recording_id,
            kind="front_preview",
            cache_identity=TARGET_IDENTITIES["front_preview"],
            output_relative_path="front_preview/current/preview.mp4",
            mime_type="video/mp4",
            size_bytes=321,
            coverage_start_ns=0,
            coverage_end_ns=1,
            manifest={"cache_identity": TARGET_IDENTITIES["front_preview"]},
        ),
    )
    history = repository.list_processing_jobs("history", limit=10)
    current = next(item for item in history if item.job.id == rerun.id)
    assert current.output_size_bytes == ready.size_bytes == 321

    now = datetime.now(timezone.utc)
    inserted_ids: list[int] = []
    with open_connection(postgres_url) as connection:
        for index, seconds_ago in enumerate((10, 20), start=4):
            cache_identity = f"{index:x}" * 64
            finished = now - timedelta(seconds=seconds_ago)
            started = finished - timedelta(seconds=1)
            artifact_row = connection.execute(
                """
                INSERT INTO artifacts (
                    recording_id, kind, cache_identity, output_relative_path,
                    mime_type, size_bytes, coverage_start_ns, coverage_end_ns,
                    manifest
                ) VALUES (%s, 'imu_series', %s, %s, 'application/json', %s, 0, 1, %s::jsonb)
                RETURNING id
                """,
                (
                    recording_id,
                    cache_identity,
                    f"imu_series/{index}/series.json",
                    index * 100,
                    json.dumps({"cache_identity": cache_identity}),
                ),
            ).fetchone()
            assert artifact_row is not None
            row = connection.execute(
                """
                INSERT INTO jobs (
                    recording_id, kind, cache_identity, state, queued_at,
                    started_at, finished_at
                ) VALUES (%s, 'imu_series', %s, 'succeeded', %s, %s, %s)
                RETURNING id
                """,
                (recording_id, cache_identity, started, started, finished),
            ).fetchone()
            inserted_ids.append(int(row["id"]))

    first_page = repository.list_processing_jobs("history", limit=2)
    assert len(first_page) == 2
    cursor_job = first_page[-1].job
    assert cursor_job.finished_at is not None

    with open_connection(postgres_url) as connection:
        newer_identity = "8" * 64
        connection.execute(
            """
            INSERT INTO artifacts (
                recording_id, kind, cache_identity, output_relative_path,
                mime_type, size_bytes, coverage_start_ns, coverage_end_ns,
                manifest
            ) VALUES (%s, 'topdown_preview', %s, 'topdown/new/preview.mp4',
                      'video/mp4', 800, 0, 1, %s::jsonb)
            """,
            (
                recording_id,
                newer_identity,
                json.dumps({"cache_identity": newer_identity}),
            ),
        )
        connection.execute(
            """
            INSERT INTO jobs (
                recording_id, kind, cache_identity, state, queued_at,
                started_at, finished_at
            ) VALUES (%s, 'topdown_preview', %s, 'succeeded', %s, %s, %s)
            """,
            (
                recording_id,
                newer_identity,
                now + timedelta(seconds=1),
                now + timedelta(seconds=1),
                now + timedelta(seconds=2),
            ),
        )

    second_page = repository.list_processing_jobs(
        "history",
        limit=10,
        cursor=(cursor_job.finished_at, cursor_job.id),
    )
    second_ids = [item.job.id for item in second_page]
    assert inserted_ids[-1] in second_ids
    assert all(item.job.finished_at < cursor_job.finished_at for item in second_page)


@pytest.mark.postgres
def test_maximum_synthetic_catalog_bulk_queries_and_response_are_bounded(
    postgres_url: str,
) -> None:
    with open_connection(postgres_url) as connection:
        connection.execute(
            """
            INSERT INTO recordings (
                id, archive_relative_path, display_name, start_time_ns,
                duration_ns, total_source_size_bytes, storage_format,
                metadata_version, message_count, topic_count, ros_health,
                source_revision, source_present, last_seen_generation,
                cache_identity_recording_id,
                cache_identity_relative_path
            )
            OVERRIDING SYSTEM VALUE
            SELECT value,
                   'nested/day/' || lpad(value::text, 5, '0'),
                   'run-' || lpad(value::text, 5, '0'),
                   1700000000000000000 + value,
                   2500000000,
                   1000000 + value,
                   'sqlite3', 5, 100, 3, 'readable',
                   md5(value::text) || md5(value::text), TRUE, 1,
                   value,
                   'nested/day/' || lpad(value::text, 5, '0')
            FROM generate_series(1, 5000) AS value
            """
        )
        connection.execute(
            """
            INSERT INTO preparation_targets (
                recording_id, kind, scan_generation, planner_identity,
                target_state, cache_identity, work_units
            )
            SELECT recording.id,
                   kind.value,
                   1,
                   CASE kind.value
                       WHEN 'front_preview' THEN %s
                       WHEN 'topdown_preview' THEN %s
                       ELSE %s
                   END,
                   'available',
                   md5(kind.value || recording.id::text)
                       || md5(kind.value || recording.id::text),
                   1000 + recording.id
            FROM recordings AS recording
            CROSS JOIN (
                VALUES ('front_preview'), ('topdown_preview'), ('imu_series')
            ) AS kind(value)
            """,
            (
                PLANNER_IDENTITIES["front_preview"],
                PLANNER_IDENTITIES["topdown_preview"],
                PLANNER_IDENTITIES["imu_series"],
            ),
        )
        connection.execute(
            """
            UPDATE catalog_state
            SET successful_generation = 1,
                successful_completed_at = CURRENT_TIMESTAMP,
                duration_ms = 250,
                recording_count = 5000,
                readable_count = 5000
            WHERE singleton = TRUE
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (recording_id, kind, cache_identity, state)
            SELECT target.recording_id, target.kind, target.cache_identity, 'queued'
            FROM preparation_targets AS target
            WHERE target.kind = 'front_preview'
              AND target.recording_id <= 1000
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (
                recording_id, kind, cache_identity, state,
                started_at, finished_at, error_code, error_message
            )
            SELECT target.recording_id, target.kind, target.cache_identity, 'failed',
                   CURRENT_TIMESTAMP - interval '2 seconds', CURRENT_TIMESTAMP,
                   'synthetic_failure', 'Synthetic bounded-query fixture failure.'
            FROM preparation_targets AS target
            WHERE target.kind = 'imu_series'
              AND target.recording_id BETWEEN 1001 AND 2000
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (
                recording_id, kind, cache_identity, state,
                started_at, finished_at
            )
            SELECT target.recording_id, target.kind, target.cache_identity, 'succeeded',
                   CURRENT_TIMESTAMP - interval '3 seconds', CURRENT_TIMESTAMP
            FROM preparation_targets AS target
            WHERE target.kind = 'topdown_preview'
              AND target.recording_id BETWEEN 2001 AND 3000
            """
        )
        connection.execute(
            """
            INSERT INTO jobs (
                recording_id, kind, cache_identity, state, started_at
            )
            SELECT target.recording_id, target.kind, target.cache_identity,
                   'running', CURRENT_TIMESTAMP - interval '1 second'
            FROM preparation_targets AS target
            WHERE target.kind = 'front_preview' AND target.recording_id = 1001
            """
        )

    class Planner:
        planner_identities = PLANNER_IDENTITIES

        def planner_identity(self, kind: str) -> str:
            return self.planner_identities[kind]

    catalog_repository = CatalogRepository(postgres_url)
    processing_repository = ProcessingRepository(postgres_url)
    preparation = PreparationService(
        catalog_repository,
        processing_repository,
        Planner(),  # type: ignore[arg-type]
        {},
    )
    service = V1CatalogService(
        catalog_repository,
        preparation,
        max_recordings=5000,
    )

    catalog_started = perf_counter()
    view = service.get_catalog()
    encoded = catalog_response(view).model_dump_json()
    catalog_ms = int((perf_counter() - catalog_started) * 1000)
    processing_started = perf_counter()
    overview = processing_repository.processing_overview(queue_limit=20)
    failures = processing_repository.list_processing_jobs("failed", limit=100)
    history = processing_repository.list_processing_jobs("history", limit=100)
    processing_ms = int((perf_counter() - processing_started) * 1000)

    assert len(view.recordings) == 5000
    assert sum(len(item.analysis.outputs) for item in view.recordings) == 15000
    assert len(encoded.encode("utf-8")) < 8 * 1024 * 1024
    assert overview.running_count == 1
    assert overview.queued_count == 1000
    assert overview.failed_count == 1000
    assert overview.succeeded_count == 1000
    assert len(failures) == 100
    assert len(history) == 100
    print(
        "V1 maximum synthetic catalog: "
        f"catalog={catalog_ms}ms, processing={processing_ms}ms, "
        f"response={len(encoded.encode('utf-8'))} bytes"
    )


@pytest.mark.postgres
@pytest.mark.anyio
async def test_v1_nested_synthetic_operational_acceptance(
    postgres_url: str,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    nested = archive / "site" / "day"
    nested.mkdir(parents=True)
    recording_roots = {
        "ready": create_recording(nested, "ready-run"),
        "new": create_recording(nested, "new-run"),
        "failed": create_recording(nested, "failed-run"),
        "unavailable": create_recording(
            nested, "unavailable-run", include_video=False
        ),
    }
    for recording_root in recording_roots.values():
        metadata_path = recording_root / "metadata.yaml"
        document = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        information = document["rosbag2_bagfile_information"]
        information["message_count"] = 84
        information["topics_with_message_count"].append(
            {
                "topic_metadata": {
                    "name": "/imu/data",
                    "type": "sensor_msgs/msg/Imu",
                    "serialization_format": "cdr",
                    "offered_qos_profiles": "",
                },
                "message_count": 42,
            }
        )
        metadata_path.write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
        )

    planner = PreparationPlanner(
        front_topic="/camera/image_raw",
        imu_topic="/imu/data",
        imu_component="angular_velocity.z",
        profile=V0_PREVIEW_PROFILE,
        encoder_identity="synthetic-encoder",
    )
    catalog_repository = CatalogRepository(postgres_url, planner)
    processing_repository = ProcessingRepository(postgres_url)
    catalog_service = CatalogService(
        CatalogScanner(archive),
        catalog_repository,
    )

    class SyntheticArtifactStore:
        def validate_media(self, *args) -> None:
            return None

        def validate_series_artifact(self, *args) -> None:
            return None

    stores = {kind: SyntheticArtifactStore() for kind in PROCESSING_KINDS}
    preparation_service = PreparationService(
        catalog_repository,
        processing_repository,
        planner,
        stores,  # type: ignore[arg-type]
    )
    v1_catalog_service = V1CatalogService(
        catalog_repository,
        preparation_service,
        max_recordings=100,
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
    )

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            rescan = await client.post("/api/v1/catalog/rescan")
            assert rescan.status_code == 200
            initial = await client.get("/api/v1/catalog")
            by_name = {
                item["name"]: item for item in initial.json()["recordings"]
            }
            assert initial.json()["folders"] == [
                {
                    "path": "site",
                    "parent_path": "",
                    "name": "site",
                    "direct_recording_count": 0,
                    "descendant_recording_count": 4,
                },
                {
                    "path": "site/day",
                    "parent_path": "site",
                    "name": "day",
                    "direct_recording_count": 4,
                    "descendant_recording_count": 4,
                },
            ]

            ids = {name: by_name[f"{name}-run"]["id"] for name in recording_roots}
            with open_connection(postgres_url) as connection:
                target_rows = connection.execute(
                    """
                    SELECT target.recording_id, target.kind, target.cache_identity,
                           target.work_units, target.planner_identity
                    FROM preparation_targets AS target
                    WHERE target.target_state = 'available'
                    ORDER BY target.recording_id, target.kind
                    """
                ).fetchall()
                targets = {
                    (int(row["recording_id"]), str(row["kind"])): row
                    for row in target_rows
                }
                for kind in PROCESSING_KINDS:
                    target = targets[(ids["ready"], kind)]
                    cache_identity = str(target["cache_identity"])
                    connection.execute(
                        """
                        INSERT INTO artifacts (
                            recording_id, kind, cache_identity,
                            output_relative_path, mime_type, size_bytes,
                            coverage_start_ns, coverage_end_ns, manifest
                        ) VALUES (%s, %s, %s, %s, %s, 100, 0, 1000, %s::jsonb)
                        """,
                        (
                            ids["ready"],
                            kind,
                            cache_identity,
                            f"{kind}/synthetic/output",
                            "application/json"
                            if kind == "imu_series"
                            else "video/mp4",
                            json.dumps(
                                {
                                    "cache_identity": cache_identity,
                                    "timing": {
                                        "timestamp_provenance": (
                                            "csv_unix_timestamp"
                                            if kind == "topdown_preview"
                                            else "ros_record_timestamp"
                                        )
                                    },
                                }
                            ),
                        ),
                    )
                front = targets[(ids["ready"], "front_preview")]
                for seconds in (1, 3):
                    connection.execute(
                        """
                        INSERT INTO jobs (
                            recording_id, kind, cache_identity, state,
                            queued_at, started_at, finished_at,
                            work_units, estimate_key
                        ) VALUES (
                            %s, 'front_preview', %s, 'succeeded',
                            CURRENT_TIMESTAMP - make_interval(secs => %s),
                            CURRENT_TIMESTAMP - make_interval(secs => %s),
                            CURRENT_TIMESTAMP, 100, %s
                        )
                        """,
                        (
                            ids["ready"],
                            front["cache_identity"],
                            seconds,
                            seconds,
                            front["planner_identity"],
                        ),
                    )
                for kind in PROCESSING_KINDS:
                    target = targets[(ids["failed"], kind)]
                    connection.execute(
                        """
                        INSERT INTO jobs (
                            recording_id, kind, cache_identity, state,
                            started_at, finished_at, error_code, error_message,
                            work_units, estimate_key
                        ) VALUES (
                            %s, %s, %s, 'failed',
                            CURRENT_TIMESTAMP - interval '1 second',
                            CURRENT_TIMESTAMP, 'synthetic_failure',
                            'Synthetic acceptance failure.', %s, %s
                        )
                        """,
                        (
                            ids["failed"],
                            kind,
                            target["cache_identity"],
                            target["work_units"],
                            target["planner_identity"],
                        ),
                    )

            mixed = await client.get("/api/v1/catalog")
            mixed_by_name = {
                item["name"]: item for item in mixed.json()["recordings"]
            }
            assert mixed_by_name["ready-run"]["analysis_state"] == "ready"
            assert mixed_by_name["failed-run"]["analysis_state"] == "failed"
            assert mixed_by_name["new-run"]["analysis_state"] == "not_planned"
            assert (
                mixed_by_name["unavailable-run"]["analysis_state"]
                == "not_planned"
            )
            paused = await client.get("/api/v1/processing/overview")
            assert paused.json()["worker_online"] is False
            assert paused.json()["failed_count"] == 3
            assert paused.json()["succeeded_count"] == 2

            selected_ids = [
                ids["ready"],
                ids["new"],
                ids["failed"],
                ids["unavailable"],
            ]
            prepared = await client.post(
                "/api/v1/recordings/prepare",
                json={"recording_ids": selected_ids},
            )
            assert prepared.status_code == 202
            prepared_rows = prepared.json()["recordings"]
            assert [item["recording_id"] for item in prepared_rows] == selected_ids
            assert [item["outcome"] for item in prepared_rows[0]["outputs"]] == [
                "ready_reused"
            ] * 3
            assert [item["outcome"] for item in prepared_rows[1]["outputs"]] == [
                "queued"
            ] * 3
            assert [item["outcome"] for item in prepared_rows[2]["outputs"]] == [
                "retry_queued"
            ] * 3
            assert [item["outcome"] for item in prepared_rows[3]["outputs"]] == [
                "unavailable"
            ] * 3

            queue = await client.get("/api/v1/processing/jobs?view=queued&limit=20")
            assert [item["queue_position"] for item in queue.json()["items"]] == list(
                range(1, 7)
            )
            running = processing_repository.claim_next_job()
            assert running is not None
            active_started = perf_counter()
            active = await client.get("/api/v1/processing/overview")
            active_ms = int((perf_counter() - active_started) * 1000)
            assert active_ms < 2_000
            assert active.json()["current"]["id"] == running.id
            assert active.json()["current"]["elapsed_ms"] >= 0
            assert active.json()["current"]["estimate"]["status"] == "available"

            with open_connection(postgres_url) as connection:
                connection.execute(
                    """
                    UPDATE jobs
                    SET started_at = %s
                    WHERE id = %s
                    """,
                    (
                        datetime.now(timezone.utc)
                        - timedelta(
                            milliseconds=(running.estimated_total_ms or 0) + 100
                        ),
                        running.id,
                    ),
                )
            exceeded = await client.get("/api/v1/processing/overview")
            assert exceeded.json()["current"]["estimate"]["status"] == "exceeded"
            assert exceeded.json()["current"]["estimate"]["remaining_ms"] is None
            processing_repository.fail_job(
                running.id, "synthetic_processing_failed", "Synthetic failure."
            )
            retry = await client.post(
                f"/api/v1/processing/jobs/{running.id}/retry"
            )
            assert retry.status_code == 202
            assert retry.json()["outcome"] == "retry_queued"

            (archive / "unsafe\\branch").mkdir()
            incomplete = await client.post("/api/v1/catalog/rescan")
            retained = await client.get("/api/v1/catalog")
            assert incomplete.status_code == 503
            assert retained.status_code == 200
            assert retained.json()["scan"]["generation"] == 1
            assert len(retained.json()["recordings"]) == 4

    restarted_catalog = V1CatalogService(
        CatalogRepository(postgres_url),
        PreparationService(
            CatalogRepository(postgres_url),
            ProcessingRepository(postgres_url),
            planner,
            stores,  # type: ignore[arg-type]
        ),
        max_recordings=100,
    ).get_catalog()
    assert restarted_catalog.scan.successful_generation == 1
    assert len(restarted_catalog.recordings) == 4
