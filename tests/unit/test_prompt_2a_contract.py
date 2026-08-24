from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_prompt_2a_reference_hashes() -> None:
    expected = {
        "archive/index.html": "5373286fcbb810cf57052a2e93c6d7e23fa1a888100635496ca8524e488f85c0",
        "archive/styles.css": "01eb93298827c4eb430f8e135184ad0a70904193cafa5d6dc05946195388f3d0",
        "archive/script.js": "a5d85e834c7bf6fa5fd8c38f3b917d451ed4857f3df50e43d8e75423427246e9",
        "archive/assets/tech-trace-icon.svg": "b2fb92cb3af87871869f2c826d7a17e4617e9572ef82c08915c15f74d4c3646a",
    }

    assert {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected
    } == expected


def test_served_prompt_2a_package_excludes_reference_mock_payloads() -> None:
    package = ROOT / "src" / "rosbag_analyser" / "web"
    names = {path.name for path in package.rglob("*") if path.is_file()}

    assert "figure8-front.mp4" not in names
    assert "figure8-top-view.mp4" not in names
    assert "figure8-imu-bundle.json" not in names
    assert "__MACOSX" not in {path.name for path in package.rglob("*")}


def test_served_prompt_2a_shell_has_only_approved_routes_and_reviewed_recorded_column() -> None:
    html = (ROOT / "src" / "rosbag_analyser" / "web" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "Experiments" not in html
    assert "Files" not in html
    assert 'data-sort="recorded"' in html
    assert ">Recorded<" in html.split("</thead>", 1)[0]
    assert 'id="analysis-filter-menu" role="listbox"' in html
    assert "<select" not in html.split('class="table-filter-bar"', 1)[1].split("</section>", 1)[0]
    assert 'id="prepare-dialog"' in html
    assert 'id="cancel-job-dialog"' in html
