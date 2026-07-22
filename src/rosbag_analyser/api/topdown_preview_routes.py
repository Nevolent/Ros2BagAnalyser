from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParameter, Request, Response
import psycopg

from rosbag_analyser.topdown_preview import (
    TopdownPreviewDisplay,
    TopdownPreviewService,
)

from .catalog_routes import _run_catalog_call
from .range_file_response import RangeFileResponse
from .topdown_preview_schemas import (
    TopdownPreviewResponse,
    topdown_preview_response,
)


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _service(request: Request) -> TopdownPreviewService:
    return request.app.state.topdown_preview_service


@router.get(
    "/recordings/{recording_id:int}/topdown-preview",
    response_model=TopdownPreviewResponse,
)
async def get_topdown_preview(
    recording_id: Annotated[int, PathParameter(gt=0)], request: Request
) -> TopdownPreviewResponse:
    display = await _preview_call(
        request, lambda: _service(request).get_state(recording_id)
    )
    _raise_if_not_found(display)
    return topdown_preview_response(recording_id, display)


@router.post(
    "/recordings/{recording_id:int}/topdown-preview",
    response_model=TopdownPreviewResponse,
)
async def request_topdown_preview(
    recording_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
    response: Response,
) -> TopdownPreviewResponse:
    display = await _preview_call(
        request, lambda: _service(request).request(recording_id)
    )
    _raise_if_not_found(display)
    if display.state in {"queued", "processing"}:
        response.status_code = 202
    return topdown_preview_response(recording_id, display)


@router.api_route(
    "/recordings/{recording_id:int}/topdown-preview/media/{artifact_id:int}",
    methods=["GET", "HEAD"],
)
async def get_topdown_preview_media(
    recording_id: Annotated[int, PathParameter(gt=0)],
    artifact_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
) -> RangeFileResponse:
    resolved = await _preview_call(
        request,
        lambda: _service(request).resolve_media(recording_id, artifact_id),
    )
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "topdown_preview_not_ready",
                "message": "The current top-down preview is not ready.",
            },
        )
    opened, artifact = resolved
    try:
        return RangeFileResponse(
            opened.descriptor,
            media_type=artifact.mime_type,
            stat_result=opened.stat_result,
            executor=request.app.state.media_read_executor,
            headers={
                "Cache-Control": "private, no-cache, must-revalidate",
                "ETag": f'"topdown-preview-{artifact.id}-{artifact.cache_identity}"',
            },
        )
    except BaseException:
        os.close(opened.descriptor)
        raise


async def _preview_call(request: Request, operation):
    try:
        return await _run_catalog_call(request, operation)
    except psycopg.OperationalError as error:
        logger.warning("Top-down preview database unavailable.", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "preview_database_unavailable",
                "message": "Top-down preview state is currently unavailable.",
            },
        ) from error
    except psycopg.Error as error:
        logger.error("Top-down preview database operation failed.", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "preview_operation_failed",
                "message": "The top-down preview operation could not be completed.",
            },
        ) from error


def _raise_if_not_found(display: TopdownPreviewDisplay) -> None:
    if not display.recording_exists:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
