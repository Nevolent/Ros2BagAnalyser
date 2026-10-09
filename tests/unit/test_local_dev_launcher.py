from __future__ import annotations

from pathlib import Path
import os
import signal
import socket
import subprocess
import time
import urllib.request

import pytest


PROJECT_ROOT = Path(__file__).parents[2]


def test_dev_help_is_available_without_local_configuration() -> None:
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "dev"), "help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Usage: ./dev COMMAND" in result.stdout
    assert "start" in result.stdout
    assert "open" in result.stdout
    assert "status" in result.stdout
    assert "logs" in result.stdout
    assert "restart" in result.stdout
    assert "stop" in result.stdout
    assert "migrate" in result.stdout
    assert "rescan" in result.stdout
    assert "install" in result.stdout


def test_dev_keeps_start_separate_from_explicit_rescan() -> None:
    script = (PROJECT_ROOT / "dev").read_text()

    start_body = script[
        script.index("start_application() {") : script.index("open_browser() {")
    ]
    rescan_body = script[
        script.index("rescan_archive() {") : script.index('command_name="${1:-help}"')
    ]

    assert "/api/catalog/rescan" not in start_body
    assert "--request POST" in rescan_body
    assert "/api/catalog/rescan" in rescan_body
    assert "archive and derived roots must not overlap" in script
    assert "must have mode 600 or 400" in script
    assert "application_is_healthy" in start_body
    assert "frontend_assets_changed" in start_body
    assert 'stop_process "API"' in start_body
    assert "wait_for_application" in start_body
    assert "start_process api" in start_body
    assert "start_process worker" in start_body
    assert "systemctl --user" not in script


def test_service_wrapper_uses_private_configuration_and_one_worker() -> None:
    wrapper = (PROJECT_ROOT / "scripts/rosbag-analyser-service").read_text()

    assert ".config/rosbag-analyser/environment" in wrapper
    assert ".config/rosbag-analyser/database.env" in wrapper
    assert "urllib.parse.quote" in wrapper
    assert "set +u\n    source /opt/ros/humble/setup.bash\n    set -u" in wrapper
    assert "source /opt/ros/humble/setup.bash" in wrapper
    assert wrapper.count("exec .venv/bin/rosbag-analyser-worker") == 1


def test_dev_supervises_only_validated_private_processes() -> None:
    script = (PROJECT_ROOT / "dev").read_text()

    assert ".local/state/rosbag-analyser" in script
    assert (
        'nohup setsid "$project_root/scripts/rosbag-analyser-service" "$mode"'
        in script
    )
    assert '9>&- >>"$log_file"' in script
    assert 'kill -TERM "$pid"' in script
    assert "did not stop after 20 seconds; it was not force-killed" in script
    assert 'expected_path="$project_root/.venv/bin/$expected_command"' in script
    assert 'if [[ "$argument" == "$expected_path" ]]' in script
    assert 'process_is_running "$api_pid_file" "rosbag-analyser"' in script
    assert (
        'process_is_running "$worker_pid_file" "rosbag-analyser-worker"'
        in script
    )
    assert "flock --exclusive 9" in script


def test_windows_shortcut_runs_the_one_command_open_flow() -> None:
    installer = (
        PROJECT_ROOT / "support/windows/Install-RosbagAnalyserShortcut.ps1"
    ).read_text()

    assert 'Name = "Real data"; Argument = "real"' in installer
    assert 'Name = "Synthetic data"; Argument = "synthetic"' in installer
    assert "Ubuntu-22.04" in installer
    assert "Open-RosbagAnalyser.ps1" in installer
    launcher = (PROJECT_ROOT / "support/windows/Open-RosbagAnalyser.ps1").read_text()
    assert '--exec "$ProjectRoot/dev" open $Mode' in launcher


