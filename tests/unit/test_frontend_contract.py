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
