"""Offline Q8 CPU inference in a job-owned llama.cpp server over a private socket."""
from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import tempfile
import time

from rosbag_analyser.ai_description import DESCRIPTION_PROMPT, validated_result, validate_description_result
from rosbag_analyser.model_runtime import (
    FRAME_COUNT, MAX_FRAME_SIDE, MAX_NEW_TOKENS, MODEL_FILE, VISION_FILE,
    validate_runtime,
)
from rosbag_analyser.processors.video_frames import sample_video_frames

MAX_RESPONSE_BYTES = 64 * 1024
CUES = ("gravel_like_terrain", "dark_curtains", "artificial_lighting",
        "other_robots_visible", "people_visible", "independent_movement_visible")
EVIDENCE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "environment": {"type": "string", "minLength": 1, "maxLength": 200},
        "objects": {"type": "array", "maxItems": 2,
                    "items": {"type": "string", "minLength": 1, "maxLength": 60}},
        **{name: {"type": "boolean"} for name in CUES},
    },
    "required": ["environment", "objects", *CUES],
}


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, *, timeout=None):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.socket_path))


def request_json(path: Path, method: str, route: str, body=None, *, timeout=None):
    connection = UnixHTTPConnection(path, timeout=timeout)
    try:
        payload = None if body is None else json.dumps(body).encode()
        connection.request(method, route, body=payload, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if response.status != 200 or len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("llama.cpp returned an unsuccessful or oversized response.")
        return json.loads(data)
    finally:
        connection.close()


def completion_request(images: list[bytes], timestamps: list[float]) -> dict:
    if len(images) != FRAME_COUNT or len(timestamps) != FRAME_COUNT:
        raise ValueError("The fixed description frame policy was not satisfied.")
    content = [{"type": "text", "text": (
        f"These {FRAME_COUNT} sampled frames are in chronological order from one video. "
        "The timestamp before each image is seconds from its beginning."
    )}]
    for index, (image, timestamp) in enumerate(zip(images, timestamps), 1):
        content.extend([
            {"type": "text", "text": f"Frame {index}, timestamp {timestamp:.3f} seconds:"},
            {"type": "image_url", "image_url": {
                "url": "data:image/png;base64," + base64.b64encode(image).decode("ascii")}},
        ])
    content.append({"type": "text", "text": DESCRIPTION_PROMPT})
    return {
        "messages": [
            {"role": "system", "content": (
                "Follow the requested JSON format exactly. Environment is one "
                "short setting/terrain/background/lighting phrase, without objects, "
                "activity, or camera motion. Objects are separate noun phrases. "
                "Use booleans for the six visual cues."
            )},
            {"role": "user", "content": content},
        ],
        "temperature": 0, "seed": 0, "max_tokens": MAX_NEW_TOKENS,
        "stream": False, "cache_prompt": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "visual_evidence", "schema": EVIDENCE_SCHEMA},
        },
    }


def infer(root: Path, images: list[bytes], timestamps: list[float], *, threads: int) -> dict:
    validate_runtime(root)
    with tempfile.TemporaryDirectory(prefix="qwen-", dir="/tmp") as temporary:
        socket_path = Path(temporary) / "server.sock"
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("LLAMA_ARG_", "GGML_", "MTMD_"))}
        environment.update(LD_LIBRARY_PATH=str(root / "bin"),
                           GGML_BACKEND_PATH=str(root / "bin"), OMP_NUM_THREADS=str(threads))
        # Inherits the inference process group: pause/cancel also controls the server.
        server = subprocess.Popen([
            str(root / "bin/llama-server"), "--model", str(root / "model" / MODEL_FILE),
            "--mmproj", str(root / "model" / VISION_FILE), "--host", str(socket_path),
            "--device", "none", "--n-gpu-layers", "0", "--no-mmproj-offload",
            "--threads", str(threads), "--threads-batch", str(threads), "--poll", "0",
            "--ctx-size", "4096", "--batch-size", "512", "--ubatch-size", "128",
            "--parallel", "1", "--image-min-tokens", "64", "--image-max-tokens", "256",
            "--no-webui", "--jinja",
        ], env=environment, stdout=None, stderr=None)
        try:
            while True:
                if server.poll() is not None:
                    raise ValueError("llama.cpp exited before becoming ready.")
                try:
                    if request_json(socket_path, "GET", "/health", timeout=1).get("status") == "ok":
                        break
                except (OSError, ValueError, http.client.HTTPException):
                    pass
                time.sleep(0.1)
            # Parent enforces active-time timeout; no wall-clock timeout invalidates pauses.
            response = request_json(socket_path, "POST", "/v1/chat/completions",
                                    completion_request(images, timestamps))
            choices = response.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("llama.cpp returned invalid completion choices.")
            choice = choices[0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("The model description was truncated.")
            text = choice.get("message", {}).get("content")
            if not isinstance(text, str):
                raise ValueError("llama.cpp returned invalid completion text.")
            return validate_description_result(validated_result(text))
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


def main():
    # Let the private socket and native child unwind when the worker cancels us.
    signal.signal(signal.SIGTERM, _terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-fd", type=int, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--threads", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.threads <= 32:
        parser.error("--threads must be between 1 and 32")
    images, timestamps = sample_video_frames(
        Path(f"/proc/self/fd/{args.video_fd}"), video_fd=args.video_fd,
        count=FRAME_COUNT, max_side=MAX_FRAME_SIDE, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
    )
    result = infer(args.runtime_root, images, timestamps, threads=args.threads)
    args.output.write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")


def _terminate(*_):
    raise SystemExit(143)


if __name__ == "__main__":
    main()
