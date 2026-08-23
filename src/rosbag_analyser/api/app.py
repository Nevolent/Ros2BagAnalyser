from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Path as PathParameter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn

from rosbag_analyser.artifact_store import ArtifactStore
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.config import AppConfig
from rosbag_analyser.deployment import (
    DeploymentSettings,
    build_admission_guard,
    validate_startup_mounts,
)
from rosbag_analyser.front_preview import (
    FrontPreviewService,
    FrontSourceResolver,
    encoder_identity,
)
from rosbag_analyser.imu_series import ImuSeriesService, ImuSourceResolver
from rosbag_analyser.health import ApplicationHealthService, HealthService
from rosbag_analyser.persistence.database import validate_catalog_schema
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.processing_repository import ProcessingRepository
from rosbag_analyser.preparation import PreparationService
from rosbag_analyser.preparation_planner import PreparationPlanner
from rosbag_analyser.persistence.processing_repository import (
    FRONT_PREVIEW_KIND,
    IMU_SERIES_KIND,
    TOPDOWN_PREVIEW_KIND,
    WORKER_LOCK_NAME,
)
from rosbag_analyser.processing_view import ProcessingViewService
from rosbag_analyser.safe_logging import configure_safe_logging
from rosbag_analyser.topdown_preview import (
    TopdownPreviewService,
    TopdownSourceResolver,
)
from rosbag_analyser.v1_catalog import V1CatalogService

from .catalog_routes import router as catalog_router
from .front_preview_routes import router as front_preview_router
from .imu_series_routes import router as imu_series_router
from .topdown_preview_routes import router as topdown_preview_router
from .v1_routes import router as v1_router


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
INDEX_HTML = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
APP_JAVASCRIPT = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
IMU_GRAPH_JAVASCRIPT = (WEB_ROOT / "imu_graph.js").read_text(encoding="utf-8")
STYLESHEET = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
TECH_TRACE_ICON = (WEB_ROOT / "assets" / "tech-trace-icon.svg").read_text(
    encoding="utf-8"
)
FRONTEND_RESPONSE_HEADERS = {"Cache-Control": "no-store"}


