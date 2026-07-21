from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Path as PathParameter, Request
from fastapi.responses import HTMLResponse, Response
import uvicorn

from rosbag_analyser.artifact_store import ArtifactStore
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.config import AppConfig
from rosbag_analyser.front_preview import (
    FrontPreviewService,
    FrontSourceResolver,
    encoder_identity,
)
from rosbag_analyser.persistence.catalog_repository import CatalogRepository
from rosbag_analyser.persistence.processing_repository import ProcessingRepository

from .catalog_routes import router as catalog_router
from .front_preview_routes import router as front_preview_router


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
INDEX_HTML = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
APP_JAVASCRIPT = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
STYLESHEET = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")


def create_app(
    service: CatalogService | None = None,
    front_preview_service: FrontPreviewService | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if service is None:
            config = AppConfig.from_environment()
            application.state.catalog_service = CatalogService(
                CatalogScanner(config.archive_root),
                CatalogRepository(config.database_url),
            )
            processing_repository = ProcessingRepository(config.database_url)
            artifact_store = ArtifactStore(
                config.derived_root, config.ffmpeg_path, config.ffprobe_path
            )
            application.state.front_preview_service = FrontPreviewService(
                FrontSourceResolver(
                    config.archive_root,
                    processing_repository,
                    config.front_topic,
                    config.preview_profile,
                    encoder_identity(),
                ),
                processing_repository,
                artifact_store,
            )
        else:
            application.state.catalog_service = service
            if front_preview_service is not None:
                application.state.front_preview_service = front_preview_service
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
    )
    application.include_router(catalog_router)
    application.include_router(front_preview_router)

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

    @application.get("/", include_in_schema=False)
    async def archive_page() -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    @application.get("/recordings/{recording_id:int}", include_in_schema=False)
    async def recording_page(
        recording_id: Annotated[int, PathParameter(gt=0)],
    ) -> HTMLResponse:
        return HTMLResponse(INDEX_HTML)

    @application.get("/app.js", include_in_schema=False)
    async def browser_script() -> Response:
        return Response(APP_JAVASCRIPT, media_type="text/javascript")

    @application.get("/styles.css", include_in_schema=False)
    async def browser_styles() -> Response:
        return Response(STYLESHEET, media_type="text/css")

    return application


app = create_app()


def main() -> None:
    uvicorn.run(
        "rosbag_analyser.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
