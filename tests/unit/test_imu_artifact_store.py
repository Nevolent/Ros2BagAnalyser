from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import pytest

from rosbag_analyser.artifact_store import (
    ArtifactStore,
    ArtifactStoreError,
    SeriesColumnExpectation,
)


def _store(derived: Path) -> ArtifactStore:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None
    return ArtifactStore(
        derived,
        Path(ffmpeg),
        Path(ffprobe),
        "imu_series",
    )


def _manifest(path: Path, identity: str) -> dict[str, object]:
    details = path.stat(follow_symlinks=False)
    return {
        "artifact_kind": "imu_series",
        "cache_identity": identity,
        "output": {
            "size_bytes": details.st_size,
            "file_identity": {
                "device_id": details.st_dev,
                "inode": details.st_ino,
                "mtime_ns": details.st_mtime_ns,
            },
        },
    }


def _columns(
    finite_count: int,
    non_finite_count: int,
    minimum_value: float | None,
    maximum_value: float | None,
) -> tuple[SeriesColumnExpectation, ...]:
    return tuple(
        SeriesColumnExpectation(
            id=f"series_{index}",
            finite_count=finite_count,
            non_finite_count=non_finite_count,
            minimum_value=minimum_value,
            maximum_value=maximum_value,
        )
        for index in range(6)
    )


def test_series_is_validated_then_atomically_published_and_reopened(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(31)
    series = workspace / "series.json"
    series.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "samples": [
                    ["-10", 2.5, 2.5, 2.5, 2.5, 2.5, 2.5],
                    ["20", None, None, None, None, None, None],
                    ["20", -1.0, -1.0, -1.0, -1.0, -1.0, -1.0],
                ],
            },
            separators=(",", ":"),
        )
    )

    validation = store.validate_series(
        series,
        expected_schema_version=2,
        expected_sample_count=3,
        expected_columns=_columns(2, 1, -1.0, 2.5),
        expected_coverage_start_ns=-10,
        expected_coverage_end_ns=20,
    )
    identity = "3" * 64
    manifest = _manifest(series, identity)
    published = store.publish_series(workspace, 31, identity, manifest)

    assert published.output_relative_path == (
        f"rosbag-analyser/artifacts/imu_series/{identity[:2]}/"
        f"{identity}/series.json"
    )
    assert published.size_bytes == validation.size_bytes
    store.validate_series_artifact(
        published.output_relative_path,
        published.size_bytes,
        identity,
        manifest,
    )
    opened = store.open_series(
        published.output_relative_path,
        published.size_bytes,
        identity,
        manifest,
    )
    try:
        assert os.read(opened.descriptor, opened.stat_result.st_size).startswith(
            b'{"schema_version":2'
        )
    finally:
        os.close(opened.descriptor)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (
            '{"schema_version":2,"samples":[["0",NaN,1,1,1,1,1]]}',
            "imu_series_validation_failed",
        ),
        (
            '{"schema_version":2,"samples":['
            '["10",1,1,1,1,1,1],["0",2,2,2,2,2,2]]}',
            "imu_series_validation_mismatch",
        ),
    ],
)
def test_invalid_json_constant_and_unordered_time_are_rejected(
    tmp_path: Path, payload: str, expected_code: str
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(32)
    series = workspace / "series.json"
    series.write_text(payload)

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_series(
            series,
            expected_schema_version=2,
            expected_sample_count=1 if "NaN" in payload else 2,
            expected_columns=(
                _columns(0, 1, None, None)
                if "NaN" in payload
                else _columns(2, 0, 1.0, 2.0)
            ),
            expected_coverage_start_ns=0,
            expected_coverage_end_ns=0 if "NaN" in payload else 10,
        )

    assert captured.value.code == expected_code


def test_published_series_tampering_is_not_served(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(33)
    series = workspace / "series.json"
    series.write_text(
        '{"schema_version":2,"samples":[["0",1,1,1,1,1,1]]}'
    )
    identity = "4" * 64
    manifest = _manifest(series, identity)
    published = store.publish_series(workspace, 33, identity, manifest)
    published_path = derived / published.output_relative_path
    published_path.write_text(
        '{"schema_version":2,"samples":[["0",2,2,2,2,2,2]]}'
    )

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_series_artifact(
            published.output_relative_path,
            published.size_bytes,
            identity,
            manifest,
        )

    assert captured.value.code == "artifact_file_changed"


def test_invalid_imu_manifest_uses_artifact_neutral_failure_text(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(34)
    series = workspace / "series.json"
    series.write_text(
        '{"schema_version":2,"samples":[["0",1,1,1,1,1,1]]}'
    )
    identity = "5" * 64
    manifest = _manifest(series, identity)
    published = store.publish_series(workspace, 34, identity, manifest)
    manifest_path = derived / published.output_relative_path
    manifest_path = manifest_path.parent / "manifest.json"
    manifest_path.write_text("not valid JSON")

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_series_artifact(
            published.output_relative_path,
            published.size_bytes,
            identity,
            manifest,
        )

    assert captured.value.code == "artifact_manifest_invalid"
    assert "artifact" in captured.value.safe_message.lower()
    assert "preview" not in captured.value.safe_message.lower()
