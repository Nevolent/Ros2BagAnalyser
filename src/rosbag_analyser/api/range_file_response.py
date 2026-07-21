from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from email.utils import formatdate, parsedate_to_datetime
import os
import re
import stat
from typing import TypeVar

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse, Response
from starlette.types import Receive, Scope, Send


CHUNK_SIZE = 1024 * 1024
Result = TypeVar("Result")


class RangeFileResponse(Response):
    """Serve one validated regular file with the byte range browsers need."""

    def __init__(
        self,
        descriptor: int,
        *,
        media_type: str,
        stat_result: os.stat_result,
        executor: ThreadPoolExecutor,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content=b"", media_type=media_type, headers=headers)
        self.descriptor = descriptor
        self.stat_result = stat_result
        self.executor = executor
        self.headers["Accept-Ranges"] = "bytes"
        self.headers["Last-Modified"] = formatdate(
            stat_result.st_mtime, usegmt=True
        )
        if "content-length" in self.headers:
            del self.headers["content-length"]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del receive
        descriptor = self._take_validated_descriptor()
        file = os.fdopen(descriptor, "rb", closefd=True)
        try:
            file_size = self.stat_result.st_size
            request_headers = Headers(scope=scope)
            is_get = scope["method"].upper() == "GET"
            range_header = request_headers.get("range") if is_get else None
            if_range = request_headers.get("if-range") if is_get else None
            try:
                selected = (
                    _selected_range(range_header, file_size)
                    if _if_range_matches(
                        if_range,
                        self.headers.get("etag"),
                        self.stat_result.st_mtime,
                    )
                    else None
                )
            except ValueError as error:
                await self._run_io(file.close)
                response = PlainTextResponse(
                    str(error),
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )
                await response(scope, _empty_receive, send)
                return

            partial = selected is not None
            start, end = selected if selected is not None else (0, file_size)
            self.status_code = 206 if partial else 200
            self.headers["Content-Length"] = str(end - start)
            if partial:
                self.headers["Content-Range"] = f"bytes {start}-{end - 1}/{file_size}"
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            if scope["method"].upper() == "HEAD":
                await send(
                    {"type": "http.response.body", "body": b"", "more_body": False}
                )
                return

            await self._run_io(file.seek, start)
            remaining = end - start
            while remaining:
                chunk = await self._run_io(file.read, min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise RuntimeError("Validated media ended before its recorded size.")
                remaining -= len(chunk)
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": remaining > 0,
                    }
                )
        finally:
            if not file.closed:
                await self._run_io(file.close)

    def _take_validated_descriptor(self) -> int:
        descriptor = self.descriptor
        if descriptor < 0:
            raise RuntimeError("Validated media descriptor is unavailable.")
        self.descriptor = -1
        try:
            actual = os.fstat(descriptor)
            expected = self.stat_result
            if (
                not stat.S_ISREG(actual.st_mode)
                or actual.st_dev != expected.st_dev
                or actual.st_ino != expected.st_ino
                or actual.st_size != expected.st_size
                or actual.st_mtime_ns != expected.st_mtime_ns
            ):
                raise RuntimeError("Validated media changed before delivery.")
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    async def _run_io(
        self, operation: Callable[..., Result], *arguments: object
    ) -> Result:
        future = self.executor.submit(operation, *arguments)
        try:
            while not future.done():
                await asyncio.sleep(0.001)
            return future.result()
        except BaseException:
            future.cancel()
            raise


def _selected_range(
    range_header: str | None, file_size: int
) -> tuple[int, int] | None:
    if range_header is None:
        return None
    if len(range_header) > 200 or "=" not in range_header:
        raise ValueError("Invalid byte range.")
    unit, value = range_header.split("=", 1)
    if unit.lower() != "bytes":
        return None
    match = re.fullmatch(r"([0-9]*)-([0-9]*)", value, flags=re.ASCII)
    if match is None or not any(match.groups()):
        raise ValueError("Invalid byte range.")
    start_text, end_text = match.groups()
    try:
        if start_text:
            start = int(start_text)
            end = file_size if not end_text else min(int(end_text) + 1, file_size)
            if start < 0 or start >= file_size or end <= start:
                raise ValueError
            return start, end
        suffix_length = int(end_text)
        if suffix_length <= 0 or file_size <= 0:
            raise ValueError
        return max(0, file_size - suffix_length), file_size
    except ValueError as error:
        raise ValueError("Requested byte range is not satisfiable.") from error


def _if_range_matches(
    if_range: str | None, etag: str | None, modification_time: float
) -> bool:
    if if_range is None:
        return True
    if if_range.startswith("W/") or if_range.startswith('"'):
        return etag is not None and if_range == etag
    try:
        validator_time = parsedate_to_datetime(if_range)
        if validator_time.tzinfo is None:
            validator_time = validator_time.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return False
    return int(modification_time) == int(validator_time.timestamp())


async def _empty_receive() -> dict[str, str]:
    return {"type": "http.request"}
