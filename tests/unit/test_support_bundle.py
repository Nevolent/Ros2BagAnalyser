from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


MODULE_PATH = (
    Path(__file__).parents[2] / "deploy" / "scripts" / "support_bundle.py"
)
SPEC = importlib.util.spec_from_file_location("support_bundle", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
support_bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(support_bundle)


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess((), returncode, stdout, stderr)


def test_bundle_collects_only_selected_journal_metadata(monkeypatch) -> None:
    def fake_run(command):
        if command[0] == "journalctl":
            return completed(
                json.dumps(
                    {
                        "__REALTIME_TIMESTAMP": "1234",
                        "PRIORITY": "6",
                        "_SYSTEMD_UNIT": command[2],
                        "MESSAGE": "password=secret /private/source/recording",
                    }
                )
                + "\n"
            )
        if command[0] == "systemctl":
            return completed("active\n")
        return completed("tool 1.2.3\n")

    monkeypatch.setattr(support_bundle, "_run", fake_run)
    monkeypatch.setattr(
        support_bundle,
        "_health",
        lambda _base_url, endpoint: {"status": endpoint.rsplit("/", 1)[-1]},
    )

    bundle = support_bundle.build_bundle("http://127.0.0.1:8000")

    encoded = json.dumps(bundle)
    assert "password" not in encoded
    assert "secret" not in encoded
    assert "/private/source" not in encoded
    events = bundle["journal_event_metadata"]["rosbag-analyser-api.service"]
    assert events == [
        {
            "__REALTIME_TIMESTAMP": "1234",
            "PRIORITY": "6",
            "_SYSTEMD_UNIT": "rosbag-analyser-api.service",
        }
    ]


def test_main_rejects_non_loopback_url(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        support_bundle.sys,
        "argv",
        ["support_bundle.py", str(tmp_path / "bundle"), "https://example.test"],
    )

    with pytest.raises(SystemExit, match="only the loopback"):
        support_bundle.main()
