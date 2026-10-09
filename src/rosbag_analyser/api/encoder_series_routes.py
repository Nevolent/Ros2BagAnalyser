from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParameter, Request, Response
import psycopg

from rosbag_analyser.encoder_series import EncoderSeriesDisplay, EncoderSeriesService

from .catalog_routes import _run_catalog_call
from .encoder_series_schemas import EncoderSeriesResponse, encoder_series_response
from .range_file_response import RangeFileResponse


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _service(request: Request) -> EncoderSeriesService:
    return request.app.state.encoder_series_service


@router.get(
    "/recordings/{recording_id:int}/encoder-series",
    response_model=EncoderSeriesResponse,
)
async def get_encoder_series(
    recording_id: Annotated[int, PathParameter(gt=0)], request: Request
) -> EncoderSeriesResponse:
    display = await _encoder_call(
        request, lambda: _service(request).get_state(recording_id)
    )
    _raise_if_not_found(display)
    return encoder_series_response(recording_id, display)


@router.post(
    "/recordings/{recording_id:int}/encoder-series",
    response_model=EncoderSeriesResponse,
)
async def request_encoder_series(
    recording_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
    response: Response,
) -> EncoderSeriesResponse:
    display = await _encoder_call(request, lambda: _service(request).request(recording_id))
    _raise_if_not_found(display)
    if display.state in {"queued", "processing"}:
        response.status_code = 202
    return encoder_series_response(recording_id, display)


@router.api_route(
    "/recordings/{recording_id:int}/encoder-series/data/{artifact_id:int}",
    methods=["GET", "HEAD"],
)
async def get_encoder_series_data(
    recording_id: Annotated[int, PathParameter(gt=0)],
    artifact_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
) -> RangeFileResponse:
    resolved = await _encoder_call(
        request,
        lambda: _service(request).resolve_series(recording_id, artifact_id),
    )
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "encoder_series_not_ready",
                "message": "The current Encoder series is not ready.",
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
                "ETag": f'"encoder-series-{artifact.id}-{artifact.cache_identity}"',
            },
        )
    except BaseException:
        os.close(opened.descriptor)
        raise


async def _encoder_call(request: Request, operation):
    try:
        return await _run_catalog_call(request, operation)
    except psycopg.OperationalError as error:
        logger.warning("Encoder series database unavailable.", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "encoder_database_unavailable",
                "message": "Encoder series state is currently unavailable.",
            },
        ) from error
    except psycopg.Error as error:
        logger.error("Encoder series database operation failed.", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "encoder_operation_failed",
                "message": "The Encoder series operation could not be completed.",
            },
        ) from error


def _raise_if_not_found(display: EncoderSeriesDisplay) -> None:
    if not display.recording_exists:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
