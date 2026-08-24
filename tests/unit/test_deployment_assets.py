from __future__ import annotations

import json
from pathlib import Path

from rosbag_analyser.front_preview import FRONT_TIMING_POLICY, PROCESSOR_VERSION
from rosbag_analyser.imu_series import (
    PROCESSOR_VERSION as IMU_PROCESSOR_VERSION,
    SERIES_SCHEMA_VERSION,
)
from rosbag_analyser.topdown_preview import (
    PROCESSOR_VERSION as TOPDOWN_PROCESSOR_VERSION,
)


ROOT = Path(__file__).parents[2]
DEPLOY = ROOT / "deploy"


def read(relative: str) -> str:
    return (DEPLOY / relative).read_text(encoding="utf-8")


def test_exactly_one_serial_worker_unit_and_no_implicit_work() -> None:
    units = tuple((DEPLOY / "systemd").glob("*"))
    worker_units = [path for path in units if "worker.service" in path.name]

    assert [path.name for path in worker_units] == [
        "rosbag-analyser-worker.service"
    ]
    joined = "\n".join(path.read_text(encoding="utf-8") for path in units)
    assert "rosbag-analyser-worker" in joined
    assert "rescan" not in joined
    assert "prepare" not in joined
    assert read("systemd/nginx-rosbag-analyser.conf") == (
        "[Unit]\nAfter=rosbag-analyser.target\n"
    )


def test_runtime_units_are_loopback_mount_ordered_and_hardened() -> None:
    for name in (
        "rosbag-analyser-api.service",
        "rosbag-analyser-worker.service",
    ):
        unit = read(f"systemd/{name}")
        assert "User=rosbag-analyser" in unit
        assert "UMask=0027" in unit
        assert "EnvironmentFile=/etc/rosbag-analyser/application.env" in unit
        assert "LoadCredential=database-pass:" in unit
        assert "After=network-online.target postgresql.service" in unit
        assert "srv-rosbag\\x2danalyser-source.mount" in unit
        assert "var-lib-rosbag\\x2danalyser-derived.mount" in unit
        assert "Restart=on-failure" in unit
        assert "StartLimitBurst=" in unit
        assert "NoNewPrivileges=yes" in unit
        assert "PrivateTmp=yes" in unit
        assert "ProtectSystem=strict" in unit
        assert "ProtectHome=yes" in unit
        assert "ReadOnlyPaths=/srv/rosbag-analyser/source" in unit
        assert "ReadWritePaths=/var/lib/rosbag-analyser/derived" in unit
        # Dependencies are startup wishes plus preflight checks; a later outage
        # must leave liveness available instead of causing a restart loop.
        assert "Wants=network-online.target postgresql.service" in unit
        assert "Requires=postgresql.service" not in unit

    assert "ExecStart=/opt/rosbag-analyser/current/deploy/scripts/run-service api" in read(
        "systemd/rosbag-analyser-api.service"
    )
    worker = read("systemd/rosbag-analyser-worker.service")
    assert "ExecStart=/opt/rosbag-analyser/current/deploy/scripts/run-service worker" in worker
    assert "TimeoutStopSec=" in worker
    assert "SendSIGKILL=yes" in worker
    runner = read("scripts/run-service")
    assert 'PGPASSFILE="$database_credential"' in runner
    assert "CREDENTIALS_DIRECTORY" in runner
    validator = read("scripts/validate-site")
    assert '$1 != "/run/postgresql"' in validator


def test_source_mount_is_read_only_and_derived_mount_is_distinct() -> None:
    source = read("systemd/rosbag-analyser-source.mount.template")
    derived = read("systemd/rosbag-analyser-derived.mount.template")

    assert "Type=cifs" in source
    assert "Options=ro,nosuid,nodev,noexec,_netdev" in source
    assert "credentials=/etc/rosbag-analyser/source.cifs-credentials" in source
    assert "password=" not in source
    assert "Where=/srv/rosbag-analyser/source" in source
    assert "Where=/var/lib/rosbag-analyser/derived" in derived
    assert "Options=rw,nosuid,nodev" in derived
    assert "/srv/rosbag-analyser/source" not in derived