def create_app(
    service: CatalogService | None = None,
    front_preview_service: FrontPreviewService | None = None,
    topdown_preview_service: TopdownPreviewService | None = None,
    imu_series_service: ImuSeriesService | None = None,
    v1_catalog_service: V1CatalogService | None = None,
    preparation_service: PreparationService | None = None,
    processing_view_service: ProcessingViewService | None = None,
    prepare_max_recordings: int = 100,
    health_service: HealthService | None = None,
) -> FastAPI:
    bootstrap_deployment = DeploymentSettings.from_environment()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if service is None:
            config = AppConfig.from_environment()
            deployment = DeploymentSettings.from_environment()
            admission_guard = build_admission_guard(
                config.archive_root,
                config.derived_root,
                deployment,
            )
            validate_startup_mounts(deployment, admission_guard)
            media_encoder_identity = encoder_identity()
            preparation_planner = PreparationPlanner(
                front_topic=config.front_topic,
                imu_topic=config.imu_topic,
                imu_component=config.imu_component,
                profile=config.preview_profile,
                encoder_identity=media_encoder_identity,
            )
            catalog_repository = CatalogRepository(
                config.database_url, preparation_planner
            )
            application.state.catalog_service = CatalogService(
                CatalogScanner(
                    config.archive_root,
                    limits=config.catalog_scan_limits,
                ),
                catalog_repository,
            )
            processing_repository = ProcessingRepository(config.database_url)
            application.state.preparation_planner = preparation_planner
            application.state.processing_repository = processing_repository
            application.state.app_config = config
            artifact_store = ArtifactStore(
                config.derived_root, config.ffmpeg_path, config.ffprobe_path
            )
            application.state.front_preview_service = FrontPreviewService(
                FrontSourceResolver(
                    config.archive_root,
                    processing_repository,
                    config.front_topic,
                    config.preview_profile,
                    media_encoder_identity,
                ),
                processing_repository,
                artifact_store,
            )
            topdown_artifact_store = ArtifactStore(
                config.derived_root,
                config.ffmpeg_path,
                config.ffprobe_path,
                TOPDOWN_PREVIEW_KIND,
            )
            application.state.topdown_preview_service = TopdownPreviewService(
                TopdownSourceResolver(
                    config.archive_root,
                    processing_repository,
                    config.preview_profile,
                    media_encoder_identity,
                ),
                processing_repository,
                topdown_artifact_store,
            )
            imu_artifact_store = ArtifactStore(
                config.derived_root,
                config.ffmpeg_path,
                config.ffprobe_path,
                IMU_SERIES_KIND,
            )
            application.state.imu_series_service = ImuSeriesService(
                ImuSourceResolver(
                    config.archive_root,
                    processing_repository,
                    config.imu_topic,
                    config.imu_component,
                ),
                processing_repository,
                imu_artifact_store,
            )
            application.state.preparation_service = PreparationService(
                catalog_repository,
                processing_repository,
                preparation_planner,
                {
                    FRONT_PREVIEW_KIND: artifact_store,
                    TOPDOWN_PREVIEW_KIND: topdown_artifact_store,
                    IMU_SERIES_KIND: imu_artifact_store,
                },
                admission_check=admission_guard.diagnostic,
            )
            application.state.v1_catalog_service = V1CatalogService(
                catalog_repository,
                application.state.preparation_service,
                max_recordings=config.catalog_scan_limits.max_recordings,
            )
            application.state.processing_view_service = ProcessingViewService(
                processing_repository,
                preparation_planner,
                worker_lock_name=WORKER_LOCK_NAME,
                admission_check=admission_guard.diagnostic,
            )
            application.state.prepare_max_recordings = config.prepare_max_recordings
            application.state.admission_guard = admission_guard
            application.state.health_service = ApplicationHealthService(
                deployment.release_id,
                database_check=lambda: validate_catalog_schema(config.database_url),
                admission_guard=admission_guard,
                worker_online=lambda: processing_repository.worker_online(
                    WORKER_LOCK_NAME
                ),
            )
        else:
            application.state.catalog_service = service
            if front_preview_service is not None:
                application.state.front_preview_service = front_preview_service
            if topdown_preview_service is not None:
                application.state.topdown_preview_service = topdown_preview_service
            if imu_series_service is not None:
                application.state.imu_series_service = imu_series_service
            if v1_catalog_service is not None:
                application.state.v1_catalog_service = v1_catalog_service
            if preparation_service is not None:
                application.state.preparation_service = preparation_service
            if processing_view_service is not None:
                application.state.processing_view_service = processing_view_service
            application.state.prepare_max_recordings = prepare_max_recordings
            application.state.health_service = health_service or HealthService(
                "development"
            )
            application.state.admission_guard = None
        # These pools keep bounded catalog calls off the event loop while reserving
        # read capacity when a scan is active. They are not artifact workers.
        application.state.catalog_read_executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="catalog-read",
        )
        application.state.catalog_scan_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="catalog-scan",
        )
        # Ready media is delivered in bounded chunks. This executor is only for
        # derived-file reads and is separate from the serial processing worker.
        application.state.media_read_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="media-read",
        )
        try:
            yield
        finally:
            application.state.media_read_executor.shutdown(
                wait=True,
                cancel_futures=True,
            )
            application.state.catalog_scan_executor.shutdown(
                wait=True,
                cancel_futures=True,
            )
            application.state.catalog_read_executor.shutdown(
                wait=True,
                cancel_futures=True,
            )

    application = FastAPI(
        title="ROS 2 Bag Analyser",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if bootstrap_deployment.enabled else "/docs",
        redoc_url=None if bootstrap_deployment.enabled else "/redoc",
        openapi_url=None if bootstrap_deployment.enabled else "/openapi.json",
    )
    application.include_router(catalog_router)
    application.include_router(front_preview_router)
    application.include_router(topdown_preview_router)
    application.include_router(imu_series_router)
    application.include_router(v1_router)

    @application.exception_handler(RequestValidationError)
    async def bounded_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del request, error
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "request_validation_failed",
                    "message": "The request parameters or body were invalid.",
                }
            },
        )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; media-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @application.get("/health/live", include_in_schema=False)
    async def health_live() -> JSONResponse:
        return JSONResponse(application.state.health_service.liveness())

    @application.get("/health/ready", include_in_schema=False)
    async def health_ready() -> JSONResponse:
        report = application.state.health_service.readiness()
        return JSONResponse(
            report.as_dict(),
            status_code=200 if report.ready else 503,
        )

    @application.get("/", include_in_schema=False)
    async def archive_page() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML, headers=FRONTEND_RESPONSE_HEADERS)

    @application.get("/processing", include_in_schema=False)
    async def processing_page() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML, headers=FRONTEND_RESPONSE_HEADERS)

    @application.get("/recordings/{recording_id:int}", include_in_schema=False)
    async def recording_page(
        recording_id: Annotated[int, PathParameter(gt=0)],
    ) -> HTMLResponse:
        return HTMLResponse(INDEX_HTML, headers=FRONTEND_RESPONSE_HEADERS)

    @application.get("/app.js", include_in_schema=False)
    async def browser_script() -> Response:
        return Response(
            APP_JAVASCRIPT,
            media_type="text/javascript",
            headers=FRONTEND_RESPONSE_HEADERS,
        )

    @application.get("/imu_graph.js", include_in_schema=False)
    async def imu_graph_script() -> Response:
        return Response(
            IMU_GRAPH_JAVASCRIPT,
            media_type="text/javascript",
            headers=FRONTEND_RESPONSE_HEADERS,
        )

    @application.get("/styles.css", include_in_schema=False)
    async def browser_styles() -> Response:
        return Response(
            STYLESHEET,
            media_type="text/css",
            headers=FRONTEND_RESPONSE_HEADERS,
        )

    @application.get("/assets/tech-trace-icon.svg", include_in_schema=False)
    async def browser_icon() -> Response:
        return Response(
            TECH_TRACE_ICON,
            media_type="image/svg+xml",
            headers=FRONTEND_RESPONSE_HEADERS,
        )

    return application


app = create_app()


def main() -> None:
    configure_safe_logging()
    deployment = DeploymentSettings.from_environment()
    uvicorn.run(
        "rosbag_analyser.api.app:app",
        host=deployment.bind_host,
        port=deployment.bind_port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()
