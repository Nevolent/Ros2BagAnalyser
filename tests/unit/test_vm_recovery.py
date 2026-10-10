from __future__ import annotations

import fcntl
import hashlib
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


@pytest.fixture
def active_incident(incident, monkeypatch):
    original = recovery.run

    def run(command, **kwargs):
        result = original(command, **kwargs)
        if command[:2] == ['systemctl', 'show'] and command[2] in (recovery.API, recovery.WORKER):
            result.stdout = 'active\n'
        return result
    monkeypatch.setattr(recovery, 'run', run)
    return incident


def test_recovery_checks_old_schema_before_starting_and_clears_gate_after_health(incident):
    root, marker, events = incident
    recovery.main()
    schema = next(index for index, args in enumerate(events) if args[0] == 'runuser')
    start = events.index(['systemctl', 'start', recovery.API, recovery.WORKER])
    assert schema < start < len(events) - 1
    assert events[-1] == ['systemctl', 'is-active', '--quiet', recovery.API, recovery.WORKER]
    assert not marker.exists()
    assert (root / 'current').resolve() == root / 'releases/git-old'


def test_running_previous_release_is_validated_without_service_interruption(active_incident):
    root, marker, events = active_incident
    recovery.main()
    assert any(event[0] == 'runuser' for event in events)
    assert events[-1] == ['systemctl', 'is-active', '--quiet', recovery.API, recovery.WORKER]
    assert all(event[1] in ('show', 'is-active') for event in events if event[0] == 'systemctl')
    assert not marker.exists()
    assert (root / 'current').resolve() == root / 'releases/git-old'


@pytest.mark.parametrize('fixture', ['incident', 'active_incident'])
def test_changed_schema_never_starts_old_services(request, fixture, monkeypatch):
    _, marker, events = request.getfixturevalue(fixture)
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
    message = 'requires a stopped migration' if 'migrate@' in unit else 'requires stopped application services'
    with pytest.raises(ValueError, match=message):
        recovery.main()
    assert marker.exists()
    assert all('start' not in event and 'restart' not in event for event in events)


@pytest.mark.parametrize('fixture', ['incident', 'active_incident'])
def test_wrong_release_health_does_not_report_recovery_or_clear_gate(request, fixture, monkeypatch):
    _, marker, _ = request.getfixturevalue(fixture)
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: None)
    monkeypatch.setattr(recovery.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(
        b'{"status":"ready","release_id":"another-release"}'))
    with pytest.raises(RuntimeError, match='did not become healthy'):
        recovery.main()
    assert marker.exists()


@pytest.mark.parametrize('api_state,worker_state', [
    ('activating', 'active'), ('active', 'deactivating'), ('reloading', 'reloading'), ('unknown', 'inactive'),
])
def test_transitional_or_unknown_service_states_retain_gate(incident, monkeypatch, api_state, worker_state):
    _, marker, events = incident
    original = recovery.run

    def run(command, **kwargs):
        result = original(command, **kwargs)
        if command[:2] == ['systemctl', 'show']:
            result.stdout = {recovery.API: api_state, recovery.WORKER: worker_state}.get(command[2], 'inactive')
        return result
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(ValueError, match='requires stopped application services or both services active'):
        recovery.main()
    assert marker.exists()
    assert all(event[:2] == ['systemctl', 'show'] for event in events)


def test_active_migration_blocks_running_release_recovery(active_incident, monkeypatch):
    _, marker, events = active_incident
    original = recovery.run

    def run(command, **kwargs):
        result = original(command, **kwargs)
        if command[:3] == ['systemctl', 'show', 'rosbag-analyser-migrate@git-new.service']:
            result.stdout = 'active\n'
        return result
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(ValueError, match='requires a stopped migration'):
        recovery.main()
    assert marker.exists()
    assert all(event[:2] == ['systemctl', 'show'] for event in events)


def test_offline_worker_retains_gate_without_restarting_running_services(active_incident, monkeypatch):
    _, marker, events = active_incident
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: None)
    monkeypatch.setattr(recovery.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps({
        'status': 'ready', 'release_id': 'git-old',
        'capabilities': {'worker_observation': {'state': 'offline'}},
    }).encode()))
    with pytest.raises(RuntimeError, match='did not become healthy'):
        recovery.main()
    assert marker.exists()
    assert all(event[1] == 'show' for event in events if event[0] == 'systemctl')


def test_running_jobs_retain_gate_without_restarting_running_services(active_incident, monkeypatch):
    _, marker, events = active_incident
    original = recovery.run

    def run(command, **kwargs):
        if command[0] == 'runuser':
            raise subprocess.CalledProcessError(1, command, stderr='Running or paused jobs need inspection')
        return original(command, **kwargs)
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        recovery.main()
    assert marker.exists()
    assert all(event[:2] == ['systemctl', 'show'] for event in events)


