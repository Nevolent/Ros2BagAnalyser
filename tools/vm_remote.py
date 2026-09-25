"""Standalone SSH receiver. Streamed from the workstation; never installed as a service."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import shlex

CURRENT = Path("/opt/rosbag-analyser/current")
CONFIG = Path("/etc/rosbag-analyser/application.env")
MAX_OUTPUT = 8 * 1024 * 1024
SERVICES = ("rosbag-analyser-api.service", "rosbag-analyser-worker.service", "rosbag-analyser-preflight.service")


def read_settings(path: Path = CONFIG) -> dict[str, str]:
    selected = {}
    allowed = {"ROS_BAG_ANALYSER_" + name for name in ("ARCHIVE_ROOT", "FRONT_TOPIC", "IMU_TOPIC")}
    for line in path.read_text().splitlines():
        key = line.partition("=")[0].strip()
        if key not in allowed:
            continue
        words = shlex.split(line, comments=True)
        if len(words) != 1 or "=" not in words[0]:
            raise ValueError("Unsupported diagnostic setting syntax in application.env.")
        selected[key] = words[0].partition("=")[2]
    if allowed - selected.keys():
        raise ValueError("Source root and front/IMU topics must be configured on the VM.")
    source = Path(selected["ROS_BAG_ANALYSER_ARCHIVE_ROOT"])
    if not source.is_absolute() or source.resolve(strict=True) != source:
        raise ValueError("The configured source path is not canonical.")
    return selected


def command_text(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"{command[0]} unavailable: {error}") from error
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:2000]
        raise ValueError(f"{command[0]} failed (exit {result.returncode}): {detail}")
    if len(result.stdout) > MAX_OUTPUT:
        raise ValueError(f"{command[0]} output exceeded the report limit.")
    return result.stdout.decode("utf-8", errors="replace")


def health(endpoint: str) -> dict:
    try:
        try:
            response = urllib.request.urlopen("http://127.0.0.1:8000/health/" + endpoint, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(65_537)
            if len(body) > 65_536:
                raise ValueError("Oversized health response")
            document = json.loads(body)
            if not isinstance(document, dict) or not isinstance(document.get("status"), str):
                raise ValueError("Invalid health response")
            return {"http_status": response.code, "body": document}
    except (OSError, ValueError) as error:
        return {"available": False, "error": str(error)}


def status_report(release: dict) -> dict:
    errors = {}
    if release.get("available") is False:
        errors["release"] = release["error"]
    services = {}
    for name in SERVICES:
        try:
            services[name] = command_text(["systemctl", "show", name,
                            "--property=LoadState,ActiveState,SubState,UnitFileState"]).strip()
            properties = dict(line.split("=", 1) for line in services[name].splitlines() if "=" in line)
            if not all(properties.get(key) for key in ("LoadState", "ActiveState", "SubState")):
                raise ValueError("Incomplete systemctl response")
        except ValueError as error:
            services[name] = "unavailable"
            errors[name] = str(error)
    checks = {name: health(name) for name in ("live", "ready")}
    for name, value in checks.items():
        if value.get("available") is False:
            errors["health/" + name] = value["error"]
    result = dict(exit_code=1 if errors else 0, complete=not errors, services=services, health=checks)
    if errors:
        result.update(collection_errors=errors, error="Status report is incomplete: " +
                      "; ".join(f"{name}: {error}" for name, error in errors.items()))
    return result


def sanitized_logs() -> str:
    text = command_text(["journalctl", "-u", SERVICES[0], "-u", SERVICES[1],
                         "--lines=200", "--no-pager", "--output=short-iso"])
    text = re.sub(r"postgresql(?:\+[A-Za-z0-9_.-]+)?://\S+", "[database-url]", text, flags=re.I)
    text = re.sub(r"(?i)\b(authorization|cookie|password|secret|token|private[_ -]?key)\s*[:=]\s*\S+",
                  lambda m: m[1] + "=[redacted]", text)
    return re.sub(r'''(?<![A-Za-z0-9_:.])/(?:[^\s:'"<>]+/?)+''', "[path]", text)


def capture(command: list[str], timeout: int, stop) -> dict:
    """Bound stdout/stderr together, and stop the whole transient unit on failure."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    streams = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    for name in buffers:
        streams.register(getattr(process, name), selectors.EVENT_READ, name)
    deadline = time.monotonic() + timeout
    error = None
    total = 0
    try:
        while streams.get_map():
            if time.monotonic() >= deadline:
                error = "Diagnostic exceeded its runtime limit."
                break
            for key, _ in streams.select(timeout=0.1):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    streams.unregister(key.fileobj)
                    continue
                remaining = MAX_OUTPUT - total
                buffers[key.data].extend(data[:remaining])
                total += min(len(data), remaining)
                if len(data) > remaining:
                    error = "Diagnostic output exceeded 8 MiB; retained output is partial."
                    break
            if error:
                break
        if error:
            stop()
            process.kill()
        try:
            code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            stop()
            process.kill()
            process.wait()
            error, code = "Diagnostic exceeded its runtime limit.", 124
    finally:
        streams.close()
        process.stdout.close()
        process.stderr.close()
    result = {key: value.decode("utf-8", errors="replace") for key, value in buffers.items()}
    result["exit_code"] = 124 if error else code
    if error:
        result["error"] = error
    return result


