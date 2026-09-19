from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

from conftest import create_recording

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vm = load("vm")
remote = load("vm_remote")
runner = load("vm_diagnostic")


def test_help_needs_no_vm_and_source_selection_is_explicit():
    completed = subprocess.run([str(ROOT / "vm"), "--help"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert "front-headers" in completed.stdout
    with pytest.raises(ValueError, match="Select a recording"):
        vm.make_request(vm.parser().parse_args(["topics"]))
    for value in ("../bag", "/source/bag", "a//b", "a/./b"):
        with pytest.raises(ValueError, match="archive-relative"):
            vm.make_request(vm.parser().parse_args(["topics", "--recording", value]))


def test_local_script_arguments_and_spaces_remain_data(tmp_path):
    script = tmp_path / "bug check.py"
    script.write_text("print('diagnosis')\n")
    dangerous_argument = "$(touch SHOULD_NOT_EXIST); 'quoted'"
    request = vm.make_request(vm.parser().parse_args([
        "run", "--recording", "folder/my bag", str(script), "--", dangerous_argument]))
    assert request["args"] == [dangerous_argument]
    assert request["recordings"] == ["folder/my bag"]
    command = vm.ssh_command({"SSH": "/usr/bin/ssh", "USER": "operator", "HOST": "vm.example.invalid"})
    parsed = shlex.split(command[-1])
    assert parsed[:4] == ["sudo", "--non-interactive", "python3", "-c"]
    assert "exec(bytes.fromhex(" in parsed[-1]
    assert dangerous_argument not in command[-1]


def test_private_settings_load_without_exposing_values(tmp_path, monkeypatch):
    config = tmp_path / "settings"
    config.write_text("ROS_BAG_ANALYSER_VM_DEPLOY_HOST=vm.example.invalid\n"
                      "ROS_BAG_ANALYSER_VM_DEPLOY_USER=operator\n"
                      "ROS_BAG_ANALYSER_VM_DEPLOY_BRANCH=main\n"
                      f"ROS_BAG_ANALYSER_VM_DEPLOY_SSH={sys.executable}\n")
    monkeypatch.setenv("ROS_BAG_ANALYSER_VM_DEPLOY_SETTINGS_FILE", str(config))
    config.chmod(0o644)
    with pytest.raises(ValueError, match="0600"):
        vm.connection_settings()
    config.chmod(0o600)
    assert vm.connection_settings()["HOST"] == "vm.example.invalid"


@pytest.mark.parametrize("failure", [False, True])
def test_ssh_round_trip_saves_private_report_and_failure_output(tmp_path, monkeypatch, failure):
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text("#!/usr/bin/env python3\nimport json,sys\n"
                        "request=json.load(sys.stdin)\nassert request['action']=='status'\n"
                        + ("print('connection failed',file=sys.stderr);sys.exit(255)\n" if failure else
                           "print(json.dumps({'exit_code':0,'stdout':'collected data','stderr':'note','release':{'release_id':'test'}}))\n"))
    fake_ssh.chmod(0o755)
    monkeypatch.setattr(vm, "connection_settings", lambda: {"SSH": str(fake_ssh), "USER": "operator", "HOST": "local.test"})
    target = tmp_path / "report"
    assert vm.main(["status", "--output", str(target)]) == (255 if failure else 0)
    report = json.loads((target / "report.json").read_text())
    assert report["exit_code"] == (255 if failure else 0)
    assert target.stat().st_mode & 0o777 == 0o700
    assert (target / "report.json").stat().st_mode & 0o777 == 0o600
    if failure:
        assert "connection failed" in (target / "ssh-stderr.txt").read_text()
    else:
        assert (target / "stdout.txt").read_text() == "collected data"
    assert "report.json" in (target / "SHA256SUMS").read_text()
    assert vm.main(["status", "--output", str(target)]) == 1


def diagnostic_fixture(tmp_path, monkeypatch):
    archive = tmp_path / "source"
    archive.mkdir()
    create_recording(archive, "bag")
    settings = {"ROS_BAG_ANALYSER_ARCHIVE_ROOT": str(archive),
                "ROS_BAG_ANALYSER_FRONT_TOPIC": "/front", "ROS_BAG_ANALYSER_IMU_TOPIC": "/imu"}
    release = tmp_path / "release"
    release.mkdir()
    (release / "venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    monkeypatch.setattr(remote, "CURRENT", release)
    monkeypatch.setattr(remote, "read_settings", lambda: settings)
    monkeypatch.setattr(remote.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(remote.pwd, "getpwnam", lambda _: SimpleNamespace(pw_gid=os.getgid(), pw_uid=os.getuid()))
    monkeypatch.setattr(remote.os, "chown", lambda *args: None)
    monkeypatch.setattr(remote.os, "statvfs", lambda _: SimpleNamespace(f_flag=os.ST_RDONLY))
    original_directory = tempfile.TemporaryDirectory
    monkeypatch.setattr(remote.tempfile, "TemporaryDirectory", lambda **kwargs: original_directory(dir=tmp_path))
    return archive


@pytest.mark.parametrize("action", ["topics", "failure", "timeout"])
def test_remote_runner_preserves_sources_and_reports_failure(tmp_path, monkeypatch, action):
    archive = diagnostic_fixture(tmp_path, monkeypatch)
    script = tmp_path / "check.py"
    script.write_text("import sys\nprint('diagnostic output')\nsys.exit(7)\n" if action == "failure" else
                      "import time\ntime.sleep(5)\n")
    args = (["topics", "--recording", "bag"] if action == "topics" else
            ["run", "--recording", "bag", "--timeout", "1" if action == "timeout" else "10", str(script)])
    request = vm.make_request(vm.parser().parse_args(args))
    def simulated_systemd(command, timeout, stop):
        assert "--property=User=rosbag-analyser" in command
        assert "--property=ProtectSystem=strict" in command
        assert "--property=PrivateNetwork=yes" in command
        assert "--property=NoNewPrivileges=yes" in command
        assert "--property=KillMode=control-group" in command
        script_path = Path(command[-1])
        result = subprocess.run([sys.executable, "-B", str(script_path)], cwd=script_path.parent,
                                capture_output=True, text=True, timeout=10)
        return {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    monkeypatch.setattr(remote, "capture", simulated_systemd)
    result = remote.run_diagnostic(request)
    assert result["exit_code"] == {"topics": 0, "failure": 7, "timeout": 1}[action]
    assert result["source_inventory"]["unchanged"] is True
    assert result["source_inventory"]["before"][0]["entry_count"] > 0
    assert not list(archive.rglob("*-journal"))
    if action == "failure":
        assert "diagnostic output" in result["stdout"]
    if action == "timeout":
        assert "TimeoutError" in result["stderr"]


def test_source_selection_rejects_symlinks_and_reserved_cache(tmp_path):
    (tmp_path / "bag").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "bag", target_is_directory=True)
    for selection in ("link", "Rosbag_Analyser_Cache", "../elsewhere"):
        with pytest.raises(ValueError):
            runner.selected_roots(tmp_path, [selection])


def test_capture_stops_on_output_limit_and_timeout(monkeypatch):
    monkeypatch.setattr(remote, "MAX_OUTPUT", 1024)
    stopped = []
    result = remote.capture([sys.executable, "-c", "print('x'*10000)"], 5, lambda: stopped.append(True))
    assert len(result["stdout"]) <= 1024
    assert result["exit_code"] != 0 and stopped
    result = remote.capture([sys.executable, "-c", "import time; time.sleep(10)"], .1, lambda: stopped.append(True))
    assert result["exit_code"] == 124 and len(stopped) == 2


def test_log_redaction(monkeypatch):
    monkeypatch.setattr(remote, "command_text", lambda _: "password=secret /private/source/bag failed\n")
    assert "secret" not in remote.sanitized_logs()
    assert "/private/source" not in remote.sanitized_logs()


@pytest.mark.parametrize("path,allowed", [("tools/check.py", True), ("jetbrains/styles.css", True),
                                          ("tests/unit/test_vm_workflow.py", True),
                                          ("src/rosbag_analyser/worker.py", False),
                                          ("deploy/environment.example", False)])
def test_deploy_guard_ignores_local_tooling_but_protects_runtime(tmp_path, path, allowed):
    launcher = (ROOT / "deploy-vm").read_text()
    guard = launcher.split("require_deployable_worktree() {", 1)[1].split('\n[[ "${1:-}"', 1)[0]
    git = tmp_path / "git"
    git.write_text("#!/bin/sh\nprintf '%s\\n' \"$CHANGED_PATH\"\n")
    git.chmod(0o755)
    command = 'fail() { echo "$*"; exit 1; }; project_root=.; require_deployable_worktree() {' + guard + '\nrequire_deployable_worktree'
    result = subprocess.run(["bash", "-c", command], env=dict(os.environ, PATH=str(tmp_path) + ":" + os.environ["PATH"],
                             CHANGED_PATH=path), capture_output=True, text=True)
    assert (result.returncode == 0) == allowed, result.stdout + result.stderr


def test_deploy_uses_committed_bootstrap():
    launcher = (ROOT / "deploy-vm").read_text()
    assert 'git -C "$project_root" show "$local_revision:deploy/scripts/deploy-from-git"' in launcher
    assert 'bash -s -- "$deploy_branch" "$local_revision"' in launcher
