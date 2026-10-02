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


ssh_transport = load("vm_ssh")
sys.modules["vm_ssh"] = ssh_transport
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
    command = ssh_transport.ssh_command({"SSH": "/usr/bin/ssh", "USER": "operator", "HOST": "vm.example.invalid"},
                                        ["python3", "-c", ssh_transport.RUN])
    parsed = shlex.split(command[-1])
    assert parsed[:2] == ["python3", "-c"]
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
def test_ssh_round_trip_saves_private_report_and_failure_output(tmp_path, monkeypatch, capsys, failure):
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text("#!/usr/bin/env python3\nimport json,sys\n"
                        "envelope=json.load(sys.stdin)\nrequest=json.loads(envelope['stdin'])\nassert request['action']=='status'\n"
                        "assert 'sudo' not in sys.argv[-1]\n"
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
        assert "connection failed" in capsys.readouterr().err
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


@pytest.mark.parametrize("interactive", [False, True])
def test_sudo_transport_preserves_input_output_exit_and_cleans_up(tmp_path, monkeypatch, interactive):
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text("#!/usr/bin/env python3\nimport subprocess,sys\n"
                        "assert len(sys.argv[-1]) < 5000\n"
                        "sys.exit(subprocess.call(sys.argv[-1],shell=True))\n")
    fake_ssh.chmod(0o755)
    sudo = tmp_path / "sudo"
    sudo.write_text("#!/usr/bin/env python3\nimport os,sys\n"
                   "os.execvp(sys.argv[2],sys.argv[2:])\n")
    sudo.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + os.environ["PATH"])
    monkeypatch.setattr(ssh_transport, "terminal", lambda: open(os.devnull, "r+b") if interactive else None)
    before = set(Path('/tmp').glob('rosbag-vm-*'))
    argument = "$(touch SHOULD_NOT_EXIST); 'quoted'"
    script = "import sys; print(sys.argv[1]); print(sys.stdin.read()); print('note',file=sys.stderr); sys.exit(7)\n#" + "x" * 40000
    result = ssh_transport.run({"SSH": str(fake_ssh), "USER": "operator", "HOST": "local.test"},
                               [sys.executable, "-c", script, argument], b"request data", sudo=True, timeout=10)
    assert result.returncode == 7
    assert result.stdout.decode() == argument + "\nrequest data\n"
    assert result.stderr == b"note\n"
    assert set(Path('/tmp').glob('rosbag-vm-*')) == before


def test_sudo_without_terminal_explains_password_requirement(tmp_path, monkeypatch):
    fake_ssh = tmp_path / "ssh"
    fake_ssh.write_text("#!/bin/sh\necho 'sudo: a password is required' >&2\nexit 1\n")
    fake_ssh.chmod(0o755)
    monkeypatch.setattr(ssh_transport, "terminal", lambda: None)
    result = ssh_transport.run({"SSH": str(fake_ssh), "USER": "operator", "HOST": "local.test"},
                               ["python3"], b"", sudo=True, timeout=10)
    assert result.returncode == 1
    assert b"interactive terminal" in result.stderr


def test_status_preserves_observed_failure_and_reports_missing_information(monkeypatch):
    monkeypatch.setattr(remote, "command_text", lambda _: "LoadState=loaded\nActiveState=failed\nSubState=failed\n")
    monkeypatch.setattr(remote, "health", lambda _: {"http_status": 503, "body": {"status": "unavailable"}})
    result = remote.status_report({"release_id": "test"})
    assert result["complete"] and result["exit_code"] == 0
    assert "ActiveState=failed" in next(iter(result["services"].values()))
    assert result["health"]["ready"]["http_status"] == 503
    def denied(_):
        raise ValueError("Permission denied")
    monkeypatch.setattr(remote, "command_text", denied)
    result = remote.status_report({"available": False, "error": "Permission denied"})
    assert not result["complete"] and result["exit_code"] == 1
    assert "Permission denied" in result["error"]
    assert result["health"]["ready"]["http_status"] == 503


