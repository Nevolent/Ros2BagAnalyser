from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_served_package_excludes_recording_and_reference_payloads() -> None:
    package = ROOT / "src" / "rosbag_analyser" / "web"
    names = {path.name for path in package.rglob("*") if path.is_file()}

    assert "figure8-front.mp4" not in names
    assert "figure8-top-view.mp4" not in names
    assert "figure8-imu-bundle.json" not in names
    assert "__MACOSX" not in {path.name for path in package.rglob("*")}


def test_served_shell_has_review_routes_recorded_column_and_controls() -> None:
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
