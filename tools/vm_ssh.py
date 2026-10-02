"""SSH transport with native sudo prompts kept separate from report streams."""
from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import os
from pathlib import Path
import tempfile
import threading
import json
import re
import selectors
import time
import shlex
import subprocess
import sys


# Send code and input over stdin, avoiding the Windows command-line length limit.
RUN = """import json,subprocess,sys
request=json.load(sys.stdin)
result=subprocess.run(request['command'],input=request['stdin'].encode('utf-8'))
sys.exit(result.returncode if result.returncode >= 0 else 128-result.returncode)
"""

STAGE = """import os,sys,tempfile,shutil
from pathlib import Path
os.umask(0o077)
directory=Path(tempfile.mkdtemp(prefix='rosbag-vm-',dir='/tmp'))
try:
    (directory/'request.json').write_bytes(sys.stdin.buffer.read())
    (directory/'stdout').touch()
    (directory/'stderr').touch()
except BaseException:
    shutil.rmtree(directory)
    raise
print(directory)
"""

# sudo authenticates before this code starts. Only command output is redirected;
# the password travels directly between the user's terminal, SSH and sudo.
RUN_STAGED = """import json,os,subprocess,sys
from pathlib import Path
directory=Path(sys.argv[1])
request=json.loads((directory/'request.json').read_text())
if request.get('deployment_backup'):
    os.environ['ROS_BAG_ANALYSER_DEPLOY_TRANSFER_DIRECTORY']=str(directory)
if request['capture_output']:
    for name,descriptor in [('stdout',1),('stderr',2)]:
        with (directory/name).open('wb') as stream:
            os.dup2(stream.fileno(),descriptor)
result=subprocess.run(request['command'],input=request['stdin'].encode('utf-8'))
sys.exit(result.returncode if result.returncode >= 0 else 128-result.returncode)
"""

COLLECT = """import base64,json,shutil,sys
from pathlib import Path
directory=Path(sys.argv[1])
try:
    result={}
    for name in ['stdout','stderr']:
        with (directory/name).open('rb') as stream:
            data=stream.read(64*1024*1024+1)
        if len(data)>64*1024*1024:
            raise ValueError('VM report exceeds transport limit')
        result[name]=base64.b64encode(data).decode('ascii')
    print(json.dumps(result))
finally:
    shutil.rmtree(directory)
"""


# Backup bytes use a separate SSH stream. They never enter report text or a TTY.
BACKUP_STATUS = """import json,os,stat,sys
from pathlib import Path
root=Path(sys.argv[1]); marker=root/'backup.json'
if not marker.exists():
    print('null'); sys.exit(0)
details=marker.lstat()
if not stat.S_ISREG(details.st_mode) or details.st_uid!=os.getuid() or details.st_mode&0o777!=0o600:
    raise ValueError('Unsafe backup transfer marker')
with marker.open() as stream: record=json.loads(stream.read(4096))
print(json.dumps(record))
"""

STREAM_BACKUP = """import os,shutil,stat,sys
from pathlib import Path
path=Path(sys.argv[1])/'backup.dump'
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
with os.fdopen(fd,'rb') as stream:
    details=os.fstat(stream.fileno())
    if not stat.S_ISREG(details.st_mode) or details.st_uid!=os.getuid() or details.st_mode&0o777!=0o600:
        raise ValueError('Unsafe backup transfer file')
    if details.st_size!=int(sys.argv[2]): raise ValueError('Backup size changed')
    shutil.copyfileobj(stream,sys.stdout.buffer,1024*1024)
"""

ACK_BACKUP = """import json,os,sys
from pathlib import Path
root=Path(sys.argv[1]); temporary=root/'backup-ack.partial'
record=json.loads(sys.stdin.buffer.read(4096))
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'w') as stream: json.dump(record,stream)
os.replace(temporary,root/'backup-ack.json')
"""