def run_diagnostic(request: dict) -> dict:
    release = CURRENT.resolve(strict=True)
    python = release / "venv/bin/python"
    if not python.is_file() or not shutil.which("systemd-run"):
        raise ValueError("Installed release Python and systemd-run are required.")
    settings = read_settings()
    source = settings["ROS_BAG_ANALYSER_ARCHIVE_ROOT"]
    if request["recordings"] and not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError("The configured source mount is not read-only.")
    account = pwd.getpwnam("rosbag-analyser")
    unit = "rosbag-diagnostic-" + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix="rosbag-diagnostic-", dir="/run") as temporary:
        workspace = Path(temporary)
        workspace.chmod(0o750)
        os.chown(workspace, 0, account.pw_gid)
        output = workspace / "result"
        output.mkdir(mode=0o700)
        os.chown(output, account.pw_uid, account.pw_gid)
        payload = dict(request, settings=settings)
        for name, text in (("script.py", request["script"]), ("runner.py", request["runner"]),
                           ("request.json", json.dumps(payload))):
            path = workspace / name
            path.write_text(text)
            path.chmod(0o640)
            os.chown(path, 0, account.pw_gid)
        command = ["systemd-run", "--quiet", "--pipe", "--wait", "--collect", "--service-type=exec",
                   "--unit=" + unit, "--property=User=rosbag-analyser", "--property=Group=rosbag-analyser",
                   "--property=UMask=0077", "--property=ProtectSystem=strict", "--property=ProtectHome=yes",
                   "--property=PrivateTmp=yes", "--property=PrivateNetwork=yes", "--property=NoNewPrivileges=yes",
                   "--property=KillMode=control-group", "--property=MemoryMax=1G", "--property=TasksMax=64",
                   "--property=RuntimeMaxSec=" + str(request["timeout"] + 10), "--property=TimeoutStopSec=5",
                   "--property=ReadWritePaths=" + str(output),
                   "--property=WorkingDirectory=" + str(workspace)]
        inaccessible = "-/etc/rosbag-analyser -/run/postgresql -/var/lib/postgresql"
        if not request["recordings"]:
            # Scripts without a source selection cannot traverse the archive.
            inaccessible += ' "' + source.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        command.append("--property=InaccessiblePaths=" + inaccessible)
        command.extend(["/bin/bash", "-c", 'source /opt/ros/humble/setup.bash && exec "$@"',
                        "vm-diagnostic", str(python), "-B", str(workspace / "runner.py")])
        def stop():
            try:
                subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass  # RuntimeMaxSec still bounds the entire remote cgroup.
        result = capture(command, request["timeout"] + 25, stop)
        inventory = output / "inventory.json"
        try:
            descriptor = os.open(inventory, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor) as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError
                text = stream.read(1_048_577)
                if len(text) > 1_048_576:
                    raise ValueError
                result["source_inventory"] = json.loads(text)
        except (OSError, ValueError):
            result["source_inventory"] = {"complete": False}
        if request["recordings"] and not result["source_inventory"].get("unchanged"):
            result["exit_code"] = result["exit_code"] or 1
        return result


def main() -> None:
    result = {"schema_version": 1, "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        payload = sys.stdin.buffer.read(1_048_577)
        if len(payload) > 1_048_576:
            raise ValueError("Diagnostic request exceeds 1 MiB.")
        request = json.loads(payload)
        if request["action"] not in ("status", "logs", "topics", "front-headers", "run"):
            raise ValueError("Unknown VM action.")
        if not isinstance(request["timeout"], int) or not 1 <= request["timeout"] <= 3600:
            raise ValueError("Invalid runtime limit.")
        try:
            release = json.loads((CURRENT / "release-manifest.json").read_text())
            keys = ("release_id", "source_revision", "application_version")
            if not isinstance(release, dict) or not all(isinstance(release.get(key), str) and release[key] for key in keys):
                raise ValueError("Invalid release manifest")
            result["release"] = {key: release[key] for key in keys}
        except (OSError, ValueError) as error:
            result["release"] = {"available": False, "error": str(error)}
        if request["action"] == "status":
            result.update(status_report(result["release"]))
        elif request["action"] == "logs":
            result.update(exit_code=0, stdout=sanitized_logs())
        else:
            result.update(run_diagnostic(request))
    except Exception as error:
        result.update(exit_code=1, error=f"VM diagnostic setup failed: {type(error).__name__}: {error}")
    result["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
