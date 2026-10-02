from __future__ import annotations

import fcntl
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('vm_recover', ROOT / 'tools/vm_recover.py')
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.fixture
def incident(tmp_path, monkeypatch):
    previous = tmp_path / 'releases/git-old'
    candidate = tmp_path / 'releases/git-new'
    previous.mkdir(parents=True)
    candidate.mkdir()
    (previous / 'release-manifest.json').write_text(json.dumps({'release_id': previous.name}))
    (tmp_path / 'current').symlink_to(previous)
    marker = tmp_path / 'maintenance'
    marker.write_text(json.dumps({'previous': str(previous), 'candidate': str(candidate)}))
    gate = SimpleNamespace(
        lstat=lambda: SimpleNamespace(st_mode=0o100644, st_uid=0),
        read_text=marker.read_text, unlink=marker.unlink,
    )
    monkeypatch.setattr(recovery, 'ROOT', tmp_path)
    monkeypatch.setattr(recovery, 'GATE', gate)
    monkeypatch.setattr(recovery, 'LOCK', tmp_path / 'lock')
    monkeypatch.setattr(recovery.os, 'geteuid', lambda: 0)
    events = []

    def run(command, **kwargs):
        events.append([str(value) for value in command])
        assert marker.exists(), 'the maintenance record must survive all validation and startup checks'
        return SimpleNamespace(stdout='inactive\n')
    monkeypatch.setattr(recovery, 'run', run)
    monkeypatch.setattr(recovery.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps({
        'status': 'ready', 'release_id': previous.name,
        'capabilities': {'worker_observation': {'state': 'online'}},
    }).encode()))
    return tmp_path, marker, events


def test_recovery_checks_old_schema_before_starting_and_clears_gate_after_health(incident):
    root, marker, events = incident
    recovery.main()
    schema = next(index for index, args in enumerate(events) if args[0] == 'runuser')
    start = events.index(['systemctl', 'start', recovery.API, recovery.WORKER])
    assert schema < start < len(events) - 1
    assert events[-1] == ['systemctl', 'is-active', '--quiet', recovery.API, recovery.WORKER]
    assert not marker.exists()
    assert (root / 'current').resolve() == root / 'releases/git-old'


def test_changed_schema_never_starts_old_services(incident, monkeypatch):
    _, marker, events = incident
    original = recovery.run

    def run(command, **kwargs):
        if command[0] == 'runuser':
            raise subprocess.CalledProcessError(1, command)
        return original(command, **kwargs)
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        recovery.main()
    assert marker.exists()
    assert all('start' not in event and 'restart' not in event for event in events)


def test_changed_pointer_requires_explicit_rollback(incident):
    root, marker, events = incident
    (root / 'current').unlink()
    (root / 'current').symlink_to(root / 'releases/git-new')
    with pytest.raises(ValueError, match='pointer changed'):
        recovery.main()
    assert marker.exists()
    assert events == []


def test_running_deployment_is_not_interrupted(incident):
    _, marker, events = incident
    with recovery.LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='still running'):
            recovery.main()
    assert marker.exists()
    assert events == []


@pytest.mark.parametrize('unit', [recovery.API, recovery.WORKER, 'rosbag-analyser-migrate@git-new.service'])
def test_active_service_or_migration_blocks_recovery(incident, monkeypatch, unit):
    _, marker, events = incident
    original = recovery.run

    def run(command, **kwargs):
        if command[:3] == ['systemctl', 'show', unit]:
            return SimpleNamespace(stdout='active\n')
        return original(command, **kwargs)
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(ValueError, match='requires stopped'):
        recovery.main()
    assert marker.exists()
    assert all('start' not in event and 'restart' not in event for event in events)


def test_wrong_release_health_does_not_report_recovery_or_clear_gate(incident, monkeypatch):
    _, marker, _ = incident
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: None)
    monkeypatch.setattr(recovery.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(
        b'{"status":"ready","release_id":"another-release"}'))
    with pytest.raises(RuntimeError, match='did not become healthy'):
        recovery.main()
    assert marker.exists()
