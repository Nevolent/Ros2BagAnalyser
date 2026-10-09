"""Read evenly spaced video frames into memory without writing near the input."""

from io import BytesIO
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess

from PIL import Image


def _local_video(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError(f"Video paths must not follow symlinks: {path}")
    if not path.is_file():
        raise ValueError(f"Video file does not exist: {path}")
    return path


def _video_timing(path: Path, *, video_fd: int | None = None, ffprobe: str = "ffprobe") -> tuple[float, float]:
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration,avg_frame_rate:format=duration", "-of", "json",
             str(path)],
            capture_output=True, text=True, check=True, timeout=30,
            pass_fds=() if video_fd is None else (video_fd,),
        )
        info = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not probe video: {exc}") from exc
    streams = info.get("streams", [])
    if not streams:
        raise ValueError("Video has no readable video stream")
    duration = None
    for value in (streams[0].get("duration"), info.get("format", {}).get("duration")):
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            duration = candidate
            break
    if duration is None:
        raise ValueError("Video has no usable duration")
    try:
        fps = float(Fraction(streams[0]["avg_frame_rate"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    return duration, 0.5 / fps if math.isfinite(fps) and fps > 0 else 0.0


def sample_video_frames(path: Path, *, count: int = 12,
                        max_side: int = 640, video_fd: int | None = None,
                        ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> tuple[list[Image.Image], list[float]]:
    """Sample the center of each equal-duration interval, earliest to latest."""
    if count < 2 or max_side < 1:
        raise ValueError("At least two frames and a positive maximum side are required")
    path = _local_video(path) if video_fd is None else Path(f"/proc/self/fd/{video_fd}")
    duration, half_frame = _video_timing(path, video_fd=video_fd, ffprobe=ffprobe)
    timestamps = [(index + 0.5) * duration / count for index in range(count)]
    frames = []
    for index, timestamp in enumerate(timestamps, 1):
        last_seek = max(0.0, duration - 2 * half_frame - 0.000001)
        nearest_seek = min(last_seek, max(0.0, timestamp - half_frame))
        # A sparse video may have no frame near the midpoint of its final bin.
        # Retry at the bin's start instead of silently returning fewer frames.
        for seek_time in (nearest_seek, (index - 1) * duration / count):
            try:
                result = subprocess.run(
                    [ffmpeg, "-nostdin", "-v", "error", "-ss", f"{seek_time:.6f}",
                     "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
                     "-vf", (f"scale={max_side}:{max_side}:"
                             "force_original_aspect_ratio=decrease"),
                     "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                    capture_output=True, check=True, timeout=60,
                    pass_fds=() if video_fd is None else (video_fd,),
                )
                if not result.stdout:
                    continue
                with Image.open(BytesIO(result.stdout)) as image:
                    frames.append(image.convert("RGB"))
                timestamps[index - 1] = seek_time
                break
            except (FileNotFoundError, subprocess.CalledProcessError,
                    subprocess.TimeoutExpired, OSError) as exc:
                raise RuntimeError(
                    f"Could not decode frame {index}/{count} near {timestamp:.1f}s: {exc}"
                ) from exc
        else:
            raise RuntimeError(f"No frame available near {timestamp:.1f}s")
    return frames, timestamps
