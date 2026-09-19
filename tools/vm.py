#!/usr/bin/env python3
"""Workstation entry point for VM deployment and private diagnostic reports."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "ROS_BAG_ANALYSER_VM_DEPLOY_"
MAX_SCRIPT_BYTES = 256 * 1024


def connection_settings() -> dict[str, str]:
    path = Path(os.environ.get(PREFIX + "SETTINGS_FILE", str(
        Path.home() / ".config/rosbag-analyser/vm-deploy.env")))
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o777 not in (0o400, 0o600):
        raise ValueError("VM settings must be a regular mode-0600/0400 file; see deploy/vm-deploy-environment.example.")
    # This is the same trusted, private shell configuration used by deploy-vm.
    loader = 'set -a; source "$1"; exec python3 -c "$2"'
    reader = 'import json,os; print(json.dumps({k:os.environ.get("' + PREFIX + '"+k,"") for k in ("HOST","USER","BRANCH","SSH")}))'
    loaded = subprocess.run(["bash", "-eu", "-c", loader, "vm-settings", str(path), reader],
                            capture_output=True, text=True, timeout=10)
    if loaded.returncode:
        raise ValueError("Could not load private VM settings.")
    settings = json.loads(loaded.stdout)
    for key, pattern in (("HOST", r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}"),
                         ("USER", r"[A-Za-z_][A-Za-z0-9_-]{0,31}"),
                         ("BRANCH", r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")):
        if not re.fullmatch(pattern, settings[key]):
            raise ValueError(f"Invalid VM {key.lower()} setting.")
    if not os.access(settings["SSH"], os.X_OK):
        raise ValueError("The configured SSH program is unavailable.")
    return settings


def ssh_command(settings: dict[str, str]) -> list[str]:
    source = (ROOT / "tools/vm_remote.py").read_bytes()
    remote = shlex.join(["sudo", "--non-interactive", "python3", "-c",
                         f"exec(bytes.fromhex('{source.hex()}'))"])
    return [settings["SSH"], "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "ConnectionAttempts=1", "-o", "StrictHostKeyChecking=yes",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
            f'{settings["USER"]}@{settings["HOST"]}', remote]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="./vm", description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    deploy = commands.add_parser("deploy", help="Deploy the committed revision using deploy-vm")
    deploy.add_argument("--push", action="store_true", help="Push this branch first (never commits files)")
    for name, description in (("status", "Save release, service and health facts"),
                              ("logs", "Save recent sanitized API/worker logs"),
                              ("topics", "Check selected recordings' configured topics"),
                              ("front-headers", "Inspect selected front-camera headers"),
                              ("run", "Send and run a local Python diagnostic, without deployment")):
        command = commands.add_parser(name, help=description)
        command.add_argument("--output", type=Path, help="New local report directory (default: .vm-reports/<run>)")
        command.add_argument("--timeout", type=int, default=300, help="Run limit in seconds (default: 300)")
        if name in ("topics", "front-headers", "run"):
            command.add_argument("--recording", action="append", default=[],
                                 help="Archive-relative recording directory; repeat to select several")
            command.add_argument("--max-entries", type=int, default=100_000,
                                 help="Source inventory entry bound per selection")
            command.add_argument("--max-depth", type=int, default=8)
        if name == "front-headers":
            command.add_argument("--max-messages", type=int, default=1_000_000)
        if name == "run":
            command.add_argument("script", type=Path)
            command.add_argument("args", nargs=argparse.REMAINDER, help="Script arguments after the script path")
    return result


def make_request(args: argparse.Namespace) -> dict:
    if not 1 <= args.timeout <= 3600:
        raise ValueError("Timeout must be between 1 and 3600 seconds.")
    recordings = getattr(args, "recording", [])
    if len(recordings) > 100 or len(set(recordings)) != len(recordings):
        raise ValueError("Select at most 100 distinct recording directories.")
    for relative in recordings:
        if (not relative or relative.startswith("/") or "\\" in relative
                or any(part in ("", ".", "..") for part in relative.split("/"))):
            raise ValueError("Recordings must be contained archive-relative directories.")
    if args.action in ("topics", "front-headers") and not recordings:
        raise ValueError("Select a recording with --recording; no implicit full-archive scan is performed.")
    request = {"action": args.action, "timeout": args.timeout, "recordings": recordings,
               "max_entries": getattr(args, "max_entries", 100_000),
               "max_depth": getattr(args, "max_depth", 8),
               "max_messages": getattr(args, "max_messages", 1_000_000), "args": []}
    if not 1 <= request["max_entries"] <= 2_000_000 or not 1 <= request["max_depth"] <= 64:
        raise ValueError("Invalid source inventory bounds.")
    if not 1 <= request["max_messages"] <= 10_000_000:
        raise ValueError("Invalid front message bound.")
    if args.action in ("topics", "front-headers", "run"):
        script = (args.script if args.action == "run" else ROOT / "deploy/scripts" /
                  ("topic_audit.py" if args.action == "topics" else "front_header_diagnostic.py"))
        if script.is_symlink() or not script.is_file() or script.suffix != ".py":
            raise ValueError("Choose a regular Python script.")
        source = script.read_bytes()
        if len(source) > MAX_SCRIPT_BYTES:
            raise ValueError("Diagnostic script exceeds 256 KiB.")
        request["script"] = source.decode("utf-8")
        request["script_sha256"] = hashlib.sha256(source).hexdigest()
        request["runner"] = (ROOT / "tools/vm_diagnostic.py").read_text()
        if args.action == "run":
            request["args"] = args.args[1:] if args.args[:1] == ["--"] else args.args
    return request


def save_report(directory: Path, request: dict, response: dict, transport: bytes) -> None:
    for name, content in (("stdout.txt", response.pop("stdout", "")),
                          ("stderr.txt", response.pop("stderr", "")),
                          ("ssh-stderr.txt", transport.decode("utf-8", errors="replace"))):
        path = directory / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o600)
    response["request"] = {key: value for key, value in request.items() if key not in ("script", "runner")}
    path = directory / "report.json"
    path.write_text(json.dumps(response, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    checksums = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
                 for p in sorted(directory.iterdir()) if p.is_file()]
    path = directory / "SHA256SUMS"
    path.write_text("".join(checksums))
    path.chmod(0o600)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "deploy":
            if args.push:
                subprocess.run([str(ROOT / "deploy-vm"), "--check"], cwd=ROOT, check=True)
                settings = connection_settings()
                branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
                if branch != settings["BRANCH"]:
                    raise ValueError("Checkout does not match the configured deployment branch.")
                subprocess.run(["git", "push", "origin", branch], cwd=ROOT, check=True)
            return subprocess.call([str(ROOT / "deploy-vm")], cwd=ROOT)
        request = make_request(args)
        settings = connection_settings()
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        directory = (args.output or ROOT / ".vm-reports" / f"{run_id}-{args.action}").absolute()
        if directory.exists() or directory.is_symlink():
            raise ValueError("Report directory already exists; choose a new one.")
        directory.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.mkdir(mode=0o700)
        print(f"Running {args.action}; local report: {directory}", flush=True)
        try:
            result = subprocess.run(ssh_command(settings), input=json.dumps(request).encode(),
                                    capture_output=True, timeout=args.timeout + 90)
            try:
                response = json.loads(result.stdout)
                if not isinstance(response, dict) or not isinstance(response.get("exit_code"), int):
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                response = {"exit_code": result.returncode or 1, "error": "No complete VM report received",
                            "stdout": result.stdout.decode("utf-8", errors="replace")}
            if result.returncode and not response["exit_code"]:
                response["exit_code"] = result.returncode
            transport = result.stderr
        except subprocess.TimeoutExpired as error:
            response = {"exit_code": 124, "error": "SSH timed out; remote diagnostic has an independent runtime limit.",
                        "stdout": (error.stdout or b"").decode("utf-8", errors="replace")}
            transport = error.stderr or b""
        except OSError:
            response, transport = {"exit_code": 1, "error": "Could not start SSH."}, b""
        save_report(directory, request, response, transport)
        code = response["exit_code"]
        print(f"{'Completed' if code == 0 else 'Failed'} (exit {code}). See {directory / 'report.json'}")
        if response.get("error"):
            print(response["error"], file=sys.stderr)
        return code if 0 <= code <= 255 else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"vm: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
