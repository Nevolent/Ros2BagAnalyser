from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).parents[2]
SCANNED_ROOTS = (ROOT / "deploy", ROOT / "docs" / "NAS_TRIAL_RUNBOOK.md", ROOT / "docs" / "ENGINEER_TRIAL_GUIDE.md")
TEXT_SUFFIXES = {"", ".conf", ".in", ".md", ".py", ".service", ".template"}


def deployment_text_files() -> tuple[Path, ...]:
    files: list[Path] = []
    for root in SCANNED_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in TEXT_SUFFIXES
        )
    return tuple(files)


def test_deployment_assets_contain_no_embedded_secret_or_generated_payload() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in deployment_text_files()
    )

    assert "-----BEGIN PRIVATE KEY-----" not in combined
    assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in combined
    assert re.search(r"postgresql://[^\s:@/]+:[^\s@/]+@", combined) is None
    assert re.search(r"AKIA[0-9A-Z]{16}", combined) is None
    assert re.search(r"\b10(?:\.\d{1,3}){3}\b", combined) is None
    assert re.search(r"\b192\.168(?:\.\d{1,3}){2}\b", combined) is None
    assert re.search(
        r"\b172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}\b", combined
    ) is None
    for suffix in (".db3", ".mcap", ".mp4", ".avi", ".dump"):
        assert not any(path.suffix == suffix for path in (ROOT / "deploy").rglob("*"))
