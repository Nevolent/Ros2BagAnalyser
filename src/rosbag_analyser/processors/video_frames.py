"""Read evenly spaced video frames into memory without writing near the input."""

from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import os
import signal
import time
from rosbag_analyser.model_runtime import FRAME_COUNT, MAX_FRAME_SIDE
from rosbag_analyser.job_control import JobCanceled

def _decode_command(command, *, timeout, pass_fds, control=None, text=False):
    if control is None:
        return subprocess.run(command, capture_output=True, check=True, timeout=timeout,
                              pass_fds=pass_fds, text=text)
    control.checkpoint("processing")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               pass_fds=pass_fds, text=text, start_new_session=True)
    started = time.monotonic()
    def send(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                send(signal.SIGSTOP)
                before = time.monotonic()
                try:
                    control.checkpoint("processing")
                finally:
                    started += time.monotonic() - before
                    send(signal.SIGCONT)
                if time.monotonic() - started >= timeout:
                    raise subprocess.TimeoutExpired(command, timeout)
    finally:
        if process.poll() is None:
            send(signal.SIGCONT)
            send(signal.SIGTERM)
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                send(signal.SIGKILL)
                process.communicate(timeout=2)

def _local_video(path: Path) -> Path:
    path = path.expanduser().absolute()
    if any(part.is_symlink() for part in [path, *path.parents]):
        raise ValueError(f"Video paths must not follow symlinks: {path}")
    if not path.is_file():
        raise ValueError(f"Video file does not exist: {path}")
    return path


def _video_timing(path: Path, *, video_fd: int | None = None, ffprobe: str = "ffprobe", control=None) -> tuple[float, float]:
    try:
        result = _decode_command(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=duration,avg_frame_rate:format=duration", "-of", "json",
             str(path)],
            text=True, timeout=30, control=control,
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


def sample_video_frames(path: Path, *, count: int = FRAME_COUNT,
                        max_side: int = MAX_FRAME_SIDE, video_fd: int | None = None,
                        ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", control=None,
                        allow_partial: bool = False) -> tuple[list[bytes], list[float]]:
    """Sample chronological PNG bytes in memory; no additional image dependency."""
    if count < 2 or max_side < 1:
        raise ValueError("At least two frames and a positive maximum side are required")
    path = _local_video(path) if video_fd is None else Path(f"/proc/self/fd/{video_fd}")
    try:
        duration, half_frame = _video_timing(path, video_fd=video_fd, ffprobe=ffprobe, control=control)
        timestamps = [(index + 0.5) * duration / count for index in range(count)]
    except JobCanceled:
        raise
    except (RuntimeError, ValueError):
        if not allow_partial:
            raise
        duration, half_frame, timestamps = 0.0, 0.0, [0.0]
    frames = []
    selected_times = []
    if allow_partial and duration > 0:
        timestamps.append(0.0)
    for index, timestamp in enumerate(timestamps, 1):
        if index > count and frames:
            break
        if control is not None:
            control.checkpoint("processing")
        last_seek = max(0.0, duration - 2 * half_frame - 0.000001)
        nearest_seek = min(last_seek, max(0.0, timestamp - half_frame))
        # A sparse video may have no frame near the midpoint of its final bin.
        # Retry at the bin's start instead of silently returning fewer frames.
        for seek_time in (nearest_seek, (index - 1) * duration / count):
            try:
                result = _decode_command(
                    [ffmpeg, "-nostdin", "-v", "error", "-ss", f"{seek_time:.6f}",
                     "-i", str(path), "-map", "0:v:0", "-frames:v", "1",
                     "-vf", (f"scale={max_side}:{max_side}:"
                             "force_original_aspect_ratio=decrease"),
                     "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
                    timeout=60, control=control,
                    pass_fds=() if video_fd is None else (video_fd,),
                )
                if not result.stdout:
                    continue
                payload = result.stdout
                if not payload.startswith(b"\x89PNG\r\n\x1a\n") or len(payload) > 4 * max_side**2 + 65536:
                    raise ValueError("Decoder did not return a bounded PNG frame")
                frames.append(payload)
                selected_times.append(seek_time)
                break
            except (FileNotFoundError, subprocess.CalledProcessError,
                    subprocess.TimeoutExpired, OSError) as exc:
                if allow_partial:
                    continue
                raise RuntimeError(
                    f"Could not decode frame {index}/{count} near {timestamp:.1f}s: {exc}"
                ) from exc
        else:
            if not allow_partial:
                raise RuntimeError(f"No frame available near {timestamp:.1f}s")
    if not frames:
        raise RuntimeError("No usable video frame was found")
    return frames, selected_times
