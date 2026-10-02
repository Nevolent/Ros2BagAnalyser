from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location('deploy_release', ROOT / 'deploy/scripts/deploy_release.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def commit(repository):
    subprocess.run(['git', '-C', str(repository), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repository), 'commit', '-qm', 'fixture'], check=True)
    return subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repository'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.invalid'], check=True)
    subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Test'], check=True)
    migrations = root / 'src/rosbag_analyser/persistence/migrations'
    migrations.mkdir(parents=True)
    (migrations / '0001_initial.sql').write_text('SELECT 1;\n')
    contract = root / 'deploy/release-contract.json'
    contract.parent.mkdir()
    contract.write_text(json.dumps({'platform': {'python': '3.10'}, 'schema_version': 1, 'database_schema': '0001'}))
    return root, commit(root)


@pytest.mark.parametrize('path,expected', [
    ('docs/OPERATIONS.md', ('none', False, False)),
    ('frontend/tests/example.spec.ts', ('none', False, False)),
    ('src/rosbag_analyser/web/react/index.html', ('api', False, False)),
    ('src/rosbag_analyser/worker.py', ('both', False, False)),
    ('deploy/runtime-requirements.in', ('both', False, True)),
    ('pyproject.toml', ('both', False, True)),
    ('deploy/scripts/deploy_release.py', ('none', False, False)),
    ('deploy/scripts/deploy-from-git', ('none', False, False)),
    ('src/rosbag_analyser/persistence/migrations/0002_new.sql', ('both', True, False)),
])
def test_application_changes_plan_the_required_upgrade(repository, path, expected):
    root, old = repository
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('fixture\n')
    new = commit(root)
    assert deploy.plan(root, old, new) == expected


@pytest.mark.parametrize('change', ['edit', 'delete', 'gap', 'platform', 'systemd', 'site_script'])
def test_unsafe_schema_or_site_changes_fail_before_activation(repository, change):
    root, old = repository
    migrations = root / 'src/rosbag_analyser/persistence/migrations'
    if change == 'edit':
        (migrations / '0001_initial.sql').write_text('SELECT 2;\n')
    elif change == 'delete':
        (migrations / '0001_initial.sql').unlink()
    elif change == 'gap':
        (migrations / '0003_gap.sql').write_text('SELECT 1;\n')
    elif change == 'platform':
        (root / 'deploy/release-contract.json').write_text(json.dumps({'platform': {'python': '3.12'}, 'schema_version': 1}))
    elif change == 'systemd':
        path = root / 'deploy/systemd/example.service'
        path.parent.mkdir()
        path.write_text('fixture')
    else:
        path = root / 'deploy/scripts/activate-release'
        path.parent.mkdir()
        path.write_text('fixture')
    with pytest.raises(ValueError):
        deploy.plan(root, old, commit(root))


def upgrade_fixture(tmp_path, monkeypatch, failure=None):
    events = []
    marker = tmp_path / 'maintenance'
    monkeypatch.setattr(deploy, 'MAINTENANCE', marker)
    candidate, previous = tmp_path / 'git-new', tmp_path / 'git-old'
    item = deploy.Upgrade(candidate, previous, True, '/tmp/rosbag-vm-fixture')
    monkeypatch.setattr(item, 'database_settings', lambda: {})
    monkeypatch.setattr(item, 'backup_settings', lambda: {})
    monkeypatch.setattr(item, 'jobs', lambda: [])
    monkeypatch.setattr(item, 'worker_active', lambda: True)
    monkeypatch.setattr(item, 'wait_worker_stopped', lambda: events.append(('worker-stopped',)))
    monkeypatch.setattr(deploy.shutil, 'which', lambda _: '/fixture/bin')
    monkeypatch.setattr(deploy.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    migrated = False

    def schema(release):
        events.append(('schema', release.name))
        if failure == 'health' and migrated and release == previous:
            raise ValueError('old schema incompatible')
    monkeypatch.setattr(item, 'validate_schema', schema)

    def command(arguments, **kwargs):
        nonlocal migrated
        command = tuple(str(value) for value in arguments)
        events.append(command)
        if 'start' in command and any('rosbag-analyser-migrate@' in value for value in command):
            if failure == 'migration':
                raise subprocess.CalledProcessError(1, command)
            migrated = True
        if command == ('systemctl', 'start', deploy.WORKER):
            assert marker.exists(), 'the worker must start under the maintenance gate'
        if command[-1].endswith('smoke-check'):
            assert marker.exists(), 'writes must remain closed through health checks'
            if failure == 'health' and 'git-new' in command[-1]:
                raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(stdout='loaded\n', returncode=0)
    monkeypatch.setattr(deploy, 'run', command)

    def backup():
        events.append(('verified-backup',))
        item.backup = tmp_path / 'recovery'
        if failure == 'backup':
            raise ValueError('copy failed')
    monkeypatch.setattr(item, 'backup_database', backup)
    return item, events, marker


def test_migration_waits_for_backup_and_keeps_new_work_closed_until_healthy(tmp_path, monkeypatch):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch)
    item.execute()
    assert not marker.exists()
    stop_api = events.index(('systemctl', 'stop', deploy.API))
    stop_worker = events.index(('systemctl', 'stop', deploy.WORKER))
    worker_stopped = events.index(('worker-stopped',))
    backup = events.index(('verified-backup',))
    migration = next(index for index, event in enumerate(events) if any('migrate@' in value for value in event) and 'start' in event)
    smoke = next(index for index, event in enumerate(events) if event[0].endswith('smoke-check'))
    start_worker = events.index(('systemctl', 'start', deploy.WORKER))
    assert stop_api < stop_worker < worker_stopped < backup < migration < start_worker < smoke


