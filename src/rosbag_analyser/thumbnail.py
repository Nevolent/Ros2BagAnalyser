"""Fixed, independent single-frame thumbnail policy."""
from __future__ import annotations

import hashlib
import io
import struct

import av

THUMBNAIL_POLICY = "thumbnail-v1:default-colour:record-midpoint:side480:png"
THUMBNAIL_PLANNER_IDENTITY = hashlib.sha256(THUMBNAIL_POLICY.encode()).hexdigest()
MAX_THUMBNAIL_SIDE = 480
MAX_THUMBNAIL_BYTES = 1024 * 1024


def thumbnail_cache_identity(front_identity: str) -> str:
    return hashlib.sha256(f"{front_identity}:{THUMBNAIL_POLICY}".encode()).hexdigest()


def validate_thumbnail(data: bytes, manifest: dict) -> None:
    front = manifest.get("front_source_identity")
    output = manifest.get("output", {})
    if (manifest.get("schema_version") != 1
            or manifest.get("artifact_kind") != "thumbnail"
            or manifest.get("processor_version") != THUMBNAIL_POLICY
            or not isinstance(front, str) or len(front) != 64
            or any(c not in "0123456789abcdef" for c in front)
            or manifest.get("cache_identity") != thumbnail_cache_identity(front)
            or not isinstance(output, dict)
            or output.get("file_name") != "thumbnail.png"
            or output.get("mime_type") != "image/png"
            or not 33 <= len(data) <= MAX_THUMBNAIL_BYTES
            or output.get("size_bytes") != len(data)
            or output.get("sha256") != hashlib.sha256(data).hexdigest()
            or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR"):
        raise ValueError("Invalid thumbnail provenance")
    width, height = struct.unpack(">II", data[16:24])
    if (not 0 < width <= MAX_THUMBNAIL_SIDE or not 0 < height <= MAX_THUMBNAIL_SIDE
            or (width, height) != (output.get("width"), output.get("height"))):
        raise ValueError("Invalid thumbnail dimensions")
    position = 8
    chunks = 0
    while position < len(data):
        if position + 12 > len(data):
            raise ValueError("Invalid PNG chunk")
        size = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        position += size + 12
        chunks += 1
        if position > len(data) or (chunks > 1 and kind == b"IHDR"):
            raise ValueError("Invalid PNG structure")
        if kind == b"IEND":
            if size != 0 or position != len(data):
                raise ValueError("Invalid PNG ending")
            break
    else:
        raise ValueError("Missing PNG ending")
    with av.open(io.BytesIO(data), format="image2pipe") as container:
        frames = list(container.decode(video=0))
    if len(frames) != 1 or (frames[0].width, frames[0].height) != (width, height):
        raise ValueError("Invalid thumbnail image")