def test_dev_check_accepts_automatic_topic_discovery(tmp_path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "dev").write_text((PROJECT_ROOT / "dev").read_text())
    for name in (".venv/bin/rosbag-analyser", "scripts/rosbag-analyser-service"):
        command = project / name
        command.parent.mkdir(parents=True, exist_ok=True)
        command.write_text("#!/bin/sh\nexit 99\n")
        command.chmod(0o755)
    archive = tmp_path / "source"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    settings = tmp_path / "environment"
    settings.write_text(
        f"ROS_BAG_ANALYSER_ARCHIVE_ROOT={archive}\n"
        f"ROS_BAG_ANALYSER_DERIVED_ROOT={derived}\n"
    )
    secret = tmp_path / "database.env"
    secret.write_text("# No connection is made by the configuration check.\n")
    settings.chmod(0o600)
    secret.chmod(0o600)
    env = dict(
        os.environ,
        ROS_BAG_ANALYSER_SETTINGS_FILE=str(settings),
        ROS_BAG_ANALYSER_DATABASE_SECRET_FILE=str(secret),
    )
    env.pop("ROS_BAG_ANALYSER_FRONT_TOPIC", None)
    env.pop("ROS_BAG_ANALYSER_IMU_TOPIC", None)
    result = subprocess.run(
        ["bash", str(project / "dev"), "check"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "Configuration is valid." in result.stdout


class LocalLauncher:
    def __init__(self, root: Path) -> None:
        self.project = root / "project"
        self.project.mkdir()
        (self.project / "dev").write_text((PROJECT_ROOT / "dev").read_text())
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        self.state = root / "home/.local/state/rosbag-analyser"
        self.state.mkdir(parents=True)
        archive, derived = root / "source", root / "derived"
        archive.mkdir()
        derived.mkdir()
        settings, secret = root / "environment", root / "database.env"
        settings.write_text(
            f"ROS_BAG_ANALYSER_ARCHIVE_ROOT={archive}\n"
            f"ROS_BAG_ANALYSER_DERIVED_ROOT={derived}\n"
        )
        secret.write_text("# Synthetic services never connect to a database.\n")
        settings.chmod(0o600)
        secret.chmod(0o600)
        self.env = dict(
            os.environ,
            HOME=str(root / "home"),
            ROS_BAG_ANALYSER_SETTINGS_FILE=str(settings),
            ROS_BAG_ANALYSER_DATABASE_SECRET_FILE=str(secret),
            ROS_BAG_ANALYSER_DEV_URL=self.url,
            FAKE_API_PORT=str(port),
            FAKE_API_LISTEN="1",
            FAKE_API_DELAY="0",
            FAKE_REQUEST_LOG=str(root / "requests.log"),
        )
        self.children: list[subprocess.Popen] = []
        self.write_command(
            ".venv/bin/rosbag-analyser",
            '''#!/usr/bin/env python3
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        with open(os.environ["FAKE_REQUEST_LOG"], "a") as log:
            log.write(self.path + "\\n")
        if self.path == "/health/ready":
            time.sleep(float(os.environ["FAKE_API_DELAY"]))
        self.send_response(200 if self.path in {"/health/live", "/health/ready"} else 404)
        self.end_headers()

if os.environ["FAKE_API_LISTEN"] == "1":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ["FAKE_API_PORT"])), Handler).serve_forever()
else:
    while True:
        time.sleep(1)
''',
        )
        self.write_command(
            ".venv/bin/rosbag-analyser-worker",
            "#!/usr/bin/env python3\nimport time\nwhile True:\n    time.sleep(1)\n",
        )
        self.write_command(
            "scripts/rosbag-analyser-service",
            '''#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
case "$1" in
  api) exec "$project_root/.venv/bin/rosbag-analyser" ;;
  worker) exec "$project_root/.venv/bin/rosbag-analyser-worker" ;;
  migrate) echo migrated >> "$project_root/migrations.log" ;;
esac
''',
        )

    def write_command(self, name: str, content: str) -> None:
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755)

    def spawn(self, mode: str, **overrides: str) -> subprocess.Popen:
        name = "rosbag-analyser" if mode == "api" else "rosbag-analyser-worker"
        process = subprocess.Popen(
            [str(self.project / ".venv/bin" / name)],
            env=dict(self.env, **overrides),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.children.append(process)
        (self.state / f"{mode}.pid").write_text(f"{process.pid}\n")
        (self.state / f"{mode}.log").touch()
        return process

    def wait_for_api(self) -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(self.url + "/health/live", timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("Synthetic API did not listen")

    def run(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(self.project / "dev"), command],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=35,
        )

    def pid(self, mode: str) -> int:
        return int((self.state / f"{mode}.pid").read_text())

    def cleanup(self) -> None:
        # Only signal processes whose arguments identify this disposable project.
        for path in self.state.glob("*.pid"):
            pid = int(path.read_text())
            try:
                arguments = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                if any(str(self.project / ".venv/bin").encode() in arg for arg in arguments):
                    os.kill(pid, signal.SIGTERM)
            except (FileNotFoundError, ProcessLookupError):
                pass
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)


@pytest.fixture()
def local_launcher(tmp_path):
    launcher = LocalLauncher(tmp_path)
    try:
        yield launcher
    finally:
        launcher.cleanup()


def test_start_recovers_unresponsive_managed_api_without_restarting_worker(local_launcher):
    api = local_launcher.spawn("api", FAKE_API_LISTEN="0")
    worker = local_launcher.spawn("worker")

    result = local_launcher.run("start")

    assert result.returncode == 0, result.stderr
    assert "The managed API is not ready; restarting its process." in result.stdout
    assert "ROS 2 Bag Analyser is ready" in result.stdout
    assert local_launcher.pid("api") != api.pid
    assert local_launcher.pid("worker") == worker.pid
    assert worker.poll() is None
    assert api.wait(timeout=5) == -signal.SIGTERM
    requests = Path(local_launcher.env["FAKE_REQUEST_LOG"]).read_text().splitlines()
    assert "/health/ready" in requests
    assert "/api/recordings" not in requests


def test_start_reuses_ready_managed_api_when_worker_is_missing(local_launcher):
    api = local_launcher.spawn("api")
    local_launcher.wait_for_api()

    result = local_launcher.run("start")

    assert result.returncode == 0, result.stderr
    assert local_launcher.pid("api") == api.pid
    assert "unmanaged" not in result.stderr
    assert local_launcher.pid("worker") > 0
    worker_pid = local_launcher.pid("worker")
    again = local_launcher.run("start")
    assert again.returncode == 0, again.stderr
    assert "already running" in again.stdout
    assert local_launcher.pid("api") == api.pid
    assert local_launcher.pid("worker") == worker_pid
    assert (local_launcher.project / "migrations.log").read_text() == "migrated\n"


@pytest.mark.parametrize("changed_file", [
    "src/rosbag_analyser/front_preview.py",
    "src/rosbag_analyser/worker.py",
    "src/rosbag_analyser/persistence/migrations/0011_encoder_series.sql",
    "pyproject.toml",
])
def test_start_reloads_old_worker_even_when_api_already_uses_new_code(
    local_launcher, changed_file,
):
    worker = local_launcher.spawn("worker")
    api = local_launcher.spawn("api")
    local_launcher.wait_for_api()
    # Reproduce an API restarted after an update with a worker predating it.
    now = time.time()
    os.utime(local_launcher.state / "worker.pid", (now - 20, now - 20))
    changed = local_launcher.project / changed_file
    changed.parent.mkdir(parents=True, exist_ok=True)
    changed.write_text("# Updated backend\n")
    os.utime(changed, (now - 10, now - 10))

    result = local_launcher.run("start")

    assert result.returncode == 0, result.stderr
    assert "Backend files changed; reloading the API and worker processes." in result.stdout
    assert local_launcher.pid("api") != api.pid
    assert local_launcher.pid("worker") != worker.pid
    assert worker.wait(timeout=5) == -signal.SIGTERM
    assert api.wait(timeout=5) == -signal.SIGTERM
    refreshed = (local_launcher.pid("api"), local_launcher.pid("worker"))
    again = local_launcher.run("start")
    assert again.returncode == 0, again.stderr
    assert "already running" in again.stdout
    assert (local_launcher.pid("api"), local_launcher.pid("worker")) == refreshed
    assert (local_launcher.project / "migrations.log").read_text() == "migrated\n"


def test_start_reloads_backend_before_starting_a_missing_worker(local_launcher):
    api = local_launcher.spawn("api")
    local_launcher.wait_for_api()
    changed = local_launcher.project / "src/rosbag_analyser/worker.py"
    changed.parent.mkdir(parents=True)
    changed.write_text("# New artifact support\n")

    result = local_launcher.run("start")

    assert result.returncode == 0, result.stderr
    assert local_launcher.pid("api") != api.pid
    assert local_launcher.pid("worker") > 0
    assert api.wait(timeout=5) == -signal.SIGTERM


def test_frontend_only_change_reloads_api_and_keeps_worker(local_launcher):
    api = local_launcher.spawn("api")
    worker = local_launcher.spawn("worker")
    local_launcher.wait_for_api()
    changed = local_launcher.project / "src/rosbag_analyser/web/react/index.html"
    changed.parent.mkdir(parents=True)
    changed.write_text("<html>Updated frontend</html>\n")

    result = local_launcher.run("start")

    assert result.returncode == 0, result.stderr
    assert "Frontend files changed" in result.stdout
    assert local_launcher.pid("api") != api.pid
    assert local_launcher.pid("worker") == worker.pid
    assert worker.poll() is None
    assert api.wait(timeout=5) == -signal.SIGTERM
    assert not (local_launcher.project / "migrations.log").exists()


def test_start_refuses_unmanaged_live_api_without_signalling_it(local_launcher):
    api = local_launcher.spawn("api")
    local_launcher.wait_for_api()
    (local_launcher.state / "api.pid").unlink()

    result = local_launcher.run("start")

    assert result.returncode == 1
    assert "an unmanaged application is already responding" in result.stderr
    assert api.poll() is None
    assert not (local_launcher.project / "migrations.log").exists()


def test_status_bounds_unresponsive_http_probe(local_launcher):
    local_launcher.spawn("api", FAKE_API_DELAY="60")
    local_launcher.wait_for_api()
    started = time.monotonic()

    result = local_launcher.run("status")

    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 8
    assert "API process                          running" in result.stdout
    assert "HTTP API                             unavailable" in result.stdout


def test_startup_deadline_includes_time_spent_waiting_for_http(local_launcher):
    local_launcher.env["FAKE_API_DELAY"] = "60"
    started = time.monotonic()

    result = local_launcher.run("start")

    assert result.returncode == 1
    # Twenty seconds for startup plus one bounded status probe for diagnostics.
    assert time.monotonic() - started < 29
    assert "The API and worker did not become ready" in result.stderr
    assert "API process                          running" in result.stderr
    assert "Serial worker                        running" in result.stderr
    assert "HTTP API                             unavailable" in result.stderr
