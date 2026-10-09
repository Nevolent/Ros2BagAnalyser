"""Explicitly provision/check the pinned llama.cpp CPU runtime, without source data."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request

from rosbag_analyser.model_runtime import (
    LLAMA_REVISION, LLAMA_SOURCE_SHA256, MODEL_ASSETS, MODEL_REPOSITORY,
    MODEL_REVISION, RUNTIME_ID, default_runtime_root, file_sha256, validate_runtime,
    DEFAULT_THREADS, FRAME_COUNT, MAX_FRAME_SIDE,
)


def download(url: str, path: Path, digest: str, size: int | None = None) -> None:
    if path.is_symlink():
        raise ValueError("Download cache must not contain symbolic links.")
    if path.is_file() and (size is None or path.stat().st_size == size) and file_sha256(path) == digest:
        return
    temporary = path.with_suffix(path.suffix + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("An incomplete download exists; remove only that cache file before retrying.")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "rosbag-analyser-model-setup"})
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open("xb") as output:
            total = 0
            limit = size if size is not None else 128 * 1024 * 1024
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ValueError("Download exceeds its pinned size.")
                output.write(chunk)
        if (size is not None and total != size) or file_sha256(temporary) != digest:
            raise ValueError("Download does not match its pinned checksum/size.")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def unpack_source(archive: Path, target: Path) -> Path:
    expected = "llama.cpp-" + LLAMA_REVISION
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if (path.is_absolute() or ".." in path.parts or not path.parts
                    or path.parts[0] != expected or not (member.isfile() or member.isdir())):
                raise ValueError("The llama.cpp source archive contains an unsafe entry.")
        bundle.extractall(target)
    return target / expected


def provision(root: Path, cache: Path, *, build_threads: int = 4) -> None:
    root = root.expanduser().absolute()
    cache = cache.expanduser().absolute()
    if any(p.is_symlink() for p in (root, *root.parents, cache, *cache.parents)):
        raise ValueError("Runtime and cache paths must not follow symbolic links.")
    if root == cache or root in cache.parents or cache in root.parents:
        raise ValueError("Runtime and download cache must be separate.")
    for name in ("ROS_BAG_ANALYSER_ARCHIVE_ROOT", "ROS_BAG_ANALYSER_DERIVED_ROOT"):
        if configured := os.environ.get(name):
            data = Path(configured).expanduser().resolve()
            for output in (root, cache):
                resolved = output.resolve()
                if data == resolved or data in resolved.parents or resolved in data.parents:
                    raise ValueError("Model setup storage must be separate from source and derived roots.")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("The supported model runtime is Linux x86_64.")
    root.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    if any((cache / name).is_symlink() for name in ("setup.lock", "build.log")):
        raise ValueError("Setup files must not follow symbolic links.")
    with (cache / "setup.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if root.exists():
            validate_runtime(root, verify_hashes=True)
            print(f"Pinned model runtime already validated: {root}", flush=True)
            return
        for command in ("cmake", "g++", "make"):
            if shutil.which(command) is None:
                raise ValueError(f"Model setup requires {command}; install build-essential and cmake on the builder.")
        if shutil.disk_usage(root.parent).free < 8 * 1024**3:
            raise ValueError("Model setup needs at least 8 GiB free for staged assets and build output.")
        archive = cache / (LLAMA_REVISION + ".tar.gz")
        print("Downloading/checking pinned llama.cpp source...", flush=True)
        download(f"https://codeload.github.com/ggml-org/llama.cpp/tar.gz/{LLAMA_REVISION}", archive, LLAMA_SOURCE_SHA256)
        for name, (size, digest) in MODEL_ASSETS.items():
            print(f"Downloading/checking {name}...", flush=True)
            download(f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{name}", cache / name, digest, size)
        with tempfile.TemporaryDirectory(prefix="model-stage-", dir=root.parent) as temporary:
            stage = Path(temporary)
            source = unpack_source(archive, stage)
            build = stage / "build"
            print("Building portable CPU runtime (no CUDA; runtime CPU feature selection)...", flush=True)
            with (cache / "build.log").open("w") as log:
                subprocess.run(["cmake", "-S", str(source), "-B", str(build),
                                "-DCMAKE_BUILD_TYPE=Release", "-DGGML_NATIVE=OFF",
                                "-DGGML_BACKEND_DL=ON", "-DGGML_CPU_ALL_VARIANTS=ON",
                                "-DGGML_CUDA=OFF", "-DGGML_VULKAN=OFF", "-DGGML_OPENMP=ON",
                                "-DLLAMA_CURL=OFF", "-DLLAMA_BUILD_TESTS=OFF",
                                "-DLLAMA_BUILD_EXAMPLES=OFF", "-DLLAMA_BUILD_SERVER=ON"],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
                subprocess.run(["cmake", "--build", str(build), "--target", "llama-server", "-j", str(build_threads)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
            install = stage / "runtime"
            (install / "bin").mkdir(parents=True)
            (install / "model").mkdir()
            for file in (build / "bin").iterdir():
                if file.name == "llama-server" or ".so" in file.name:
                    shutil.copyfile(file, install / "bin" / file.name)
                    (install / "bin" / file.name).chmod(0o755)
            for name in MODEL_ASSETS:
                shutil.copyfile(cache / name, install / "model" / name)
            files = {}
            for file in sorted(install.glob("*/*")):
                files[str(file.relative_to(install))] = {
                    "size_bytes": file.stat().st_size, "mtime_ns": file.stat().st_mtime_ns,
                    "sha256": file_sha256(file),
                }
            (install / "runtime.json").write_text(json.dumps({
                "runtime_id": RUNTIME_ID, "model_revision": MODEL_REVISION,
                "llama_revision": LLAMA_REVISION, "files": files,
            }, indent=2) + "\n")
            validate_runtime(install, verify_hashes=True)
            subprocess.run([str(install / "bin/llama-server"), "--version"],
                           env=dict(os.environ, LD_LIBRARY_PATH=str(install / "bin")),
                           capture_output=True, check=True, timeout=15)
            for file in install.glob("*/*"):
                file.chmod(0o555 if file.parent.name == "bin" else 0o444)
            (install / "runtime.json").chmod(0o444)
            os.rename(install, root)
        print(f"Pinned offline model runtime ready: {root}", flush=True)


def smoke(root: Path, *, threads: int = DEFAULT_THREADS) -> dict:
    """Exercise the actual worker processor using generated media, never recordings."""
    from rosbag_analyser.processors.ai_description import DescriptionProcessor
    with tempfile.TemporaryDirectory(prefix="qwen-smoke-") as temporary:
        directory = Path(temporary)
        video = directory / "synthetic.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=448x336:rate=2:duration=3", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", str(video)], check=True, timeout=30)
        started = time.monotonic()
        try:
            with video.open("rb") as stream:
                result = DescriptionProcessor(root, Path("ffmpeg"), Path("ffprobe"), threads=threads).process(
                    stream.fileno(), directory / "description.json")
        except RuntimeError:
            log = directory / "inference.log"
            if log.is_file():
                import sys
                print("Synthetic inference diagnostics:\n" + log.read_text(errors="replace")[-6000:], file=sys.stderr)
            raise
        return {"runtime_id": RUNTIME_ID, "frames": FRAME_COUNT, "max_side": MAX_FRAME_SIDE,
                "threads": threads, "elapsed_seconds": round(time.monotonic() - started, 2),
                "result": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "check", "smoke"))
    parser.add_argument("--runtime-root", type=Path, default=Path(
        os.environ.get("ROS_BAG_ANALYSER_DESCRIPTION_RUNTIME_ROOT") or
        default_runtime_root(deployment=os.environ.get("ROS_BAG_ANALYSER_DEPLOYMENT_MODE") == "1")))
    parser.add_argument("--cache", type=Path, default=Path.home() / ".cache/rosbag-analyser/setup")
    parser.add_argument("--build-threads", type=int, default=4)
    parser.add_argument("--threads", type=int, default=os.environ.get("ROS_BAG_ANALYSER_DESCRIPTION_THREADS", DEFAULT_THREADS))
    args = parser.parse_args()
    if not 1 <= args.build_threads <= 32:
        parser.error("--build-threads must be between 1 and 32")
    if not 1 <= args.threads <= 32:
        parser.error("--threads must be between 1 and 32")
    try:
        if args.action == "setup":
            provision(args.runtime_root, args.cache, build_threads=args.build_threads)
        elif args.action == "check":
            validate_runtime(args.runtime_root, verify_hashes=True)
            print("Pinned model runtime checksums verified.")
        else:
            print(json.dumps(smoke(args.runtime_root, threads=args.threads), indent=2))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Model setup failed: {error}. Build diagnostics: {args.cache / 'build.log'}") from error


if __name__ == "__main__":
    main()
