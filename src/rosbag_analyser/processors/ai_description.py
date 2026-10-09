from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import time

from rosbag_analyser.ai_description import MAX_DESCRIPTION_BYTES, validate_description_result


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
    def __init__(self, python: Path | None, model_root: Path | None,
                 ffmpeg: Path, ffprobe: Path, *, timeout_seconds: float = 1800) -> None:
        self.python = python
        self.model_root = model_root
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout_seconds = timeout_seconds

    def process(self, video_descriptor: int, output_path: Path, *, control=None):
        if self.python is None or self.model_root is None:
            raise DescriptionProcessingError(
                "ai_model_unavailable", "Configure the local Qwen model environment to prepare AI descriptions.")
        if not self.python.is_file() or not (self.model_root / "model.safetensors").is_file():
            raise DescriptionProcessingError("ai_model_unavailable", "The configured Qwen model environment is unavailable.")
        environment = dict(os.environ)
        package_root = str(Path(__file__).resolve().parents[2])
        environment["PYTHONPATH"] = package_root
        environment["HF_HUB_OFFLINE"] = "1"
        environment["TRANSFORMERS_OFFLINE"] = "1"
        command = [str(self.python), "-m", "rosbag_analyser.processors.qwen_inference",
                   "--video-fd", str(video_descriptor), "--model-root", str(self.model_root),
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
                raise DescriptionProcessingError("ai_description_inference_failed", "Qwen could not generate a valid description. Check the model environment and retry.")
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
            if process is not None and process.poll() is None:
                _signal_group(process, signal.SIGCONT)
                _signal_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    _signal_group(process, signal.SIGKILL)
                    process.wait(timeout=2)
