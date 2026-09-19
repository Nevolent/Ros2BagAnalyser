"""Runs inside the service-account sandbox with the installed ROS/Python runtime."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import sys
import traceback

from rosbag_analyser.source_manifest import build_source_manifest
from rosbag_analyser.storage_layout import is_reserved_cache_root_entry


def selected_roots(source: Path, recordings: list[str]) -> list[Path]:
    roots = []
    for relative in recordings:
        parts = relative.split("/")
        if (not relative or relative.startswith("/") or "\\" in relative
                or any(part in ("", ".", "..") for part in parts)
                or is_reserved_cache_root_entry(parts[0])):
            raise ValueError("Invalid source recording selection.")
        current = source
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Source selection contains a symbolic link.")
        current.resolve(strict=True).relative_to(source)
        if not current.is_dir():
            raise ValueError("Selected recording is not a directory.")
        roots.append(current)
    return roots


def inventory(roots: list[Path], request: dict) -> list[dict]:
    documents = []
    for relative, root in zip(request["recordings"], roots):
        entries = build_source_manifest(root, max_depth=request["max_depth"], max_entries=request["max_entries"])
        encoded = json.dumps([asdict(item) for item in entries], sort_keys=True, separators=(",", ":")).encode()
        documents.append({"recording": relative, "entry_count": len(entries), "sha256": hashlib.sha256(encoded).hexdigest()})
    return documents


def main() -> int:
    workspace = Path(__file__).resolve().parent
    request = json.loads((workspace / "request.json").read_text())
    settings = request["settings"]
    source = Path(settings["ROS_BAG_ANALYSER_ARCHIVE_ROOT"])
    roots = selected_roots(source, request["recordings"])
    evidence = {"before": inventory(roots, request), "complete": False}
    destination = workspace / "result/inventory.json"
    destination.write_text(json.dumps(evidence))
    arguments = list(request["args"])
    if request["action"] in ("topics", "front-headers"):
        arguments = ["--archive-root", str(source), "--front-topic", settings["ROS_BAG_ANALYSER_FRONT_TOPIC"]]
        for relative in request["recordings"]:
            arguments.extend(["--recording", relative])
        if request["action"] == "topics":
            arguments.extend(["--imu-topic", settings["ROS_BAG_ANALYSER_IMU_TOPIC"]])
        else:
            arguments.extend(["--max-messages", str(request["max_messages"])])
    os.environ.update(settings)
    os.environ["VM_DIAGNOSTIC_RECORDINGS"] = json.dumps(request["recordings"])
    sys.argv = [str(workspace / "script.py"), *arguments]
    code = 0
    def expired(_signal, _frame):
        raise TimeoutError("Diagnostic runtime limit reached.")
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(request["timeout"])
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
        if error.code and not isinstance(error.code, int):
            print(error.code, file=sys.stderr)
    except Exception:
        traceback.print_exc()
        code = 1
    finally:
        signal.alarm(0)
        try:
            evidence["after"] = inventory(roots, request)
            evidence.update(complete=True, unchanged=evidence["before"] == evidence["after"])
            if not evidence["unchanged"]:
                print("Source inventory changed during diagnosis.", file=sys.stderr)
                code = 1
        except Exception:
            traceback.print_exc()
            code = 1
        destination.write_text(json.dumps(evidence))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
