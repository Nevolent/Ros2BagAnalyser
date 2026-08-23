from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from rosbag_analyser.deployment import DeploymentConfigurationError
from rosbag_analyser.preflight import (
    validate_private_file,
    validate_release_manifest,
    verify_probe_capability,
)


def test_private_environment_file_requires_regular_nonsymlink_tight_mode(
    tmp_path: Path,
) -> None:
    private = tmp_path / "application.env"
    private.write_text("PLACEHOLDER=value\n", encoding="utf-8")
    private.chmod(0o600)

    validate_private_file(private, required_owner_uid=os.getuid())

    private.chmod(0o644)
    with pytest.raises(DeploymentConfigurationError, match="mode"):
        validate_private_file(private, required_owner_uid=os.getuid())
    private.chmod(0o600)
    alias = tmp_path / "alias.env"
    alias.symlink_to(private)
    with pytest.raises(DeploymentConfigurationError, match="symbolic link"):
        validate_private_file(alias, required_owner_uid=os.getuid())


def test_release_manifest_binds_clean_source_and_dependency_checksum(
    tmp_path: Path,
) -> None:
    dependency_manifest = tmp_path / "wheelhouse.sha256"
    dependency_manifest.write_text(
        "a" * 64 + "  dependency.whl\n", encoding="utf-8"
    )
    release_contract = tmp_path / "release-contract.json"
    release_contract.write_text('{"schema_version":1}\n', encoding="utf-8")
    dependency_checksum = hashlib.sha256(dependency_manifest.read_bytes()).hexdigest()
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "release_id": "v1-20260816.1",
                "application_version": "0.1.0",
                "source_revision": "b" * 40,
                "source_archive_sha256": "c" * 64,
                "dependency_manifest_sha256": dependency_checksum,
                "release_contract_sha256": hashlib.sha256(
                    release_contract.read_bytes()
                ).hexdigest(),
                "worktree_clean": True,
                "built_at": "2026-08-16T12:00:00Z",
                "build_operator": "release-operator",
            }
        ),
        encoding="utf-8",
    )

    document = validate_release_manifest(
        manifest,
        dependency_manifest,
        release_contract,
        expected_release_id="v1-20260816.1",
    )

    assert document["source_revision"] == "b" * 40

    dependency_manifest.write_text("changed\n", encoding="utf-8")
    with pytest.raises(DeploymentConfigurationError, match="dependency identity"):
        validate_release_manifest(
            manifest,
            dependency_manifest,
            release_contract,
            expected_release_id="v1-20260816.1",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worktree_clean", False),
        ("source_revision", "dirty"),
        ("source_archive_sha256", "not-a-digest"),
        ("build_operator", ""),
    ],
)
def test_release_manifest_rejects_unidentified_source(
    tmp_path: Path, field: str, value: object
) -> None:
    dependency_manifest = tmp_path / "wheelhouse.sha256"
    dependency_manifest.write_text("manifest\n", encoding="utf-8")
    release_contract = tmp_path / "release-contract.json"
    release_contract.write_text('{"schema_version":1}\n', encoding="utf-8")
    manifest_data = {
        "schema_version": 1,
        "release_id": "v1-20260816.1",
        "application_version": "0.1.0",
        "source_revision": "b" * 40,
        "source_archive_sha256": "c" * 64,
        "dependency_manifest_sha256": hashlib.sha256(
            dependency_manifest.read_bytes()
        ).hexdigest(),
        "release_contract_sha256": hashlib.sha256(
            release_contract.read_bytes()
        ).hexdigest(),
        "worktree_clean": True,
        "built_at": "2026-08-16T12:00:00Z",
        "build_operator": "release-operator",
    }
    manifest_data[field] = value
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

    with pytest.raises(DeploymentConfigurationError):
        validate_release_manifest(
            manifest,
            dependency_manifest,
            release_contract,
            expected_release_id="v1-20260816.1",
        )


def test_ffprobe_capability_rejects_unexpected_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        stdout = "unexpected tool\n"

    monkeypatch.setattr(
        "rosbag_analyser.preflight.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    with pytest.raises(DeploymentConfigurationError, match="ffprobe"):
        verify_probe_capability(Path("/usr/bin/ffprobe"))
