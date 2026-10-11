from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
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
    assert "recover" in completed.stdout
    with pytest.raises(ValueError, match="Select a recording"):
        vm.make_request(vm.parser().parse_args(["topics"]))
    for value in ("../bag", "/source/bag", "a//b", "a/./b"):
        with pytest.raises(ValueError, match="archive-relative"):
            vm.make_request(vm.parser().parse_args(["topics", "--recording", value]))


@pytest.mark.parametrize('candidate', [False, True])
def test_recovery_uses_existing_sudo_transport_without_deployment_backup(monkeypatch, candidate):
    monkeypatch.setattr(vm, 'connection_settings', lambda: {'HOST': 'fixture'})
    calls = []

    def run(settings, command, payload, **kwargs):
        calls.append((settings, command, payload, kwargs))
        return subprocess.CompletedProcess(command, 0, b'', b'')
    monkeypatch.setattr(vm.vm_ssh, 'run', run)
    assert vm.main(['recover'] + (['--candidate'] if candidate else [])) == 0
    assert len(calls) == 1
    assert calls[0][1][:2] == ['python3', '-c']
    assert 'def recover(' in calls[0][1][2]
    assert calls[0][1][3:] == (['--candidate'] if candidate else [])
    assert calls[0][3] == {'sudo': True, 'capture_output': False}


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


def test_logs_keep_a_separate_worker_snapshot_when_api_access_is_busy(monkeypatch):
    units = []

    def journal(command):
        assert command.count('-u') == 1
        unit = command[command.index('-u') + 1]
        units.append(unit)
        return ('HTTP 200\n' * 200 if unit == remote.SERVICES[0]
                else 'Thumbnail job 1 failed with code thumbnail_query_timeout.\n')

    monkeypatch.setattr(remote, 'command_text', journal)
    logs = remote.sanitized_logs()
    assert units == list(remote.SERVICES[:2])
    assert logs.count('HTTP 200') == 200
    assert 'thumbnail_query_timeout' in logs


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