def test_proxy_is_same_origin_bounded_and_never_serves_derived_files() -> None:
    proxy = read("nginx/rosbag-analyser.conf.template")
    headers = read("nginx/rosbag-analyser-proxy-headers.conf")
    validator = read("scripts/validate-proxy")

    for requirement in (
        "listen 192.0.2.10:443 ssl",
        "listen [2001:db8::10]:443 ssl",
        "server_name trial.example.invalid",
        "client_max_body_size 64k",
        "auth_basic_user_file",
        "autoindex off",
        "limit_req_zone",
        "if ($host !=",
        "if ($request_method !~ ^(GET|HEAD|POST)$)",
        "if ($rosbag_write_origin_denied)",
        "location = /docs",
        "location = /openapi.json",
        "server 127.0.0.1:8000",
        "(retry|pause|resume|cancel)",
        "(cancel|reorder|retry)",
    ):
        assert requirement in proxy
    assert '"" 1;' not in proxy
    assert "alias " not in proxy
    assert "root /var/lib/rosbag-analyser/derived" not in proxy
    assert "proxy_buffering off" in headers
    assert "proxy_cache off" in headers
    assert "proxy_set_header X-Forwarded-For $remote_addr" in headers
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for" not in headers
    assert 'proxy_set_header Authorization ""' in headers
    assert "proxy_set_header Range $http_range" in headers
    assert "proxy_set_header If-Range $http_if_range" in headers
    assert "127.0.0.1:8000" in validator
    assert "must not serve derived storage directly" in validator


def test_worker_drain_fails_closed_for_user_paused_work() -> None:
    drain = read("scripts/drain-worker")

    assert '"paused" || "$control_state" == "pause_requested"' in drain
    assert "Resume it to drain normally" in drain
    assert "this script changed nothing" in drain


def test_firewall_defaults_to_drop_for_both_ip_families() -> None:
    firewall = read("firewall/rosbag-analyser.nft.template")

    assert "table inet rosbag_analyser" in firewall
    assert "policy drop" in firewall
    assert "ip saddr @administration_ipv4 tcp dport 22 accept" in firewall
    assert "ip6 saddr @administration_ipv6 tcp dport 22 accept" in firewall
    assert "ip saddr @trial_ipv4 tcp dport 443 accept" in firewall
    assert "ip6 saddr @trial_ipv6 tcp dport 443 accept" in firewall
    for forbidden_port in ("8000", "5432", "2049"):
        assert f"dport {forbidden_port}" not in firewall


def test_release_scripts_fail_closed_and_do_not_run_migrations_on_startup() -> None:
    build = read("scripts/build-release")
    install = read("scripts/install-release")
    activate = read("scripts/activate-release")
    wheelhouse = read("scripts/build-wheelhouse")

    assert "status --porcelain" in build
    assert "A release cannot be built from an uncommitted" in build
    assert "sha256sum --check --strict SHA256SUMS" in build
    assert "! -name RELEASE-CONTENTS.sha256" in build
    assert "validate_release_archive.py" in install
    assert "--system-site-packages" not in install
    assert "INSTALLER-SHA256SUMS" in build
    assert "--platform manylinux_2_28_x86_64" in wheelhouse
    assert "--platform manylinux_2_17_x86_64" in wheelhouse
    assert "already exists; it was not replaced" in install
    assert "mv -T" in activate
    assert "migrate" not in read("systemd/rosbag-analyser-api.service")
    assert "migrate" not in read("systemd/rosbag-analyser-worker.service")


def test_release_contract_matches_accepted_processor_and_schema_identities() -> None:
    contract = json.loads(read("release-contract.json"))

    assert contract["processors"] == {
        "front_preview": PROCESSOR_VERSION,
        "front_timing_policy": FRONT_TIMING_POLICY,
        "imu_series": IMU_PROCESSOR_VERSION,
        "topdown_preview": TOPDOWN_PROCESSOR_VERSION,
    }
    assert contract["artifact_contracts"]["imu_series_schema"] == SERIES_SCHEMA_VERSION
    assert contract["database_schema"].endswith("0001-through-0007")
