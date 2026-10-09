"""Pinned, offline CPU vision runtime; large assets are provisioned outside Git."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat

MODEL_REPOSITORY = "Qwen/Qwen3-VL-2B-Instruct-GGUF"
MODEL_REVISION = "52d6c8ffea26cc873ac5ad116f8631268d7eb503"
LLAMA_REVISION = "8345f333951c661d166b00e6f9362e553768f292"
LLAMA_SOURCE_SHA256 = "84050e783dbd0c4a4678f90f253b0881df04e90a98c20f73ae3709751c4a4850"
RUNTIME_ID = "qwen3-vl-2b-q8-52d6c8ff-llama-8345f333-cpu-v1"
MODEL_FILE = "Qwen3VL-2B-Instruct-Q8_0.gguf"
VISION_FILE = "mmproj-Qwen3VL-2B-Instruct-F16.gguf"
MODEL_ASSETS = {
    MODEL_FILE: (1834427424, "1e8db19207c8ce0733ddd78c2eff8a9e22c27c82f4443df94c25792ed8fe04f2"),
    VISION_FILE: (819394848, "c3d5afbef5287953acd57b4043d2269456e5761a4eaccb3b71b062996970aea5"),
}
FRAME_COUNT = 6
MAX_FRAME_SIDE = 448
MAX_NEW_TOKENS = 160
DEFAULT_THREADS = 4
DEFAULT_TIMEOUT_SECONDS = 300


def default_runtime_root(*, deployment: bool = False) -> Path:
    base = Path("/opt/rosbag-analyser/models") if deployment else Path.home() / ".local/share/rosbag-analyser/models"
    return base / RUNTIME_ID


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_path(path: Path) -> os.stat_result:
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Model runtime paths must not follow symbolic links.")
    details = path.stat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError("A model runtime file is not regular.")
    return details


def validate_runtime(root: Path, *, verify_hashes: bool = False) -> dict:
    """Check pinned provenance and installed file facts; setup also verifies bytes."""
    marker = root / "runtime.json"
    details = regular_path(marker)
    if details.st_size > 128 * 1024:
        raise ValueError("Model runtime manifest is too large.")
    manifest = json.loads(marker.read_text())
    if (not isinstance(manifest, dict) or manifest.get("runtime_id") != RUNTIME_ID
            or manifest.get("model_revision") != MODEL_REVISION
            or manifest.get("llama_revision") != LLAMA_REVISION
            or not isinstance(manifest.get("files"), dict)):
        raise ValueError("Model runtime has the wrong identity.")
    files = manifest["files"]
    required = {f"model/{name}" for name in MODEL_ASSETS} | {"bin/llama-server"}
    if not required.issubset(files) or len(files) > 64:
        raise ValueError("Model runtime is incomplete.")
    for relative, recorded in files.items():
        if (not isinstance(relative, str) or not isinstance(recorded, dict)
                or not isinstance(recorded.get("sha256"), str)
                or any(char not in "0123456789abcdef" for char in recorded["sha256"])):
            raise ValueError("Model runtime contains an invalid file record.")
        path = Path(relative)
        if (path.is_absolute() or ".." in path.parts or len(path.parts) != 2
                or path.parts[0] not in {"bin", "model"}):
            raise ValueError("Model runtime contains an unsafe path.")
        current = regular_path(root / path)
        if (current.st_size != recorded.get("size_bytes")
                or current.st_mtime_ns != recorded.get("mtime_ns")
                or len(recorded.get("sha256", "")) != 64):
            raise ValueError("A model runtime file changed after validation.")
        if path.parts[0] == "model" and (
                path.name not in MODEL_ASSETS
                or (recorded["size_bytes"], recorded["sha256"]) != MODEL_ASSETS[path.name]):
            raise ValueError("Model weights have the wrong identity.")
        if verify_hashes and file_sha256(root / path) != recorded["sha256"]:
            raise ValueError("A model runtime checksum does not match.")
    if not os.access(root / "bin/llama-server", os.X_OK):
        raise ValueError("The llama.cpp executable is unavailable.")
    return manifest
