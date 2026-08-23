#!/usr/bin/env python3
"""Collect bounded deployment facts without copying journal messages or secrets."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


SERVICE_NAMES = (
    "rosbag-analyser-api.service",
    "rosbag-analyser-worker.service",
    "rosbag-analyser.target",
    "nginx.service",
    "postgresql.service",
)
VERSION_COMMANDS = {
    "operating_system": ("lsb_release", "--description", "--short"),
    "python": (sys.executable, "--version"),
    "pip": (sys.executable, "-m", "pip", "--version"),
    "ffmpeg": ("ffmpeg", "-version"),
    "ffprobe": ("ffprobe", "-version"),
    "postgresql_client": ("psql", "--version"),
    "nginx": ("nginx", "-v"),
    "ros_humble_rclpy": (
        "dpkg-query",
        "--show",
        "--showformat=${Version}",
        "ros-humble-rclpy",
    ),
    "ros_humble_sensor_msgs": (
        "dpkg-query",
        "--show",
        "--showformat=${Version}",
        "ros-humble-sensor-msgs",
    ),
}


def _run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )


def _first_line(command: tuple[str, ...]) -> dict[str, object]:
    try:
        result = _run(command)
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False}
    output = (result.stdout or result.stderr).splitlines()
    return {
        "available": result.returncode == 0,
        "version": output[0][:240] if output else "unavailable",
    }


def _service_state(name: str) -> dict[str, str]:
    state: dict[str, str] = {}
    for property_name in ("ActiveState", "SubState", "UnitFileState"):
        try:
            result = _run(
                (
                    "systemctl",
                    "show",
                    name,
                    f"--property={property_name}",
                    "--value",
                )
            )
        except (OSError, subprocess.TimeoutExpired):
            state[property_name] = "unavailable"
            continue
        state[property_name] = (
            result.stdout.strip()[:80] if result.returncode == 0 else "unavailable"
        )
    return state


def _journal_metadata(name: str) -> list[dict[str, str]]:
    try:
        result = _run(
            (
                "journalctl",
                "--unit",
                name,
                "--lines=1000",
                "--output=json",
                "--output-fields=__REALTIME_TIMESTAMP,PRIORITY,_SYSTEMD_UNIT",
                "--no-pager",
            )
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    events: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        try:
            source = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(
            {
                key: str(source[key])[:80]
                for key in ("__REALTIME_TIMESTAMP", "PRIORITY", "_SYSTEMD_UNIT")
                if key in source
            }
        )
    return events


def _health(base_url: str, endpoint: str) -> dict[str, object]:
    try:
        with urllib.request.urlopen(base_url + endpoint, timeout=5) as response:
            payload = response.read(65_537)
            if len(payload) > 65_536:
                return {"available": False, "error": "response_too_large"}
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise ValueError
            return document
    except urllib.error.HTTPError as error:
        if error.code != 503:
            return {"available": False, "error": "health_unavailable"}
        try:
            payload = error.read(65_537)
            if len(payload) > 65_536:
                raise ValueError
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise ValueError
            return document
        except (OSError, ValueError, json.JSONDecodeError):
            return {"available": False, "error": "health_unavailable"}
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return {"available": False, "error": "health_unavailable"}


def _release_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[2] / "deploy" / "release-contract.json"
    try:
        if path.is_symlink():
            raise OSError
        payload = path.read_bytes()
        if len(payload) > 64 * 1024:
            raise OSError
        document = json.loads(payload)
        if not isinstance(document, dict):
            raise ValueError
        return document
    except (OSError, ValueError, json.JSONDecodeError):
        return {"available": False}


def build_bundle(base_url: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "collected_at": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "privacy": {
            "journal_messages_included": False,
            "environment_included": False,
            "paths_addresses_credentials_included": False,
        },
        "health": {
            "live": _health(base_url, "/health/live"),
            "ready": _health(base_url, "/health/ready"),
        },
        "versions": {
            name: _first_line(command) for name, command in VERSION_COMMANDS.items()
        },
        "release_contract": _release_contract(),
        "services": {name: _service_state(name) for name in SERVICE_NAMES},
        "journal_event_metadata": {
            name: _journal_metadata(name)
            for name in (
                "rosbag-analyser-api.service",
                "rosbag-analyser-worker.service",
            )
        },
    }


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("Usage: support_bundle.py OUTPUT_DIRECTORY [LOCAL_BASE_URL]")
    requested_output = Path(sys.argv[1])
    if not requested_output.is_absolute():
        raise SystemExit("The support-bundle output target must be absolute.")
    output = requested_output
    base_url = sys.argv[2] if len(sys.argv) == 3 else "http://127.0.0.1:8000"
    if base_url != "http://127.0.0.1:8000":
        raise SystemExit("Support collection accepts only the loopback application URL.")
    if output.exists() or output.is_symlink():
        raise SystemExit("The support-bundle output target already exists.")
    try:
        if output.parent.resolve(strict=True) != output.parent:
            raise OSError
    except OSError as error:
        raise SystemExit("The support-bundle output parent is unsafe.") from error
    try:
        output.mkdir(mode=0o700, parents=False)
        destination = output / "support.json"
        encoded = (
            json.dumps(build_bundle(base_url), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        destination.write_bytes(encoded)
        destination.chmod(0o600)
        checksum = hashlib.sha256(encoded).hexdigest()
        checksum_path = output / "SHA256SUMS"
        checksum_path.write_text(f"{checksum}  support.json\n", encoding="ascii")
        checksum_path.chmod(0o600)
    except OSError as error:
        raise SystemExit("Support metadata could not be written safely.") from error
    print("Sanitized support metadata collected; review it before sharing.")


if __name__ == "__main__":
    main()
