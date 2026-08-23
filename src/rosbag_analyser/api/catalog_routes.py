from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import logging
from typing import Annotated, TypeVar

from fastapi import (
    APIRouter,
    HTTPException,
    Path as PathParameter,
    Request,
    status,
)
import psycopg

from rosbag_analyser.catalog.service import CatalogService
from rosbag_analyser.catalog.types import RootScanError

from .schemas import (
    RecordingDetailResponse,
    RecordingListResponse,
    RescanResponse,
    recording_detail_response,
    recording_list_response,
    rescan_response,
)


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)
Result = TypeVar("Result")


def _service(request: Request) -> CatalogService:
    return request.app.state.catalog_service


@router.post("/catalog/rescan", response_model=RescanResponse)
async def rescan_catalog(request: Request) -> RescanResponse:
    _require_source_capability(request)
    try:
        result = await _run_catalog_call(
            request,
            _service(request).rescan,
            executor=request.app.state.catalog_scan_executor,
        )
    except RootScanError as error:
        logger.warning(
            "Catalog root scan failed with code %s.",
            error.diagnostic.code,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": error.diagnostic.code,
                "message": error.diagnostic.message,
            },
        ) from error
    except psycopg.Error as error:
        raise _catalog_database_error("rescan", error) from error
    return rescan_response(result)


def _require_source_capability(request: Request) -> None:
    guard = getattr(request.app.state, "admission_guard", None)
    if guard is None:
        return
    diagnostic = guard.source_diagnostic()
    if diagnostic is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": diagnostic.code, "message": diagnostic.message},
        )


@router.get("/recordings", response_model=RecordingListResponse)
async def list_recordings(request: Request) -> RecordingListResponse:
    try:
        recordings = await _run_catalog_call(
            request, _service(request).list_recordings
        )
    except psycopg.Error as error:
        raise _catalog_database_error("list recordings", error) from error
    return recording_list_response(recordings)


@router.get("/recordings/{recording_id:int}", response_model=RecordingDetailResponse)
async def get_recording(
    recording_id: Annotated[int, PathParameter(gt=0)], request: Request
) -> RecordingDetailResponse:
    try:
        detail = await _run_catalog_call(
            request,
            lambda: _service(request).get_recording(recording_id),
        )
    except psycopg.Error as error:
        raise _catalog_database_error("get recording detail", error) from error
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
    return recording_detail_response(detail)


async def _run_catalog_call(
    request: Request,
    operation: Callable[[], Result],
    *,
    executor: ThreadPoolExecutor | None = None,
) -> Result:
    selected_executor = executor or request.app.state.catalog_read_executor
    future = selected_executor.submit(operation)
    try:
        # Polling keeps cancellation and response handling on the event loop while
        # the synchronous scanner or PostgreSQL call runs in the request pool.
        while not future.done():
            await asyncio.sleep(0.01)
        return future.result()
    except BaseException:
        future.cancel()
        raise


def _catalog_database_error(operation: str, error: psycopg.Error) -> HTTPException:
    if isinstance(error, psycopg.OperationalError):
        logger.warning(
            "Catalog database unavailable during %s.", operation, exc_info=True
        )
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "catalog_database_unavailable",
                "message": "The catalog database is currently unavailable.",
            },
        )

    logger.error(
        "Catalog database operation failed during %s.", operation, exc_info=True
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "catalog_operation_failed",
            "message": "The catalog operation could not be completed.",
        },
    )