@pytest.fixture
def candidate_incident(incident, monkeypatch):
    root, marker, events = incident
    candidate = root / 'releases/git-new'
    (candidate / 'release-manifest.json').write_text(json.dumps({'release_id': candidate.name}))
    (root / 'current').unlink()
    (root / 'current').symlink_to(candidate)
    monkeypatch.setattr(recovery, 'repair_checksum_access', lambda path: events.append(['repair', str(path)]))
    monkeypatch.setattr(recovery.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(json.dumps({
        'status': 'ready', 'release_id': candidate.name,
        'capabilities': {'worker_observation': {'state': 'online'}},
    }).encode()))
    return root, marker, events


def test_candidate_recovery_validates_identity_and_schema_before_repair_and_start(candidate_incident):
    root, marker, events = candidate_incident
    recovery.main(candidate_selected=True)
    candidate = root / 'releases/git-new'
    identity = next(index for index, args in enumerate(events) if recovery.CHECK_RELEASE in args)
    schema = next(index for index, args in enumerate(events) if args[0] == 'runuser')
    repair = events.index(['repair', str(candidate)])
    preflight = events.index(['systemctl', 'restart', 'rosbag-analyser-preflight.service'])
    start = events.index(['systemctl', 'start', recovery.API, recovery.WORKER])
    assert identity < schema < repair < preflight < start
    assert events[-1] == [str(candidate / 'deploy/scripts/smoke-check')]
    assert not marker.exists()
    assert (root / 'current').resolve() == candidate


@pytest.mark.parametrize('failure', ['identity', 'schema', 'preflight', 'smoke'])
def test_candidate_recovery_failure_retains_gate_and_pointer(candidate_incident, monkeypatch, failure):
    root, marker, events = candidate_incident
    original = recovery.run

    def run(command, **kwargs):
        if ((failure == 'identity' and recovery.CHECK_RELEASE in command)
                or (failure == 'schema' and command[0] == 'runuser')
                or (failure == 'preflight' and command[:2] == ['systemctl', 'restart'])
                or (failure == 'smoke' and str(command[0]).endswith('/smoke-check'))):
            raise subprocess.CalledProcessError(1, command)
        return original(command, **kwargs)
    monkeypatch.setattr(recovery, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        recovery.main(candidate_selected=True)
    assert marker.exists()
    assert (root / 'current').resolve() == root / 'releases/git-new'
    if failure in ('identity', 'schema'):
        assert not any(event[0] == 'repair' or event[:2] == ['systemctl', 'start'] for event in events)
    if failure == 'preflight':
        assert not any(event[:2] == ['systemctl', 'start'] for event in events)


def test_candidate_mode_requires_candidate_already_selected(incident):
    root, marker, events = incident
    with pytest.raises(ValueError, match='candidate is not selected'):
        recovery.main(candidate_selected=True)
    assert marker.exists() and events == []
    assert (root / 'current').resolve() == root / 'releases/git-old'


@pytest.fixture
def checksum_metadata(tmp_path, monkeypatch):
    wheelhouse = tmp_path / 'wheelhouse'
    wheelhouse.mkdir()
    path = wheelhouse / 'SHA256SUMS'
    content = b'fixture dependency checksums\n'
    path.write_bytes(content)
    path.chmod(0o600)
    (tmp_path / 'release-manifest.json').write_text(json.dumps({
        'dependency_manifest_sha256': hashlib.sha256(content).hexdigest(),
    }))
    original = recovery.os.fstat

    def root_owned(descriptor):
        details = original(descriptor)
        return SimpleNamespace(st_mode=details.st_mode, st_uid=0, st_size=details.st_size)
    monkeypatch.setattr(recovery.os, 'fstat', root_owned)
    return tmp_path, path, content


def test_checksum_repair_only_changes_verified_metadata_read_access(checksum_metadata):
    root, path, content = checksum_metadata
    private = root / 'private.env'
    private.write_text('synthetic private fixture')
    private.chmod(0o600)
    recovery.repair_checksum_access(root)
    assert path.stat().st_mode & 0o777 == 0o644
    assert path.read_bytes() == content
    assert private.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('failure', ['checksum', 'symlink', 'directory', 'writable', 'owner'])
def test_unsafe_checksum_metadata_is_never_repaired(checksum_metadata, monkeypatch, failure):
    root, path, content = checksum_metadata
    if failure == 'checksum':
        path.write_bytes(b'changed identity')
    elif failure == 'symlink':
        target = root / 'other'
        path.rename(target)
        path.symlink_to(target)
    elif failure == 'directory':
        path.unlink()
        path.mkdir(mode=0o600)
    elif failure == 'writable':
        path.chmod(0o666)
    elif failure == 'owner':
        original = recovery.os.fstat
        monkeypatch.setattr(recovery.os, 'fstat', lambda descriptor: SimpleNamespace(
            st_mode=original(descriptor).st_mode, st_uid=1234, st_size=original(descriptor).st_size))
    before = path.lstat().st_mode
    with pytest.raises((OSError, ValueError)):
        recovery.repair_checksum_access(root)
    assert path.lstat().st_mode == before
