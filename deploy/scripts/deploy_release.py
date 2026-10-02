#!/usr/bin/env python3
"""Plan application releases and perform an upgrade with a verified recovery copy."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import uuid

ROOT = Path('/opt/rosbag-analyser')
CONFIG = Path('/etc/rosbag-analyser')
BACKUPS = Path('/var/backups/rosbag-analyser')
MAINTENANCE = Path('/run/rosbag-analyser-maintenance')
API = 'rosbag-analyser-api.service'
WORKER = 'rosbag-analyser-worker.service'
DATABASE = 'postgresql://rosbag_analyser_migration@/rosbag_analyser?host=/run/postgresql'
BACKUP_DATABASE = 'postgresql://rosbag_analyser_backup@/rosbag_analyser?host=/run/postgresql'


def run(command, *, env=None, capture=False, stdin=None, timeout=120):
    return subprocess.run([str(item) for item in command], check=True, env=env,
                          capture_output=capture, text=stdin is None, stdin=stdin,
                          timeout=timeout)


def git(repository, *arguments):
    return run(['git', '-C', repository, *arguments], capture=True).stdout.strip()


def plan(repository, previous, candidate):
    changes = git(repository, 'diff', '--name-only', previous, candidate).splitlines()
    mode, migrate, dependencies = 'none', False, False
    for path in changes:
        if path.startswith('deploy/scripts/') and path not in (
            'deploy/scripts/deploy-from-git', 'deploy/scripts/deploy_release.py'
        ):
            raise ValueError('Release tooling changes need a reviewed site upgrade.')
        if path.startswith(('deploy/systemd/', 'deploy/nginx/', 'deploy/firewall/')) or (
            path.startswith('deploy/') and path.endswith('.example')
        ) or path == 'deploy/apt-packages.in':
            raise ValueError('OS, service, proxy, firewall or site configuration changes need a site upgrade.')
        if path.startswith('src/rosbag_analyser/persistence/migrations/') and path.endswith('.sql'):
            migrate, mode = True, 'both'
        elif path in ('pyproject.toml', 'deploy/runtime-requirements.in', 'deploy/build-requirements.in'):
            dependencies, mode = True, 'both'
        elif path == 'deploy/release-contract.json':
            old = json.loads(git(repository, 'show', f'{previous}:{path}'))
            new = json.loads(git(repository, 'show', f'{candidate}:{path}'))
            if old.get('platform') != new.get('platform') or old.get('schema_version') != new.get('schema_version'):
                raise ValueError('The release platform/contract format changed; a site upgrade is required.')
            mode = 'both'
        elif path.startswith('src/rosbag_analyser/web/'):
            if mode == 'none':
                mode = 'api'
        elif path.startswith('src/rosbag_analyser/'):
            mode = 'both'
    if migrate:
        prefix = 'src/rosbag_analyser/persistence/migrations/'
        def migrations(revision):
            result = {}
            for line in git(repository, 'ls-tree', '-r', revision, '--', prefix).splitlines():
                identity, path = line.split('\t')
                if path.endswith('.sql'):
                    if not re.fullmatch(r'\d{4}_[a-z0-9_]+\.sql', Path(path).name):
                        raise ValueError('Migration filenames must have a numbered SQL identity.')
                    result[path] = identity.split()[2]
            return result
        old, new = migrations(previous), migrations(candidate)
        if any(new.get(path) != digest for path, digest in old.items()):
            raise ValueError('Existing migrations were changed or removed; only appended migrations deploy automatically.')
        added = sorted(set(new) - set(old))
        last = max(int(Path(path).name[:4]) for path in old)
        if [int(Path(path).name[:4]) for path in added] != list(range(last + 1, last + 1 + len(added))):
            raise ValueError('New migrations must continue the existing sequence without gaps.')
    return mode, migrate, dependencies


def private_environment(path):
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or stat.S_IMODE(details.st_mode) not in (0o600, 0o640):
        raise ValueError(f'Private configuration has unsafe ownership or mode: {path.name}')
    values = {}
    for line in path.read_text().splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        if len(words) != 1 or '=' not in words[0]:
            raise ValueError(f'Unsupported configuration syntax: {path.name}')
        key, value = words[0].split('=', 1)
        values[key] = value
    return values


def credential(path):
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or stat.S_IMODE(details.st_mode) not in (0o600, 0o640):
        raise ValueError('The database credential has unsafe ownership or mode.')
    return str(path)


def digest_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def publish_backup(dump, directory, *, timeout=600):
    """Wait for the workstation to acknowledge its independently checked copy."""
    if not re.fullmatch(r'/tmp/rosbag-vm-[A-Za-z0-9_-]+', str(directory)):
        raise ValueError('Automatic upgrades require the workstation backup transfer channel.')
    details = directory.lstat()
    if not stat.S_ISDIR(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o700:
        raise ValueError('The backup transfer directory is unsafe.')
    expected_digest = digest_file(dump)
    output = directory / 'backup.dump'
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'wb') as destination, dump.open('rb') as source:
        shutil.copyfileobj(source, destination, 1024 * 1024)
        destination.flush()
        os.fsync(destination.fileno())
    os.chown(output, details.st_uid, details.st_gid)
    if digest_file(output) != expected_digest:
        raise ValueError('The VM backup transfer copy changed unexpectedly.')
    record = {'size': output.stat().st_size, 'sha256': expected_digest}
    marker = directory / 'backup.partial'
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(record, stream)
    os.chown(marker, details.st_uid, details.st_gid)
    marker.rename(directory / 'backup.json')
    print('Waiting for the verified database backup to reach this PC.', flush=True)
    deadline = time.monotonic() + timeout
    acknowledgement = directory / 'backup-ack.json'
    while time.monotonic() < deadline:
        try:
            descriptor = os.open(acknowledgement, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            time.sleep(1)
            continue
        with os.fdopen(descriptor) as stream:
            answer = json.loads(stream.read(4096))
        if answer.get('sha256') != record['sha256'] or answer.get('size') != record['size']:
            raise ValueError('The workstation did not confirm a valid recovery copy.')
        print('Database backup verified on the VM and this PC.', flush=True)
        return record
    raise TimeoutError('No verified workstation backup acknowledgement arrived; migration was not started.')


class Upgrade:
    def __init__(self, candidate, previous, migrate, transfer):
        self.candidate = Path(candidate)
        self.previous = Path(previous)
        self.migrate = migrate
        self.transfer = Path(transfer) if transfer else None
        self.started = False
        self.drained = False
        self.worker_was_active = False
        self.worker_signalled = False
        self.migration_started = False
        self.backup = None
        self.database_env = None

    def database_settings(self):
        settings = private_environment(CONFIG / 'migration.env')
        if settings.get('ROS_BAG_ANALYSER_DATABASE_URL') != DATABASE:
            raise ValueError('The migration database target is invalid.')
        return dict(os.environ, ROS_BAG_ANALYSER_DATABASE_URL=DATABASE,
                    PGPASSFILE=credential(CONFIG / 'migration.pgpass'))

    def jobs(self):
        import psycopg
        with psycopg.connect(DATABASE, passfile=self.database_env['PGPASSFILE'],
                             options='-c statement_timeout=10000 -c default_transaction_read_only=on') as connection:
            return connection.execute("SELECT control_state FROM jobs WHERE state = 'running'").fetchall()

    def worker_active(self):
        state = run(['systemctl', 'show', WORKER, '--property=ActiveState', '--value'],
                    capture=True).stdout.strip()
        if state not in ('active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'):
            raise ValueError('The worker service state could not be determined safely.')
        return state in ('active', 'activating', 'deactivating', 'reloading')

    def wait_worker_stopped(self, timeout=30):
        deadline = time.monotonic() + timeout
        while self.worker_active():
            if time.monotonic() >= deadline:
                raise TimeoutError('The worker did not stop cleanly; maintenance remains enabled.')
            time.sleep(1)

    def validate_schema(self, release):
        run([release / 'venv/bin/python', '-c',
             'import os; from rosbag_analyser.persistence.database import validate_catalog_schema; '
             "validate_catalog_schema(os.environ['ROS_BAG_ANALYSER_DATABASE_URL'])"],
            env=self.database_env, capture=True)

    def backup_settings(self):
        settings = private_environment(CONFIG / 'backup.env')
        if settings.get('ROS_BAG_ANALYSER_DATABASE_URL') != BACKUP_DATABASE:
            raise ValueError('The backup database target is invalid.')
        passfile = Path(settings.get('PGPASSFILE', str(CONFIG / 'backup.pgpass')))
        return dict(os.environ, ROS_BAG_ANALYSER_DATABASE_URL=BACKUP_DATABASE,
                    PGPASSFILE=credential(passfile))

    def backup_database(self):
        BACKUPS.mkdir(mode=0o700, exist_ok=True)
        if BACKUPS.is_symlink() or BACKUPS.resolve() != BACKUPS or BACKUPS.stat().st_uid != 0 or stat.S_IMODE(BACKUPS.stat().st_mode) not in (0o700, 0o750):
            raise ValueError('The protected backup root is unsafe.')
        directory = BACKUPS / f"deploy-{self.candidate.name}-{uuid.uuid4().hex[:12]}"
        directory.mkdir(mode=0o700)
        self.backup = directory
        run([self.previous / 'deploy/scripts/backup-database', directory, self.previous.name],
            env=self.backup_settings(), timeout=600)
        dumps = list(directory.glob('*.dump'))
        if len(dumps) != 1 or not dumps[0].is_file() or dumps[0].is_symlink():
            raise ValueError('The database backup was not published correctly.')
        dump = dumps[0]
        # Preserve the private configuration beside the dump, never in Git or logs.
        for name in ('application.env', 'migration.env', 'backup.env', 'runtime.pgpass', 'migration.pgpass', 'backup.pgpass'):
            source = CONFIG / name
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise ValueError('A recovery configuration file is not regular.')
                shutil.copyfile(source, directory / name)
                (directory / name).chmod(0o600)
        self.verify_restore(dump)
        record = publish_backup(dump, self.transfer)
        record.update(previous_release=str(self.previous), candidate_release=str(self.candidate), dump=dump.name)
        recovery = directory / 'recovery.json'
        recovery.write_text(json.dumps(record, indent=2) + '\n')
        recovery.chmod(0o600)
        print(f'Recovery files retained at {directory}.', flush=True)

    def verify_restore(self, dump):
        restore_name = 'rosbag_analyser_restore_' + uuid.uuid4().hex[:24]
        run(['runuser', '-u', 'postgres', '--', 'createdb', '--host=/run/postgresql',
             '--template=template0', restore_name])
        try:
            with dump.open('rb') as source:
                run(['runuser', '-u', 'postgres', '--', 'pg_restore', '--exit-on-error',
                     '--host=/run/postgresql', '--dbname=' + restore_name], stdin=source, timeout=600)
            run(['runuser', '-u', 'postgres', '--', self.previous / 'venv/bin/python', '-c',
                 'import sys; from rosbag_analyser.persistence.database import validate_catalog_schema; '
                 'validate_catalog_schema(sys.argv[1])',
                 f'postgresql:///{restore_name}?host=/run/postgresql'], capture=True)
        finally:
            run(['runuser', '-u', 'postgres', '--', 'dropdb', '--host=/run/postgresql', restore_name])

    def wait_ready(self):
        for attempt in range(30):
            try:
                run(['curl', '--fail', '--silent', '--max-time', '5',
                     'http://127.0.0.1:8000/health/ready'], capture=True, timeout=10)
                return
            except subprocess.SubprocessError:
                time.sleep(1)
        raise RuntimeError('The restarted API did not become ready within 30 checks.')

    def activate(self, release):
        run([self.candidate / 'deploy/scripts/activate-release', release.name])
        run(['systemctl', 'restart', 'rosbag-analyser-preflight.service'])
        run(['systemctl', 'start', API])
        # Readiness includes the worker's PostgreSQL advisory lock. Starting
        # it under the maintenance gate keeps it online without claiming jobs.
        run(['systemctl', 'start', WORKER])
        self.wait_ready()
        run([release / 'deploy/scripts/smoke-check'])

    def recover(self):
        if not self.started:
            return
        if not self.drained:
            # Wait out a systemd stop before reopening writes. A timed-out
            # active job was never signalled and can continue normally.
            if self.worker_signalled:
                try:
                    self.wait_worker_stopped()
                except Exception:
                    run(['systemctl', 'start', API])
                    print('The API is available for reads, but the maintenance gate remains enabled '
                          'because the worker did not stop cleanly.', file=sys.stderr)
                    return
            run(['systemctl', 'start', API])
            run(['systemctl', 'start', WORKER])
            MAINTENANCE.unlink()
            print('The original release reopened; no active processor was interrupted.', file=sys.stderr)
            return
        run(['systemctl', 'stop', API, WORKER])
        if self.migration_started:
            # systemctl start may have timed out on the client while systemd
            # still runs the oneshot. Stop it before checking either schema.
            run(['systemctl', 'stop', f'rosbag-analyser-migrate@{self.candidate.name}.service'],
                timeout=600)
        try:
            self.validate_schema(self.previous)
        except Exception:
            print('Upgrade failed after a schema change. API and worker remain stopped; '
                  f'the maintenance gate and recovery files are retained at {self.backup}.', file=sys.stderr)
            return
        self.activate(self.previous)
        MAINTENANCE.unlink()
        print('The previous compatible release was restored; no database restore was needed.', file=sys.stderr)

    def execute(self):
        self.database_env = self.database_settings()
        self.validate_schema(self.previous)
        initial_jobs = self.jobs()
        if any(row[0] in ('paused', 'pause_requested') for row in initial_jobs):
            raise ValueError('A job is paused. Resume or cancel it in Processing before deploying.')
        self.worker_was_active = self.worker_active()
        if initial_jobs and not self.worker_was_active:
            raise ValueError('A job is running while the worker service is offline; resolve it before deploying.')
        if self.migrate:
            if self.transfer is None:
                raise ValueError('Migration requires the workstation backup transfer channel; use ./vm deploy.')
            self.backup_settings()
            for command in ('pg_dump', 'pg_restore', 'createdb', 'dropdb', 'runuser'):
                if shutil.which(command) is None:
                    raise ValueError(f'Required backup/restore tool is unavailable: {command}')
            if run(['systemctl', 'show', f'rosbag-analyser-migrate@{self.candidate.name}.service',
                    '--property=LoadState', '--value'], capture=True).stdout.strip() != 'loaded':
                raise ValueError('The migration service is not installed.')
        descriptor = os.open(MAINTENANCE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'previous': str(self.previous), 'candidate': str(self.candidate)}, stream)
        self.started = True
        try:
            # Stop admission first. The maintenance gate blocks new claims;
            # let any current database job finish before stopping the worker.
            run(['systemctl', 'stop', API])
            if any(row[0] in ('paused', 'pause_requested') for row in self.jobs()):
                raise ValueError('A job was paused while deployment started; resume or cancel it first.')
            print('Waiting for the current processing job to finish; the queue remains saved.', flush=True)
            deadline = time.monotonic() + 3600
            while True:
                running = self.jobs()
                if any(row[0] in ('paused', 'pause_requested') for row in running):
                    raise ValueError('A job was paused while deployment started; resume or cancel it first.')
                if not running:
                    break
                if time.monotonic() >= deadline:
                    # Recovery reopens the old release without signalling the
                    # worker, so an unusually long job can finish safely.
                    raise TimeoutError('Worker drain exceeded one hour; its current job was not killed.')
                time.sleep(2)
            if self.worker_was_active:
                # The maintenance gate prevented another claim, and no job is
                # running, so systemd can now stop the idle worker safely.
                self.worker_signalled = True
                run(['systemctl', 'stop', WORKER])
                self.wait_worker_stopped()
            self.drained = True
            if self.migrate:
                self.backup_database()
                print('Applying the candidate database migrations.', flush=True)
                self.migration_started = True
                run(['systemctl', 'start', f'rosbag-analyser-migrate@{self.candidate.name}.service'], timeout=600)
            self.activate(self.candidate)
            run(['systemctl', 'is-active', '--quiet', API, WORKER])
            MAINTENANCE.unlink()
            self.started = False
            print('Release healthy; application writes and queued processing reopened.', flush=True)
        except BaseException:
            self.recover()
            raise


def main():
    if len(sys.argv) == 5 and sys.argv[1] == 'plan':
        mode, migrate, dependencies = plan(Path(sys.argv[2]), sys.argv[3], sys.argv[4])
        print(mode, str(migrate).lower(), str(dependencies).lower())
    elif len(sys.argv) == 5 and sys.argv[1] == 'upgrade':
        if os.geteuid() != 0:
            raise ValueError('Upgrade must run as root on the configured VM.')
        Upgrade(sys.argv[2], sys.argv[3], sys.argv[4] == 'true',
                os.environ.get('ROS_BAG_ANALYSER_DEPLOY_TRANSFER_DIRECTORY')).execute()
    else:
        raise ValueError('Usage: deploy_release.py plan REPOSITORY PREVIOUS CANDIDATE | upgrade CANDIDATE PREVIOUS MIGRATE')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'deploy: {error}', file=sys.stderr)
        raise SystemExit(1)
