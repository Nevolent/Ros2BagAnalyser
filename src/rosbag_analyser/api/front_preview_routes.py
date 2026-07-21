from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParameter, Request, Response
import psycopg

from rosbag_analyser.front_preview import FrontPreviewService, PreviewDisplay

from .catalog_routes import _run_catalog_call
from .front_preview_schemas import FrontPreviewResponse, front_preview_response
from .range_file_response import RangeFileResponse


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _service(request: Request) -> FrontPreviewService:
    return request.app.state.front_preview_service


@router.get(
    "/recordings/{recording_id:int}/front-preview",
    response_model=FrontPreviewResponse,
)
async def get_front_preview(
    recording_id: Annotated[int, PathParameter(gt=0)], request: Request
) -> FrontPreviewResponse:
    display = await _preview_call(
        request, lambda: _service(request).get_state(recording_id)
    )
    _raise_if_not_found(display)
    return front_preview_response(recording_id, display)


@router.post(
    "/recordings/{recording_id:int}/front-preview",
    response_model=FrontPreviewResponse,
)
async def request_front_preview(
    recording_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
    response: Response,
) -> FrontPreviewResponse:
    display = await _preview_call(
        request, lambda: _service(request).request(recording_id)
    )
    _raise_if_not_found(display)
    if display.state in {"queued", "processing"}:
        response.status_code = 202
    return front_preview_response(recording_id, display)


@router.api_route(
    "/recordings/{recording_id:int}/front-preview/media/{artifact_id:int}",
    methods=["GET", "HEAD"],
)
async def get_front_preview_media(
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
                "code": "front_preview_not_ready",
                "message": "The current front-camera preview is not ready.",
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
                "ETag": f'"front-preview-{artifact.id}-{artifact.cache_identity}"',
            },
        )
    except BaseException:
        os.close(opened.descriptor)
        raise


async def _preview_call(request: Request, operation):
    try:
        return await _run_catalog_call(request, operation)
    except psycopg.OperationalError as error:
        logger.warning("Preview database unavailable.", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "preview_database_unavailable",
                "message": "Preview state is currently unavailable.",
            },
        ) from error
    except psycopg.Error as error:
        logger.error("Preview database operation failed.", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "preview_operation_failed",
                "message": "The preview operation could not be completed.",
            },
        ) from error


def _raise_if_not_found(display: PreviewDisplay) -> None:
    if not display.recording_exists:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
