"""SSH transport with native sudo prompts kept separate from report streams."""
from __future__ import annotations

import argparse
import base64
import json
import re
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
        capture_output: bool = True) -> subprocess.CompletedProcess:
    envelope = json.dumps({'command': command, 'stdin': payload.decode('utf-8'),
                           'capture_output': capture_output}).encode()
    tty = terminal() if sudo else None
    if tty is None:
        prefix = ['sudo', '--non-interactive'] if sudo else []
        result = subprocess.run(ssh_command(settings, prefix + ['python3', '-c', RUN]),
                                input=envelope, capture_output=capture_output, timeout=timeout)
        if result.stderr and b'sudo: a password is required' in result.stderr:
            result.stderr += b'Run this command in an interactive terminal to enter the VM sudo password.\n'
        return result

    with tty:
        staged = subprocess.run(ssh_command(settings, ['python3', '-c', STAGE]),
                                input=envelope, capture_output=True, timeout=30)
        if staged.returncode:
            return staged
        directory = staged.stdout.decode().strip()
        if not re.fullmatch(r'/tmp/rosbag-vm-[A-Za-z0-9_-]+', directory):
            raise ValueError('SSH returned an invalid temporary report directory.')
        remote = ssh_command(settings, ['sudo', '--', 'python3', '-c', RUN_STAGED, directory], tty=True)
        print('Connecting to the VM terminal; sudo may ask for your VM password.', file=sys.stderr, flush=True)
        interrupted = None
        try:
            # Inherit terminal output; never capture the password conversation.
            result = subprocess.run(remote, stdin=tty, stdout=tty, stderr=tty, timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            interrupted = error
            result = subprocess.CompletedProcess(remote, 124 if isinstance(error, subprocess.TimeoutExpired) else 130)
        finally:
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
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        result = run({'SSH': args.ssh, 'HOST': args.host, 'USER': args.user},
                     args.command, sys.stdin.buffer.read(), sudo=True, capture_output=False)
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
        return result.returncode
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'vm: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
