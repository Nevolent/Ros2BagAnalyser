from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

from rosbag_analyser.api import range_file_response
from rosbag_analyser.api.range_file_response import RangeFileResponse


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_abandoned_open_ended_range_stops_reading_after_disconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "preview.mp4"
    media.write_bytes(b"0123456789abcdefghij")
    descriptor = os.open(media, os.O_RDONLY)
    disconnected = asyncio.Event()
    request_delivered = False
    messages: list[dict[str, object]] = []
    monkeypatch.setattr(range_file_response, "CHUNK_SIZE", 4)

    async def receive() -> dict[str, object]:
        nonlocal request_delivered
        if not request_delivered:
            request_delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            disconnected.set()
            await asyncio.sleep(0)

    with ThreadPoolExecutor(max_workers=1) as executor:
        response = RangeFileResponse(
            descriptor,
            media_type="video/mp4",
            stat_result=os.stat(media),
            executor=executor,
        )
        await response(
            {
                "type": "http",
                "method": "GET",
                "headers": [(b"range", b"bytes=0-")],
            },
            receive,
            send,
        )

    start = messages[0]
    bodies = [
        message for message in messages if message["type"] == "http.response.body"
    ]
    assert start["status"] == 206
    assert len(bodies) == 1
    assert bodies[0]["body"] == b"0123"
    assert bodies[0]["more_body"] is True