def receive_backup(settings, directory, target, record, done=None):
    size, digest = record.get('size'), record.get('sha256')
    if not isinstance(size, int) or not 0 < size <= 10 * 1024**3 or not re.fullmatch(r'[0-9a-f]{64}', str(digest)):
        raise ValueError('Invalid database recovery copy identity or size.')
    # Only a newly created private local directory is used; failed transfers
    # leave the verified VM backup in place and never acknowledge migration.
    destination = target / 'database.dump'
    descriptor, temporary_name = tempfile.mkstemp(prefix='backup-', suffix='.partial', dir=target)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, 'wb') as output, tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(ssh_command(settings, ['python3', '-c', STREAM_BACKUP, directory, str(size)]),
                                       stdout=subprocess.PIPE, stderr=errors)
            total, checksum = 0, hashlib.sha256()
            try:
                deadline = time.monotonic() + 600
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        if time.monotonic() >= deadline or (done is not None and done.is_set()):
                            raise ValueError('Database backup transfer did not finish before its deadline.')
                        if not selector.select(timeout=1):
                            continue
                        chunk = os.read(process.stdout.fileno(), 1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > size:
                            raise ValueError('Database backup exceeded its declared size.')
                        output.write(chunk)
                        checksum.update(chunk)
                if process.wait(timeout=30):
                    raise ValueError('SSH could not transfer the database backup.')
                if total != size or checksum.hexdigest() != digest:
                    raise ValueError('The workstation database backup checksum did not match.')
                output.flush()
                os.fsync(output.fileno())
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
        if destination.exists() or destination.is_symlink():
            raise ValueError('The local database backup target already exists.')
        temporary.rename(destination)
        metadata = target / 'backup.json'
        metadata.write_text(json.dumps(record, indent=2) + '\n')
        metadata.chmod(0o600)
        # Persist the rename before acknowledging the recovery copy.
        descriptor = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        acknowledged = subprocess.run(ssh_command(settings, ['python3', '-c', ACK_BACKUP, directory]),
                                      input=json.dumps(record).encode(), capture_output=True, timeout=30)
        if acknowledged.returncode:
            raise ValueError('Could not acknowledge the verified backup to the VM.')
        print(f'Verified recovery copy: {destination}', file=sys.stderr, flush=True)
    finally:
        temporary.unlink(missing_ok=True)


def backup_monitor(settings, directory, target, done, failures):
    try:
        while not done.is_set():
            result = subprocess.run(ssh_command(settings, ['python3', '-c', BACKUP_STATUS, directory]),
                                    capture_output=True, timeout=20)
            if result.returncode:
                raise ValueError('Could not read the VM backup transfer status.')
            record = json.loads(result.stdout)
            if record is not None:
                receive_backup(settings, directory, target, record, done)
                return
            done.wait(1)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        failures.append(str(error))
        try:
            subprocess.run(ssh_command(settings, ['python3', '-c', ACK_BACKUP, directory]),
                           input=json.dumps({'error': str(error)}).encode(), capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            pass


def ssh_command(settings: dict[str, str], command: list[str], *, tty: bool = False) -> list[str]:
    return [settings['SSH'], '-tt' if tty else '-T', '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
            '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=2', f"{settings['USER']}@{settings['HOST']}",
            shlex.join(command)]


def terminal():
    # Deployment's stdin contains its script, so check the controlling terminal.
    if not sys.stderr.isatty():
        return None
    try:
        return open('/dev/tty', 'r+b', buffering=0)
    except OSError:
        return None


def run(settings: dict[str, str], command: list[str], payload: bytes, *,
        sudo: bool = False, timeout: int | None = None,
        capture_output: bool = True, deployment_backup: Path | None = None) -> subprocess.CompletedProcess:
    if deployment_backup is not None:
        deployment_backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if deployment_backup.parent.resolve() != deployment_backup.parent:
            raise ValueError('The local deployment report parent must be canonical.')
        deployment_backup.mkdir(mode=0o700)
    envelope = json.dumps({'command': command, 'stdin': payload.decode('utf-8'),
                           'capture_output': capture_output, 'deployment_backup': deployment_backup is not None}).encode()
    tty = terminal() if sudo else None
    if tty is None and deployment_backup is None:
        prefix = ['sudo', '--non-interactive'] if sudo else []
        result = subprocess.run(ssh_command(settings, prefix + ['python3', '-c', RUN]),
                                input=envelope, capture_output=capture_output, timeout=timeout)
        if result.stderr and b'sudo: a password is required' in result.stderr:
            result.stderr += b'Run this command in an interactive terminal to enter the VM sudo password.\n'
        return result

    with (tty if tty is not None else contextlib.nullcontext()):
        staged = subprocess.run(ssh_command(settings, ['python3', '-c', STAGE]),
                                input=envelope, capture_output=True, timeout=30)
        if staged.returncode:
            return staged
        directory = staged.stdout.decode().strip()
        if not re.fullmatch(r'/tmp/rosbag-vm-[A-Za-z0-9_-]+', directory):
            raise ValueError('SSH returned an invalid temporary report directory.')
        failures, done, monitor = [], threading.Event(), None
        if deployment_backup is not None:
            monitor = threading.Thread(target=backup_monitor, args=(settings, directory, deployment_backup, done, failures))
            monitor.start()
        prefix = ['sudo', '--'] if tty is not None else ['sudo', '--non-interactive']
        remote = ssh_command(settings, prefix + ['python3', '-c', RUN_STAGED, directory], tty=tty is not None)
        print('Connecting to the VM terminal; sudo may ask for your VM password.', file=sys.stderr, flush=True)
        interrupted = None
        try:
            # Inherit terminal output; never capture the password conversation.
            result = subprocess.run(remote, stdin=tty or subprocess.DEVNULL,
                                    stdout=tty, stderr=tty, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            interrupted = error
            result = subprocess.CompletedProcess(remote, 124 if isinstance(error, subprocess.TimeoutExpired) else 130)
        finally:
            done.set()
            if monitor is not None:
                monitor.join(timeout=55)
            try:
                collected = subprocess.run(ssh_command(settings, ['python3', '-c', COLLECT, directory]),
                                           capture_output=True, timeout=30)
                if collected.returncode:
                    raise ValueError(collected.stderr.decode('utf-8', errors='replace').strip())
                streams = json.loads(collected.stdout)
                output = base64.b64decode(streams['stdout'], validate=True)
                errors = base64.b64decode(streams['stderr'], validate=True)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                output = b''
                errors = (f'Could not retrieve/clean up the VM report in {directory}: {error}\n').encode()
        if failures:
            errors += ('Database backup transfer failed: ' + '; '.join(failures) + '\n').encode()
            if not result.returncode:
                result.returncode = 1
        if isinstance(interrupted, subprocess.TimeoutExpired):
            raise subprocess.TimeoutExpired(remote, timeout, output=output, stderr=errors)
        if isinstance(interrupted, KeyboardInterrupt):
            errors += b'VM command interrupted.\n'
        if result.returncode and not output and not errors:
            errors = b'VM command or sudo authentication failed; see the terminal output above.\n'
        return subprocess.CompletedProcess(remote, result.returncode, output, errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('ssh', 'host', 'user'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--deployment', action='store_true', help='Copy and acknowledge migration backups on this PC')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        backup = None
        if args.deployment:
            import datetime, uuid
            identity = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
            backup = Path(__file__).resolve().parents[1] / '.vm-reports' / (identity + '-deploy')
        result = run({'SSH': args.ssh, 'HOST': args.host, 'USER': args.user},
                     args.command, sys.stdin.buffer.read(), sudo=True, capture_output=False, deployment_backup=backup)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        return result.returncode
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'vm: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
