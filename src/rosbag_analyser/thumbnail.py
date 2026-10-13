"""Shared bounded preview frames for row playback and visual inference."""
from __future__ import annotations

import hashlib
import io
import struct
import math
import json
import os

import av
from rosbag_analyser.catalog.paths import cache_source_identity_values, SOURCE_CACHE_IDENTITY_POLICY

THUMBNAIL_POLICY = "thumbnail-v3:preview-or-camera:shared-six:side448:png-strip"
THUMBNAIL_PLANNER_IDENTITY = hashlib.sha256(THUMBNAIL_POLICY.encode()).hexdigest()
MAX_THUMBNAIL_SIDE = 448
THUMBNAIL_FRAME_COUNT = 6
MAX_THUMBNAIL_BYTES = THUMBNAIL_FRAME_COUNT * 1024 * 1024


def unavailable_thumbnail(kind: str, code: str | None) -> bool:
    return kind == "thumbnail" and code == "thumbnail_camera_unavailable"


def thumbnail_cache_identity(front_identity: str) -> str:
    return hashlib.sha256(f"{front_identity}:{THUMBNAIL_POLICY}".encode()).hexdigest()


def thumbnail_source_identity(record, metadata_identity, database_identity, video_identity=None) -> str:
    document = {
        "policy": SOURCE_CACHE_IDENTITY_POLICY,
        "recording": [record.identity_recording_id, record.identity_relative_path,
                      record.start_time_ns, record.duration_ns],
        "files": [None if identity is None else cache_source_identity_values(identity)
                  for identity in (metadata_identity, database_identity, video_identity)],
    }
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def png_bytes(pixels) -> bytes:
    frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
    codec = av.CodecContext.create("png", "w")
    codec.width, codec.height, codec.pix_fmt = frame.width, frame.height, "rgb24"
    return b"".join(bytes(packet) for packet in codec.encode(frame) + codec.encode(None))


def thumbnail_frames(descriptor: int, manifest: dict) -> tuple[list[bytes], list[float]]:
    """Feed the exact displayed tile pixels into inference, without video decoding."""
    data = os.pread(descriptor, MAX_THUMBNAIL_BYTES + 1, 0)
    validate_thumbnail(data, manifest)
    with av.open(io.BytesIO(data), format="image2pipe") as container:
        pixels = next(container.decode(video=0)).to_ndarray(format="rgb24")
    width, count = manifest['output']['frame_width'], manifest['output']['frame_count']
    images = [png_bytes(pixels[:, index * width:(index + 1) * width].copy()) for index in range(count)]
    source = manifest['source']
    times = source.get('frame_times_seconds')
    if times is None:
        stamps = list(map(int, source['record_timestamps_ns']))
        times = [(stamp - stamps[0]) / 1e9 for stamp in stamps]
    return images, times


def validate_thumbnail(data: bytes, manifest: dict) -> None:
    front = manifest.get("front_source_identity")
    output = manifest.get("output", {})
    if (manifest.get("schema_version") != 2
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
    frame_width = output.get("frame_width")
    count = output.get("frame_count")
    if (type(frame_width) is not int or not 0 < frame_width <= MAX_THUMBNAIL_SIDE
            or type(count) is not int or not 1 <= count <= THUMBNAIL_FRAME_COUNT
            or width != frame_width * count
            or not 0 < height <= MAX_THUMBNAIL_SIDE
            or (width, height) != (output.get("width"), output.get("height"))):
        raise ValueError("Invalid thumbnail dimensions")
    source = manifest.get("source")
    timestamps = source.get("record_timestamps_ns") if isinstance(source, dict) else None
    if (not isinstance(timestamps, list) or len(timestamps) != count
            or any(not isinstance(t, str) or not t.isdecimal() or int(t) > 2**63 - 1 for t in timestamps)
            or timestamps != sorted(timestamps, key=int)):
        raise ValueError("Invalid thumbnail timestamps")
    times = source.get("frame_times_seconds")
    if times is not None and (not isinstance(times, list) or len(times) != count
        or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times)
        or times != sorted(times)):
        raise ValueError("Invalid thumbnail frame times")
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