@pytest.mark.parametrize("path,allowed", [("tools/check.py", True), ("docs/USAGE.md", True),
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


def multiplexing_ssh(tmp_path, failure=None):
    """A transport that refuses command sessions without a live private master."""
    fake_ssh = tmp_path / 'ssh'
    fake_ssh.write_text(
        "#!/usr/bin/env python3\nimport json,subprocess,sys\nfrom pathlib import Path\n"
        f"with Path({str(tmp_path / 'ssh-calls.jsonl')!r}).open('a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "control=Path(next(arg.split('=',1)[1] for arg in sys.argv if arg.startswith('ControlPath=')))\n"
        "assert control.parent.stat().st_mode & 0o777 == 0o700\n"
        "if '-M' in sys.argv:\n"
        f"    if {failure!r} == 'start':\n"
        "        print('fixture banner timeout',file=sys.stderr);sys.exit(255)\n"
        f"    if {failure!r} != 'unavailable': control.touch()\n"
        "elif '-O' in sys.argv:\n"
        "    if sys.argv[sys.argv.index('-O')+1]=='check': sys.exit(0 if control.exists() else 255)\n"
        "    control.unlink(missing_ok=True)\n"
        "else:\n"
        "    assert control.is_file(), 'unexpected new connection during deployment'\n"
        "    sys.exit(subprocess.call(sys.argv[-1],shell=True))\n"
    )
    fake_ssh.chmod(0o755)
    return {'SSH': str(fake_ssh), 'USER': 'operator', 'HOST': 'local.test'}


@pytest.mark.parametrize('failure', ['start', 'unavailable', 'command'])
def test_deployment_connection_failure_cleans_up_and_never_runs_unconnected(tmp_path, failure):
    settings = multiplexing_ssh(tmp_path, failure)
    entered = False
    with pytest.raises((ValueError, RuntimeError)):
        with ssh_transport.deployment_connection(settings) as shared:
            entered = True
            assert failure == 'command'
            assert Path(shared['CONTROL_PATH']).exists()
            raise RuntimeError('fixture command failure')
    assert entered == (failure == 'command')
    calls = [json.loads(line) for line in (tmp_path / 'ssh-calls.jsonl').read_text().splitlines()]
    assert '-M' in calls[0] and calls[-1][-3:-1] == ['-O', 'exit']
    socket = Path(next(arg.split('=', 1)[1] for arg in calls[0] if arg.startswith('ControlPath=')))
    assert not socket.parent.exists()
    assert 'CONTROL_PATH' not in settings


def test_windows_deployment_preserves_configured_transport(monkeypatch):
    settings = {'SSH': '/mnt/c/Windows/System32/OpenSSH/ssh.exe', 'USER': 'operator', 'HOST': 'local.test'}
    monkeypatch.setattr(ssh_transport.subprocess, 'run', lambda *a, **k: pytest.fail('unexpected SSH invocation'))
    with ssh_transport.deployment_connection(settings) as shared:
        assert shared is settings
        assert not any(arg.startswith('ControlPath=') for arg in ssh_transport.ssh_command(shared, ['true']))


@pytest.mark.parametrize('interactive', [False, True])
@pytest.mark.parametrize('exit_code', [0, 7])
def test_deployment_backup_is_verified_off_vm_before_upgrade_can_continue(tmp_path, monkeypatch, interactive, exit_code):
    settings = multiplexing_ssh(tmp_path)
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
        f"raise SystemExit({exit_code})\n"
    )
    target = tmp_path / 'report'
    result = ssh_transport.run(settings,
                               [sys.executable, '-c', script], b'', sudo=True, timeout=25,
                               deployment_backup=target)
    assert result.returncode == exit_code, result.stderr
    assert b'migration allowed' in result.stdout
    assert (target / 'database.dump').read_bytes() == b'recovery fixture'*100000
    assert target.stat().st_mode & 0o777 == 0o700
    assert (target / 'database.dump').stat().st_mode & 0o777 == 0o600
    assert (target / 'backup.json').stat().st_mode & 0o777 == 0o600
    calls = [json.loads(line) for line in (tmp_path / 'ssh-calls.jsonl').read_text().splitlines()]
    assert sum('-M' in call for call in calls) == 1
    assert calls[1][-3:-1] == ['-O', 'check']
    assert calls[-1][-3:-1] == ['-O', 'exit']
    paths = {arg.split('=', 1)[1] for call in calls for arg in call if arg.startswith('ControlPath=')}
    assert len(paths) == 1
    assert not Path(paths.pop()).parent.exists()
    assert 'CONTROL_PATH' not in settings


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


@pytest.mark.parametrize('first_failure', [255, 'timeout'])
def test_backup_status_retries_transport_failure_and_preserves_diagnostics(tmp_path, monkeypatch, first_failure):
    target = tmp_path / 'report'
    target.mkdir(mode=0o700)
    done = threading.Event()
    waits = []
    monkeypatch.setattr(done, 'wait', waits.append)
    polls = []
    received = []
    record = {'size': 7, 'sha256': 'a' * 64}

    def run(command, **kwargs):
        assert shlex.split(command[-1])[2] == ssh_transport.BACKUP_STATUS
        assert kwargs['stdin'] == subprocess.DEVNULL
        polls.append(command)
        if len(polls) == 1:
            if first_failure == 'timeout':
                raise subprocess.TimeoutExpired(command, 20, stderr=b'status timed out')
            return subprocess.CompletedProcess(command, 255, b'', b'Connection reset by peer')
        return subprocess.CompletedProcess(command, 0, json.dumps(record).encode(), b'')

    monkeypatch.setattr(ssh_transport.subprocess, 'run', run)
    monkeypatch.setattr(ssh_transport, 'receive_backup', lambda *args: received.append(args[3]))
    failures = []
    ssh_transport.backup_monitor({'SSH': 'ssh', 'USER': 'operator', 'HOST': 'fixture'},
                                 '/tmp/rosbag-vm-fixture', target, done, failures)
    assert len(polls) == 2 and waits == [1]
    assert received == [record] and failures == []
    path = target / 'backup-transport.jsonl'
    saved = json.loads(path.read_text())
    assert saved['phase'] == 'status' and saved['exit_code'] == (124 if first_failure == 'timeout' else 255)
    assert saved['stderr'] == ('status timed out' if first_failure == 'timeout' else 'Connection reset by peer')
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('failure,expected_polls', [('connection', 3), ('unsafe-marker', 1), ('malformed', 1)])
def test_backup_status_failure_is_bounded_and_never_acknowledges_success(tmp_path, monkeypatch, failure, expected_polls):
    target = tmp_path / 'report'
    target.mkdir(mode=0o700)
    done = threading.Event()
    monkeypatch.setattr(done, 'wait', lambda _: None)
    polls = []
    acknowledgements = []

    def run(command, **kwargs):
        code = shlex.split(command[-1])[2]
        if code == ssh_transport.BACKUP_STATUS:
            polls.append(command)
            assert kwargs['stdin'] == subprocess.DEVNULL
            if failure == 'connection':
                return subprocess.CompletedProcess(command, 255, b'', b'Connection refused')
            if failure == 'unsafe-marker':
                return subprocess.CompletedProcess(command, 1, b'', b'Unsafe backup transfer marker')
            return subprocess.CompletedProcess(command, 0, b'not json', b'')
        assert code == ssh_transport.ACK_BACKUP
        acknowledgements.append(json.loads(kwargs['input']))
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(ssh_transport.subprocess, 'run', run)
    monkeypatch.setattr(ssh_transport, 'receive_backup', lambda *args: pytest.fail('unverified transfer'))
    failures = []
    ssh_transport.backup_monitor({'SSH': 'ssh', 'USER': 'operator', 'HOST': 'fixture'},
                                 '/tmp/rosbag-vm-fixture', target, done, failures)
    assert len(polls) == expected_polls
    assert len(failures) == len(acknowledgements) == 1
    assert acknowledgements == [{'error': failures[0]}]
    assert 'backup-transport.jsonl' in failures[0]
    saved = [json.loads(line) for line in (target / 'backup-transport.jsonl').read_text().splitlines()]
    assert len(saved) == expected_polls
    if failure == 'unsafe-marker':
        assert saved[0]['stderr'] == 'Unsafe backup transfer marker'
    elif failure == 'malformed':
        assert saved[0]['stdout'] == 'not json'
    assert not (target / 'database.dump').exists()


def test_finished_deployment_does_not_report_teardown_as_backup_failure(tmp_path, monkeypatch):
    done = threading.Event()

    def run(command, **kwargs):
        assert shlex.split(command[-1])[2] == ssh_transport.BACKUP_STATUS
        done.set()
        return subprocess.CompletedProcess(command, 255, b'', b'Connection closed')

    monkeypatch.setattr(ssh_transport.subprocess, 'run', run)
    failures = []
    ssh_transport.backup_monitor({'SSH': 'ssh', 'USER': 'operator', 'HOST': 'fixture'},
                                 '/tmp/rosbag-vm-fixture', tmp_path, done, failures)
    assert failures == []
    assert not (tmp_path / 'backup-transport.jsonl').exists()


def test_stream_diagnostics_are_private_and_never_contain_backup_payload(tmp_path):
    result = subprocess.CompletedProcess(['fixture'], 255, b'private database bytes', b'x' * 5000)
    path = ssh_transport.record_backup_transport_error(tmp_path, 'stream', result)
    saved = json.loads(path.read_text())
    assert saved == {'phase': 'stream', 'exit_code': 255, 'stderr': 'x' * 4096}
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('phase', ['stream', 'acknowledgement'])
def test_failed_backup_transport_retains_safe_output_and_logs_the_actual_error(tmp_path, phase):
    failed_code = ssh_transport.STREAM_BACKUP if phase == 'stream' else ssh_transport.ACK_BACKUP
    fake_ssh = tmp_path / 'ssh'
    fake_ssh.write_text("#!/usr/bin/env python3\nimport shlex,subprocess,sys\n"
                        f"if shlex.split(sys.argv[-1])[2] == {failed_code!r}:\n"
                        "    print('fixture transport rejected',file=sys.stderr)\n"
                        "    sys.exit(255)\n"
                        "sys.exit(subprocess.call(sys.argv[-1],shell=True))\n")
    fake_ssh.chmod(0o755)
    remote_dir = tmp_path / 'transfer'
    remote_dir.mkdir(mode=0o700)
    payload = b'private synthetic recovery fixture'
    (remote_dir / 'backup.dump').write_bytes(payload)
    (remote_dir / 'backup.dump').chmod(0o600)
    local_dir = tmp_path / 'local'
    local_dir.mkdir(mode=0o700)
    if phase == 'stream':
        (local_dir / 'database.dump').write_bytes(b'previous valid copy')
    import hashlib
    record = {'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    with pytest.raises(ValueError, match='backup-transport.jsonl'):
        ssh_transport.receive_backup({'SSH': str(fake_ssh), 'USER': 'operator', 'HOST': 'local.test'},
                                     str(remote_dir), local_dir, record)
    assert (local_dir / 'database.dump').read_bytes() == (b'previous valid copy' if phase == 'stream' else payload)
    assert not (remote_dir / 'backup-ack.json').exists()
    assert not list(local_dir.glob('*.partial'))
    saved = json.loads((local_dir / 'backup-transport.jsonl').read_text())
    assert saved == {'phase': phase, 'exit_code': 255, 'stderr': 'fixture transport rejected\n'}


@pytest.mark.parametrize('record', [[], None, 'unexpected'])
def test_invalid_backup_record_never_creates_output(tmp_path, record):
    with pytest.raises(ValueError, match='Invalid database recovery copy'):
        ssh_transport.receive_backup({}, '/tmp/rosbag-vm-fixture', tmp_path, record)
    assert list(tmp_path.iterdir()) == []


def test_deployment_result_is_private_and_records_verified_backup(tmp_path):
    target = tmp_path / "deployment"
    target.mkdir(mode=0o700)
    (target / "backup.json").write_text('{"sha256":"fixture"}')
    vm.vm_ssh.save_deployment_result(target, 1)
    result = target / "result.json"
    assert json.loads(result.read_text()) == {
        "exit_code": 1, "succeeded": False, "backup_verified": True}
    assert result.stat().st_mode & 0o777 == 0o600
