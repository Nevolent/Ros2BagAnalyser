from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).parents[2]
DEPLOY = ROOT / "deploy"


def run(command: list[str], *, environment: dict[str, str] | None = None):
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_rendered_proxy_validator_accepts_exact_dual_stack_values(
    tmp_path: Path,
) -> None:
    template = (DEPLOY / "nginx" / "rosbag-analyser.conf.template").read_text(
        encoding="utf-8"
    )
    rendered = (
        template.replace("trial.example.invalid", "trial.lab.test")
        .replace("192.0.2.10", "10.20.30.40")
        .replace("2001:db8::10", "fd12:3456::10")
    )
    config = tmp_path / "proxy.conf"
    config.write_text(rendered, encoding="utf-8")

    result = run(
        [
            str(DEPLOY / "scripts" / "validate-proxy"),
            str(config),
            "trial.lab.test",
            "10.20.30.40",
            "fd12:3456::10",
        ]
    )

    assert result.returncode == 0, result.stderr
    assert "valid" in result.stdout


def test_firewall_validator_rejects_public_any_and_checks_safe_render(
    tmp_path: Path,
) -> None:
    template = (DEPLOY / "firewall" / "rosbag-analyser.nft.template").read_text(
        encoding="utf-8"
    )
    rendered = (
        template.replace("192.0.2.0/24", "10.20.30.0/24")
        .replace("198.51.100.0/24", "10.30.40.0/24")
        .replace("2001:db8:1::/48", "fd12:3456:1::/48")
        .replace("2001:db8:2::/48", "fd12:3456:2::/48")
    )
    rules = tmp_path / "rules.nft"
    rules.write_text(rendered, encoding="utf-8")
    binary = tmp_path / "bin"
    binary.mkdir()
    fake_nft = binary / "nft"
    fake_nft.write_text(
        "#!/usr/bin/env bash\n[[ \"$1\" == --check && \"$2\" == --file ]]\n",
        encoding="utf-8",
    )
    fake_nft.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{binary}:{environment['PATH']}"

    accepted = run(
        [str(DEPLOY / "scripts" / "validate-firewall"), str(rules)],
        environment=environment,
    )
    assert accepted.returncode == 0, accepted.stderr

    rules.write_text(rendered.replace("10.30.40.0/24", "0.0.0.0/0"), encoding="utf-8")
    rejected = run(
        [str(DEPLOY / "scripts" / "validate-firewall"), str(rules)],
        environment=environment,
    )
    assert rejected.returncode != 0
    assert "public-any" in rejected.stderr


@pytest.mark.skipif(
    not os.environ.get("ROS_BAG_ANALYSER_TEST_NFT"),
    reason="real disposable nft syntax check not configured",
)
def test_real_nft_parser_accepts_rendered_dual_stack_rules(tmp_path: Path) -> None:
    template = (DEPLOY / "firewall" / "rosbag-analyser.nft.template").read_text(
        encoding="utf-8"
    )
    rendered = (
        template.replace("192.0.2.0/24", "10.20.30.0/24")
        .replace("198.51.100.0/24", "10.30.40.0/24")
        .replace("2001:db8:1::/48", "fd12:3456:1::/48")
        .replace("2001:db8:2::/48", "fd12:3456:2::/48")
    )
    rules = tmp_path / "rules.nft"
    rules.write_text(rendered, encoding="utf-8")

    result = run(
        [
            os.environ["ROS_BAG_ANALYSER_TEST_NFT"],
            "--check",
            "--file",
            str(rules),
        ]
    )

    assert result.returncode == 0, result.stderr
