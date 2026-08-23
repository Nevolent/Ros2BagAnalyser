from __future__ import annotations

from pathlib import Path
import subprocess


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

    assert "ROS 2 Bag Analyser.lnk" in installer
    assert "Ubuntu-22.04" in installer
    assert "--exec ./dev open" in installer
