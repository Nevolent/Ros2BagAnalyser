"""Reopen the selected, schema-compatible release after an aborted deployment.

Streamed by ./vm recover; never migrates, restores a dump or changes Git/pointers.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path('/opt/rosbag-analyser')
GATE = Path('/run/rosbag-analyser-maintenance')
LOCK = Path('/run/rosbag-analyser-deploy.lock')
API = 'rosbag-analyser-api.service'
WORKER = 'rosbag-analyser-worker.service'

# Execute with the selected release's schema definition and local peer auth.
# The database transaction is explicitly read-only and has bounded queries.
CHECK_DATABASE = """
import psycopg
from rosbag_analyser.persistence.database import validate_catalog_schema
url = 'postgresql:///rosbag_analyser?host=/run/postgresql'
validate_catalog_schema(url)
with psycopg.connect(url, connect_timeout=5,
        options='-c default_transaction_read_only=on -c statement_timeout=10000') as connection:
    if connection.execute("SELECT count(*) FROM jobs WHERE state = 'running'").fetchone()[0]:
        raise SystemExit('Running or paused jobs need inspection before restarting the worker.')
"""


CHECK_RELEASE = """
import sys
from pathlib import Path
from rosbag_analyser.preflight import validate_release_manifest
root = Path(sys.argv[1])
validate_release_manifest(root / 'release-manifest.json', root / 'wheelhouse/SHA256SUMS',
                         root / 'deploy/release-contract.json', expected_release_id=root.name)
"""


def repair_checksum_access(release):
    """Repair only non-secret, identity-matching installed checksum metadata."""
    wheelhouse = release / 'wheelhouse'
    if wheelhouse.resolve(strict=True) != wheelhouse or not wheelhouse.is_dir():
        raise ValueError('The installed wheelhouse is not a contained regular directory.')
    expected = json.loads((release / 'release-manifest.json').read_text())['dependency_manifest_sha256']
    descriptor = os.open(wheelhouse / 'SHA256SUMS', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as checksum:
        details = os.fstat(checksum.fileno())
        if (not stat.S_ISREG(details.st_mode) or details.st_uid != 0
                or details.st_mode & 0o022 or details.st_size > 1024 * 1024):
            raise ValueError('The installed dependency manifest is not protected regular metadata.')
        if hashlib.sha256(checksum.read(1024 * 1024 + 1)).hexdigest() != expected:
            raise ValueError('The installed dependency manifest checksum does not match the release.')
        if stat.S_IMODE(details.st_mode) != 0o644:
            os.fchmod(checksum.fileno(), 0o644)
            print('Corrected service read access for the verified dependency manifest.', flush=True)


def run(command, *, capture=False):
    return subprocess.run([str(value) for value in command], check=True, text=True,
                          capture_output=capture, timeout=120, cwd='/')


def checked_release(value):
    path = Path(value)
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', path.name)
            or path.parent != ROOT / 'releases' or path.resolve(strict=True) != path
            or not path.is_dir()):
        raise ValueError('The recorded release path is invalid.')
    return path


def recover(*, candidate_selected=False):
    details = GATE.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o022:
        raise ValueError('The maintenance record is not a protected regular file.')
    record = json.loads(GATE.read_text())
    previous = checked_release(record['previous'])
    candidate = checked_release(record['candidate'])
    selected = candidate if candidate_selected else previous
    if (ROOT / 'current').resolve(strict=True) != selected:
        if candidate_selected:
            raise ValueError('The recorded candidate is not selected; recovery did not change the release pointer.')
        raise ValueError('The release pointer changed. This recovery only reopens the unchanged previous release.')
    manifest = json.loads((selected / 'release-manifest.json').read_text())
    if manifest.get('release_id') != selected.name:
        raise ValueError('The selected release manifest does not match its directory.')
    states = {}
    for unit in (API, WORKER, f'rosbag-analyser-migrate@{candidate.name}.service'):
        state = run(['systemctl', 'show', unit, '--property=ActiveState', '--value'], capture=True).stdout.strip()
        states[unit] = state
    migration = f'rosbag-analyser-migrate@{candidate.name}.service'
    if states[migration] not in ('inactive', 'failed'):
        raise ValueError(f'{migration} is {states[migration]}; recovery requires a stopped migration.')
    running = states[API] == states[WORKER] == 'active'
    stopped = all(states[unit] in ('inactive', 'failed') for unit in (API, WORKER))
    if not running and not stopped:
        raise ValueError('Recovery requires stopped application services or both services active; '
                         f'API is {states[API]}, worker is {states[WORKER]}.')

    if candidate_selected:
        run([selected / 'venv/bin/python', '-c', CHECK_RELEASE, selected], capture=True)
    print(f'Checking database compatibility with {selected.name}.', flush=True)
    run(['runuser', '-u', 'postgres', '--', selected / 'venv/bin/python', '-c', CHECK_DATABASE])
    if candidate_selected:
        repair_checksum_access(selected)
    if running:
        print('Schema verified. Checking the running selected release.', flush=True)
    else:
        print('Schema verified. Starting the selected application release.', flush=True)
        run(['systemctl', 'reset-failed', API, WORKER])
        run(['systemctl', 'restart', 'rosbag-analyser-preflight.service'])
        run(['systemctl', 'start', API, WORKER])
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3) as response:
                health = json.load(response)
            if (health.get('status') == 'ready' and health.get('release_id') == selected.name
                    and health.get('capabilities', {}).get('worker_observation', {}).get('state') == 'online'):
                run(['systemctl', 'is-active', '--quiet', API, WORKER])
                if candidate_selected:
                    run([selected / 'deploy/scripts/smoke-check'])
                GATE.unlink()
                print(f'Recovered {selected.name}: API ready, worker online.', flush=True)
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('The selected services did not become healthy; the maintenance record was retained. Run ./vm status.')


def main(*, candidate_selected=False):
    if os.geteuid() != 0:
        raise ValueError('Recovery requires sudo on the configured VM.')
    descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('A deployment is still running; recovery did not change anything.') from error
        recover(candidate_selected=candidate_selected)


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--candidate', action='store_true')
        main(candidate_selected=parser.parse_args().candidate)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'recover: {error}', file=sys.stderr)
        raise SystemExit(1)
