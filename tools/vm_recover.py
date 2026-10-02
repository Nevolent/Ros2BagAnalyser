"""Reopen an unchanged, schema-compatible release after an aborted deployment.

Streamed by ./vm recover; never migrates, restores a dump or changes Git/pointers.
"""
from __future__ import annotations

import fcntl
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

# Execute with the previous release's schema definition and local peer auth.
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


def recover():
    details = GATE.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o022:
        raise ValueError('The maintenance record is not a protected regular file.')
    record = json.loads(GATE.read_text())
    previous = checked_release(record['previous'])
    candidate = checked_release(record['candidate'])
    if (ROOT / 'current').resolve(strict=True) != previous:
        raise ValueError('The release pointer changed. This recovery only reopens the unchanged previous release.')
    manifest = json.loads((previous / 'release-manifest.json').read_text())
    if manifest.get('release_id') != previous.name:
        raise ValueError('The previous release manifest does not match its directory.')
    for unit in (API, WORKER, f'rosbag-analyser-migrate@{candidate.name}.service'):
        state = run(['systemctl', 'show', unit, '--property=ActiveState', '--value'], capture=True).stdout.strip()
        if state not in ('inactive', 'failed'):
            raise ValueError(f'{unit} is {state}; recovery requires stopped services and migration.')

    print(f'Checking database compatibility with {previous.name}.', flush=True)
    run(['runuser', '-u', 'postgres', '--', previous / 'venv/bin/python', '-c', CHECK_DATABASE])
    print('Previous schema verified. Starting the previous application release.', flush=True)
    run(['systemctl', 'reset-failed', API, WORKER])
    run(['systemctl', 'restart', 'rosbag-analyser-preflight.service'])
    run(['systemctl', 'start', API, WORKER])
    for _ in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3) as response:
                health = json.load(response)
            if (health.get('status') == 'ready' and health.get('release_id') == previous.name
                    and health.get('capabilities', {}).get('worker_observation', {}).get('state') == 'online'):
                run(['systemctl', 'is-active', '--quiet', API, WORKER])
                GATE.unlink()
                print(f'Recovered {previous.name}: API ready, worker online.', flush=True)
                return
        except (OSError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('The previous services did not become healthy; the maintenance record was retained. Run ./vm status.')


def main():
    if os.geteuid() != 0:
        raise ValueError('Recovery requires sudo on the configured VM.')
    descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('A deployment is still running; recovery did not change anything.') from error
        recover()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'recover: {error}', file=sys.stderr)
        raise SystemExit(1)
