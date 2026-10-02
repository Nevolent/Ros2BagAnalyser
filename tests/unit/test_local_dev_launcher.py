from __future__ import annotations

from pathlib import Path
import os
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
