from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request

from .front_preview_routes import _preview_call
from .range_file_response import RangeFileResponse

router = APIRouter(prefix="/api")


@router.api_route("/recordings/{recording_id:int}/thumbnail/media/{artifact_id:int}", methods=["GET", "HEAD"])
async def get_thumbnail(recording_id: Annotated[int, Path(gt=0)],
                        artifact_id: Annotated[int, Path(gt=0)], request: Request):
    resolved = await _preview_call(request, lambda: request.app.state.preparation_service.resolve_thumbnail(
        recording_id, artifact_id,
    ))
    if resolved is None:
        raise HTTPException(status_code=404, detail={"code": "thumbnail_not_ready",
                                                    "message": "The current thumbnail is not ready."})
    opened, artifact = resolved
    try:
        return RangeFileResponse(
            opened.descriptor, media_type="image/png", stat_result=opened.stat_result,
            executor=request.app.state.media_read_executor,
            headers={"Cache-Control": "private, no-cache, must-revalidate",
                     "ETag": f'"thumbnail-{artifact.id}-{artifact.cache_identity}"'},
        )
    except BaseException:
        os.close(opened.descriptor)
        raise
