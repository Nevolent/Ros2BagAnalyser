from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[2]


def test_git_deployment_launcher_is_local_clean_and_remote_revision_guarded() -> None:
    launcher = (ROOT / "deploy-vm").read_text(encoding="utf-8")

    assert "Usage: ./deploy-vm" in launcher
    assert "must have mode 600 or 400" in launcher
    assert "git -C \"$project_root\" diff --quiet" in launcher
    assert "git -C \"$project_root\" diff --cached --quiet" in launcher
    assert "ls-files --others --exclude-standard" in launcher
    assert "ls-remote --exit-code --heads origin" in launcher
    assert "BatchMode=yes" in launcher
    assert "StrictHostKeyChecking=yes" in launcher
    assert "sudo --non-interactive" in launcher
    assert "deploy-from-git" in launcher


def test_vm_git_deployment_preserves_immutable_release_and_refuses_sensitive_changes() -> None:
    deployer = (ROOT / "deploy" / "scripts" / "deploy-from-git").read_text(
        encoding="utf-8"
    )

    assert 'repository_root="$deployment_root/repository"' in deployer
    assert 'current_link="$deployment_root/current"' in deployer
    assert "status --porcelain" in deployer
    assert "git -C \"$repository_root\" pull --ff-only origin \"$branch\"" in deployer
    assert "the VM resolved a different revision" in deployer
    assert "persistence/migrations" in deployer
    assert "runtime-requirements.in" in deployer
    assert "deploy/systemd" in deployer
    assert "deploy/scripts/*" in deployer
    assert '"$current_link/deploy/scripts/drain-worker"' in deployer
    assert "systemctl restart rosbag-analyser-api.service" in deployer
    assert "systemctl restart rosbag-analyser-worker.service" in deployer
    assert "activate-release" in deployer
    assert "build-release" in deployer
    assert "rescan" not in deployer
    assert "prepare" not in deployer


def test_git_deployment_help_needs_no_private_settings() -> None:
    result = subprocess.run(
        ["bash", str(ROOT / "deploy-vm"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Usage: ./deploy-vm" in result.stdout


def test_deployment_private_and_generated_files_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "*.pgpass",
        "*.pem",
        "*.key",
        "*.htpasswd",
        "source.cifs-credentials",
        "vm-deploy.env",
        "wheelhouse/",
        "*.tar.gz",
        "*.dump",
        "*-inventory.json",
        "*-manifest.json",
    ):
        assert pattern in ignored
