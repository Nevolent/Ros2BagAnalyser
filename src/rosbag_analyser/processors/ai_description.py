from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import time
import sys

from rosbag_analyser.ai_description import MAX_DESCRIPTION_BYTES, validate_description_result
from rosbag_analyser.model_runtime import DEFAULT_THREADS, DEFAULT_TIMEOUT_SECONDS, validate_runtime


def _signal_group(process, sig):
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


class DescriptionProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class DescriptionProcessor:
    def __init__(self, runtime_root: Path | None,
                 ffmpeg: Path, ffprobe: Path, *, threads: int = DEFAULT_THREADS,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 32:
            raise ValueError("Description CPU threads must be between 1 and 32.")
        if timeout_seconds <= 0:
            raise ValueError("Description timeout must be positive.")
        self.runtime_root = runtime_root
        self.threads = threads
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout_seconds = timeout_seconds

    def process(self, video_descriptor: int, output_path: Path, *, control=None):
        if self.runtime_root is None:
            raise DescriptionProcessingError(
                "ai_model_unavailable", "Provision the Q8 CPU model runtime to prepare AI descriptions.")
        try:
            validate_runtime(self.runtime_root)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DescriptionProcessingError("ai_model_unavailable", "The pinned Q8 CPU model runtime is unavailable or invalid.") from error
        environment = dict(os.environ)
        package_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = package_root
        command = [sys.executable, "-m", "rosbag_analyser.processors.qwen_inference",
                   "--video-fd", str(video_descriptor), "--runtime-root", str(self.runtime_root),
                   "--threads", str(self.threads),
                   "--output", str(output_path), "--ffmpeg", str(self.ffmpeg), "--ffprobe", str(self.ffprobe)]
        process = None
        started = time.monotonic()
        try:
            with (output_path.parent / "inference.log").open("wb") as log:
                process = subprocess.Popen(command, stdout=log, stderr=log, env=environment,
                                           pass_fds=(video_descriptor,), start_new_session=True)
                while True:
                    try:
                        returncode = process.wait(timeout=0.25)
                        break
                    except subprocess.TimeoutExpired:
                        if control is not None:
                            # Stop the child and decoders at the checkpoint so durable
                            # pauses do not leave inference advancing in the background.
                            _signal_group(process, signal.SIGSTOP)
                            try:
                                before = time.monotonic()
                                control.checkpoint("processing")
                                started += time.monotonic() - before
                            finally:
                                _signal_group(process, signal.SIGCONT)
                        if time.monotonic() - started > self.timeout_seconds:
                            raise DescriptionProcessingError("ai_description_timeout", "AI description generation timed out. Retry it.")
            if returncode != 0:
                raise DescriptionProcessingError("ai_description_inference_failed", "Qwen could not generate a valid description. Check the CPU model runtime and retry.")
            if control is not None:
                control.checkpoint("validating", force=True)
            if output_path.is_symlink() or not 0 < output_path.stat().st_size <= MAX_DESCRIPTION_BYTES:
                raise ValueError("Invalid result size")
            result = validate_description_result(json.loads(output_path.read_text(encoding="utf-8")))
            (output_path.parent / "inference.log").unlink(missing_ok=True)
            return result
        except (OSError, ValueError) as error:
            raise DescriptionProcessingError("ai_description_invalid", "The generated AI description is invalid.") from error
        finally:
            if process is not None:
                _signal_group(process, signal.SIGCONT)
                _signal_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _signal_group(process, signal.SIGKILL)
                    process.wait(timeout=2)
                # Reap remaining group members even if the Python wrapper exited first.
                _signal_group(process, signal.SIGKILL)