@pytest.mark.parametrize('failure', ['backup', 'migration'])
def test_failure_before_committed_schema_change_restores_previous_release(tmp_path, monkeypatch, failure):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch, failure)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        item.execute()
    assert not marker.exists()
    assert any(event[-1] == 'git-old' for event in events)
    assert ('systemctl', 'start', deploy.WORKER) in events
    if failure == 'backup':
        assert not any('start' in event and any('migrate@' in part for part in event) for event in events)


def test_health_failure_after_schema_change_preserves_backup_and_stops_services(tmp_path, monkeypatch):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch, 'health')
    with pytest.raises(subprocess.CalledProcessError):
        item.execute()
    assert marker.exists()
    assert item.backup == tmp_path / 'recovery'
    assert events[-3] == ('systemctl', 'stop', deploy.API, deploy.WORKER)
    assert events[-2] == ('systemctl', 'stop', 'rosbag-analyser-migrate@git-new.service')
    assert ('systemctl', 'start', deploy.WORKER) in events
    assert not any(event[0].endswith('activate-release') and event[-1] == 'git-old' for event in events)


def test_paused_job_is_never_killed_or_migrated(tmp_path, monkeypatch):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(item, 'jobs', lambda: [('paused',)])
    with pytest.raises(ValueError, match='paused'):
        item.execute()
    assert not marker.exists()
    assert not any(event[0] == 'systemctl' for event in events)


def test_pause_race_reopens_api_without_stopping_processor(tmp_path, monkeypatch):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch)
    states = iter([[], [('pause_requested',)]])
    monkeypatch.setattr(item, 'jobs', lambda: next(states))
    with pytest.raises(ValueError, match='paused'):
        item.execute()
    assert not marker.exists()
    assert ('systemctl', 'start', deploy.API) in events
    assert ('systemctl', 'stop', deploy.WORKER) not in events
    assert not any('kill' in event for event in events)


def test_running_job_with_offline_worker_fails_before_maintenance(tmp_path, monkeypatch):
    item, events, marker = upgrade_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(item, 'jobs', lambda: [('running',)])
    monkeypatch.setattr(item, 'worker_active', lambda: False)
    with pytest.raises(ValueError, match='worker service is offline'):
        item.execute()
    assert not marker.exists()
    assert not any(event[0] == 'systemctl' for event in events)


def test_backup_publisher_requires_matching_workstation_ack(tmp_path, monkeypatch):
    directory = Path('/tmp') / ('rosbag-vm-' + tmp_path.name)
    directory.mkdir(mode=0o700)
    dump = tmp_path / 'original.dump'
    dump.write_bytes(b'original recovery data')
    acknowledgement = directory / 'backup-ack.json'
    acknowledgement.write_text(json.dumps({'size': dump.stat().st_size, 'sha256': '0' * 64}))
    monkeypatch.setattr(deploy.os, 'chown', lambda *args: None)
    try:
        with pytest.raises(ValueError, match='confirm'):
            deploy.publish_backup(dump, directory, timeout=1)
        assert dump.read_bytes() == b'original recovery data'
    finally:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
