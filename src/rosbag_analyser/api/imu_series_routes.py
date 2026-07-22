from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path as PathParameter, Request, Response
import psycopg

from rosbag_analyser.imu_series import ImuSeriesDisplay, ImuSeriesService

from .catalog_routes import _run_catalog_call
from .imu_series_schemas import ImuSeriesResponse, imu_series_response
from .range_file_response import RangeFileResponse


router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _service(request: Request) -> ImuSeriesService:
    return request.app.state.imu_series_service


@router.get(
    "/recordings/{recording_id:int}/imu-series",
    response_model=ImuSeriesResponse,
)
async def get_imu_series(
    recording_id: Annotated[int, PathParameter(gt=0)], request: Request
) -> ImuSeriesResponse:
    display = await _imu_call(
        request, lambda: _service(request).get_state(recording_id)
    )
    _raise_if_not_found(display)
    return imu_series_response(recording_id, display)


@router.post(
    "/recordings/{recording_id:int}/imu-series",
    response_model=ImuSeriesResponse,
)
async def request_imu_series(
    recording_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
    response: Response,
) -> ImuSeriesResponse:
    display = await _imu_call(request, lambda: _service(request).request(recording_id))
    _raise_if_not_found(display)
    if display.state in {"queued", "processing"}:
        response.status_code = 202
    return imu_series_response(recording_id, display)


@router.api_route(
    "/recordings/{recording_id:int}/imu-series/data/{artifact_id:int}",
    methods=["GET", "HEAD"],
)
async def get_imu_series_data(
    recording_id: Annotated[int, PathParameter(gt=0)],
    artifact_id: Annotated[int, PathParameter(gt=0)],
    request: Request,
) -> RangeFileResponse:
    resolved = await _imu_call(
        request,
        lambda: _service(request).resolve_series(recording_id, artifact_id),
    )
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "imu_series_not_ready",
                "message": "The current IMU series is not ready.",
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
                "ETag": f'"imu-series-{artifact.id}-{artifact.cache_identity}"',
            },
        )
    except BaseException:
        os.close(opened.descriptor)
        raise


async def _imu_call(request: Request, operation):
    try:
        return await _run_catalog_call(request, operation)
    except psycopg.OperationalError as error:
        logger.warning("IMU series database unavailable.", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "imu_database_unavailable",
                "message": "IMU series state is currently unavailable.",
            },
        ) from error
    except psycopg.Error as error:
        logger.error("IMU series database operation failed.", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "imu_operation_failed",
                "message": "The IMU series operation could not be completed.",
            },
        ) from error


def _raise_if_not_found(display: ImuSeriesDisplay) -> None:
    if not display.recording_exists:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "recording_not_found",
                "message": "The requested recording was not found.",
            },
        )
