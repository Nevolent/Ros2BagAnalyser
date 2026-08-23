from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
import psycopg

from rosbag_analyser.catalog.types import RootScanError
from rosbag_analyser.processing_view import InvalidProcessingCursor

from .catalog_routes import _require_source_capability, _run_catalog_call
from .v1_schemas import (
    CatalogResponse,
    PrepareSelectedRequest,
    PrepareSelectedResponse,
    ProcessingJobsResponse,
    ProcessingOverviewResponse,
    RecordingDetailResponse,
    RescanResponse,
    RetryResponse,
    catalog_response,
    prepare_response,
    processing_jobs_response,
    processing_overview_response,
    recording_detail_response,
    rescan_response,
    retry_response,
)


router = APIRouter(prefix="/api/v1")
logger = logging.getLogger(__name__)


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(request: Request) -> CatalogResponse:
    view = await _database_call(
        request,
        "load V1 catalog",
        request.app.state.v1_catalog_service.get_catalog,
    )
    return catalog_response(view)


@router.post("/catalog/rescan", response_model=RescanResponse)
async def rescan_catalog(request: Request) -> RescanResponse:
    _require_source_capability(request)
    try:
        result = await _run_catalog_call(
            request,
            request.app.state.catalog_service.rescan,
            executor=request.app.state.catalog_scan_executor,
        )
    except RootScanError as error:
        logger.warning(
            "V1 catalog scan failed with code %s.",
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
        raise _database_error("rescan V1 catalog", error) from error
    return rescan_response(result)


@router.get("/recordings/{recording_id:int}", response_model=RecordingDetailResponse)
async def get_recording(
    recording_id: Annotated[int, Path(gt=0)], request: Request
) -> RecordingDetailResponse:
    detail = await _database_call(
        request,
        "load V1 recording detail",
        lambda: request.app.state.v1_catalog_service.get_recording(recording_id),
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
    return recording_detail_response(detail)


@router.post("/recordings/prepare", response_model=PrepareSelectedResponse)
async def prepare_selected(
    body: PrepareSelectedRequest,
    request: Request,
    response: Response,
) -> PrepareSelectedResponse:
    maximum = request.app.state.prepare_max_recordings
    if len(body.recording_ids) > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "preparation_selection_too_large",
                "message": f"Select no more than {maximum} recordings.",
            },
        )
    result = await _database_call(
        request,
        "prepare selected recordings",
        lambda: request.app.state.preparation_service.prepare_selected(
            tuple(body.recording_ids)
        ),
    )
    if result.has_active_work:
        response.status_code = status.HTTP_202_ACCEPTED
    return prepare_response(result)


@router.get("/processing/overview", response_model=ProcessingOverviewResponse)
async def processing_overview(request: Request) -> ProcessingOverviewResponse:
    view = await _database_call(
        request,
        "load processing overview",
        request.app.state.processing_view_service.overview,
    )
    return processing_overview_response(view)


@router.get("/processing/jobs", response_model=ProcessingJobsResponse)
async def processing_jobs(
    request: Request,
    view: Annotated[Literal["queued", "failed", "history"], Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    q: Annotated[str, Query(max_length=100)] = "",
) -> ProcessingJobsResponse:
    try:
        page = await _database_call(
            request,
            "load processing jobs",
            lambda: request.app.state.processing_view_service.jobs(
                view,
                limit=limit,
                cursor=cursor,
                search=q,
            ),
        )
    except InvalidProcessingCursor as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "processing_cursor_invalid",
                "message": "The processing cursor is invalid.",
            },
        ) from error
    return processing_jobs_response(page)


@router.post(
    "/processing/jobs/{failed_job_id:int}/retry",
    response_model=RetryResponse,
)
async def retry_failed_job(
    failed_job_id: Annotated[int, Path(gt=0)],
    request: Request,
    response: Response,
) -> RetryResponse:
    result = await _database_call(
        request,
        "retry failed processing job",
        lambda: request.app.state.processing_view_service.retry(failed_job_id),
    )
    if result.outcome == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "processing_job_not_found",
                "message": "The requested processing job was not found.",
            },
        )
    if result.outcome == "conflict":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "processing_job_not_failed",
                "message": "Only a failed processing attempt can be retried.",
            },
        )
    if result.state in {"queued", "processing"}:
        response.status_code = status.HTTP_202_ACCEPTED
    return retry_response(result)


async def _database_call(request: Request, operation_name: str, operation):
    try:
        return await _run_catalog_call(request, operation)
    except psycopg.Error as error:
        raise _database_error(operation_name, error) from error


def _database_error(operation: str, error: psycopg.Error) -> HTTPException:
    if isinstance(error, psycopg.OperationalError):
        logger.warning("Database unavailable while attempting to %s.", operation)
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "The requested state is currently unavailable.",
            },
        )
    logger.error("Database operation failed while attempting to %s.", operation)
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "database_operation_failed",
            "message": "The requested operation could not be completed.",
        },
    )