def test_journal_failure_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(remote.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b"Permission denied"))
    with pytest.raises(ValueError, match="Permission denied"):
        remote.sanitized_logs()


@pytest.mark.parametrize("path,allowed", [("tools/check.py", True), ("jetbrains/styles.css", True),
                                          ("tests/unit/test_vm_workflow.py", True), ("frontend/tests/clock.spec.ts", True),
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


@pytest.mark.parametrize('interactive', [False, True])
def test_deployment_backup_is_verified_off_vm_before_upgrade_can_continue(tmp_path, monkeypatch, interactive):
    fake_ssh = tmp_path / 'ssh'
    fake_ssh.write_text("#!/usr/bin/env python3\nimport subprocess,sys\nsys.exit(subprocess.call(sys.argv[-1],shell=True))\n")
    fake_ssh.chmod(0o755)
    sudo = tmp_path / 'sudo'
    sudo.write_text("#!/usr/bin/env python3\nimport os,sys\nos.execvp(sys.argv[2],sys.argv[2:])\n")
    sudo.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + ':' + os.environ['PATH'])
    monkeypatch.setattr(ssh_transport, 'terminal', lambda: open(os.devnull, 'r+b') if interactive else None)
    source = ROOT / 'deploy/scripts/deploy_release.py'
    script = (
        "import importlib.util,os,tempfile\nfrom pathlib import Path\n"
        f"spec=importlib.util.spec_from_file_location('upgrade',{str(source)!r})\n"
        "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
        "with tempfile.TemporaryDirectory() as temporary:\n"
        "    dump=Path(temporary)/'original.dump';dump.write_bytes(b'recovery fixture'*100000)\n"
        "    module.publish_backup(dump,Path(os.environ['ROS_BAG_ANALYSER_DEPLOY_TRANSFER_DIRECTORY']),timeout=15)\n"
        "    print('migration allowed')\n"
    )
    target = tmp_path / 'report'
    result = ssh_transport.run({'SSH': str(fake_ssh), 'USER': 'operator', 'HOST': 'local.test'},
                               [sys.executable, '-c', script], b'', sudo=True, timeout=25,
                               deployment_backup=target)
    assert result.returncode == 0, result.stderr
    assert b'migration allowed' in result.stdout
    assert (target / 'database.dump').read_bytes() == b'recovery fixture'*100000
    assert target.stat().st_mode & 0o777 == 0o700
    assert (target / 'database.dump').stat().st_mode & 0o777 == 0o600
    assert (target / 'backup.json').stat().st_mode & 0o777 == 0o600


def test_corrupt_backup_never_acknowledges_migration_or_replaces_valid_output(tmp_path):
    fake_ssh = tmp_path / 'ssh'
    fake_ssh.write_text("#!/usr/bin/env python3\nimport subprocess,sys\nsys.exit(subprocess.call(sys.argv[-1],shell=True))\n")
    fake_ssh.chmod(0o755)
    remote_dir = tmp_path / 'transfer'
    remote_dir.mkdir(mode=0o700)
    (remote_dir / 'backup.dump').write_bytes(b'corrupt data')
    (remote_dir / 'backup.dump').chmod(0o600)
    local_dir = tmp_path / 'local'
    local_dir.mkdir(mode=0o700)
    (local_dir / 'database.dump').write_bytes(b'previous valid copy')
    import hashlib
    identity = {'size': len(b'corrupt data'), 'sha256': hashlib.sha256(b'correct data').hexdigest()}
    with pytest.raises(ValueError, match='checksum'):
        ssh_transport.receive_backup({'SSH': str(fake_ssh), 'USER': 'operator', 'HOST': 'local.test'},
                                     str(remote_dir), local_dir, identity)
    assert not (remote_dir / 'backup-ack.json').exists()
    assert (local_dir / 'database.dump').read_bytes() == b'previous valid copy'
    assert not list(local_dir.glob('*.partial'))
