from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest
import yaml

from conftest import create_recording, inventory, metadata_document
from rosbag_analyser.catalog import paths as catalog_paths
from rosbag_analyser.catalog import scanner as catalog_scanner
from rosbag_analyser.catalog.limits import POSTGRES_BIGINT_MAX
from rosbag_analyser.catalog.paths import CatalogScanLimits
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.types import (
    RootScanError,
    RosHealth,
    SourceCondition,
    SourceRole,
)


def test_scans_complete_recording_and_is_idempotent(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "unusual recording name")
    before = inventory(archive)
    scanner = CatalogScanner(archive)

    first = scanner.scan()
    second = scanner.scan()

    assert len(first.recordings) == 1
    recording = first.recordings[0]
    assert recording.display_name == "unusual recording name"
    assert recording.ros_health is RosHealth.READABLE
    assert recording.topic_count == 1
    assert recording.message_count == 42
    assert recording.total_source_size_bytes is not None
    assert [component.role for component in recording.components] == list(SourceRole)
    for component in recording.components:
        assert component.relative_path is not None
        source_path = archive / component.relative_path
        details = source_path.stat(follow_symlinks=False)
        assert component.size_bytes == details.st_size
        assert component.mtime_ns == details.st_mtime_ns
    assert first.recordings[0].source_revision == second.recordings[0].source_revision
    assert inventory(archive) == before


def test_isolates_damaged_database_and_preserves_companions(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    create_recording(archive, "damaged", damaged=True)

    snapshot = CatalogScanner(archive).scan()

    by_name = {recording.display_name: recording for recording in snapshot.recordings}
    assert by_name["healthy"].ros_health is RosHealth.READABLE
    damaged = by_name["damaged"]
    assert damaged.ros_health is RosHealth.DAMAGED
    components = {component.role: component for component in damaged.components}
    assert components[SourceRole.ROS_DATABASE].condition is SourceCondition.DAMAGED
    assert components[SourceRole.TOPDOWN_VIDEO].condition is SourceCondition.PRESENT
    assert components[SourceRole.TOPDOWN_TIMESTAMPS].condition is SourceCondition.PRESENT


def test_catalogues_invalid_metadata_folder_without_aborting_sibling(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    invalid = archive / "invalid"
    invalid.mkdir()
    (invalid / "metadata.yaml").write_text("invalid: true", encoding="utf-8")
    (invalid / "camera.avi").write_bytes(b"placeholder")
    (invalid / "camera.csv").write_text("header\n", encoding="utf-8")

    snapshot = CatalogScanner(archive).scan()

    assert len(snapshot.recordings) == 2
    by_name = {recording.display_name: recording for recording in snapshot.recordings}
    assert by_name["healthy"].ros_health is RosHealth.READABLE
    assert by_name["invalid"].ros_health is RosHealth.UNINSPECTABLE


def test_deep_yaml_keeps_companions_visible_and_does_not_abort_sibling(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    nested = "value"
    for _ in range(80):
        nested = f"[{nested}]"
    invalid = archive / "deep-yaml"
    invalid.mkdir()
    (invalid / "metadata.yaml").write_text(f"root: {nested}\n", encoding="utf-8")
    (invalid / "camera.avi").write_bytes(b"placeholder")
    (invalid / "camera.csv").write_text("header\n", encoding="utf-8")

    snapshot = CatalogScanner(archive).scan()

    by_name = {recording.display_name: recording for recording in snapshot.recordings}
    assert by_name["healthy"].ros_health is RosHealth.READABLE
    components = {item.role: item for item in by_name["deep-yaml"].components}
    assert components[SourceRole.METADATA].condition is SourceCondition.INVALID
    assert components[SourceRole.TOPDOWN_VIDEO].condition is SourceCondition.PRESENT
    assert components[SourceRole.TOPDOWN_TIMESTAMPS].condition is SourceCondition.PRESENT


def test_metadata_replacement_after_inventory_is_rejected_without_hiding_companions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording_root = create_recording(archive, "changing")
    original_parse = catalog_scanner.parse_metadata_file

    def replace_before_parse(path: Path, *, expected_identity=None):
        replacement = path.with_name("replacement-metadata.yaml")
        document = metadata_document("changing_0.db3")
        document["rosbag2_bagfile_information"]["message_count"] = 99
        replacement.write_text(yaml.safe_dump(document), encoding="utf-8")
        replacement.replace(path)
        return original_parse(path, expected_identity=expected_identity)

    monkeypatch.setattr(catalog_scanner, "parse_metadata_file", replace_before_parse)

    result = CatalogScanner(archive).scan().recordings[0]

    assert result.message_count is None
    components = {item.role: item for item in result.components}
    assert components[SourceRole.METADATA].condition is SourceCondition.INVALID
    assert components[SourceRole.METADATA].diagnostic is not None
    assert (
        components[SourceRole.METADATA].diagnostic.code
        == "metadata_changed_during_scan"
    )
    assert components[SourceRole.TOPDOWN_VIDEO].condition is SourceCondition.PRESENT
    assert components[SourceRole.TOPDOWN_TIMESTAMPS].condition is SourceCondition.PRESENT
    assert (recording_root / "changing.avi").is_file()


def test_missing_companion_keeps_known_source_size(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "missing-video", include_video=False)

    recording = CatalogScanner(archive).scan().recordings[0]

    assert recording.ros_health is RosHealth.READABLE
    known_size = sum(
        component.size_bytes or 0
        for component in recording.components
        if component.size_bytes is not None
    )
    assert recording.total_source_size_bytes == known_size
    video = next(
        item for item in recording.components if item.role is SourceRole.TOPDOWN_VIDEO
    )
    assert video.condition is SourceCondition.MISSING


def test_rejects_escaped_database_path_but_keeps_recording(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording = archive / "escaped"
    recording.mkdir()
    document = metadata_document(relative_file_paths=["../outside.db3"])
    (recording / "metadata.yaml").write_text(
        yaml.safe_dump(document), encoding="utf-8"
    )
    (recording / "camera.avi").write_bytes(b"placeholder")
    (recording / "camera.csv").write_text("header\n", encoding="utf-8")

    result = CatalogScanner(archive).scan().recordings[0]

    assert result.ros_health is RosHealth.UNINSPECTABLE
    database = next(
        item for item in result.components if item.role is SourceRole.ROS_DATABASE
    )
    assert database.diagnostic.code == "unsafe_source_path"


def test_unrelated_metadata_change_changes_revision(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording_root = create_recording(archive, "revision")
    scanner = CatalogScanner(archive)
    first = scanner.scan().recordings[0].source_revision

    metadata_path = recording_root / "metadata.yaml"
    document = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    document["rosbag2_bagfile_information"]["message_count"] = 43
    metadata_path.write_text(yaml.safe_dump(document), encoding="utf-8")
    second = scanner.scan().recordings[0].source_revision

    assert first != second


@pytest.mark.parametrize("suffix", [".db3", ".avi", ".csv"])
def test_each_non_metadata_source_change_changes_revision(
    tmp_path: Path, suffix: str
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording_root = create_recording(archive, "revision-input")
    scanner = CatalogScanner(archive)
    first = scanner.scan().recordings[0].source_revision
    source_path = next(recording_root.glob(f"*{suffix}"))

    source_path.write_bytes(source_path.read_bytes() + b"changed")
    second = scanner.scan().recordings[0].source_revision

    assert first != second


def test_out_of_range_metadata_is_isolated_from_healthy_sibling(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    create_recording(
        archive,
        "out-of-range",
        metadata_overrides={
            "starting_time": {"nanoseconds_since_epoch": 2**63},
        },
    )

    snapshot = CatalogScanner(archive).scan()
    by_name = {recording.display_name: recording for recording in snapshot.recordings}

    assert by_name["healthy"].ros_health is RosHealth.READABLE
    assert by_name["out-of-range"].ros_health is RosHealth.UNINSPECTABLE
    assert by_name["out-of-range"].start_time_ns is None


def test_nul_metadata_is_isolated_from_healthy_sibling(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    create_recording(
        archive,
        "nul-storage",
        metadata_overrides={"storage_identifier": "sqlite3\x00"},
    )

    snapshot = CatalogScanner(archive).scan()
    by_name = {recording.display_name: recording for recording in snapshot.recordings}

    assert by_name["healthy"].ros_health is RosHealth.READABLE
    assert by_name["nul-storage"].ros_health is RosHealth.UNINSPECTABLE
    assert by_name["nul-storage"].storage_format is None


def test_out_of_range_filesystem_fact_is_isolated_from_healthy_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "healthy")
    create_recording(archive, "future-mtime")
    original_inventory = catalog_paths._direct_entries

    def inventory_with_future_mtime(raw_entries):
        entries = original_inventory(raw_entries)
        if not entries or Path(entries[0].path).parent.name != "future-mtime":
            return entries
        return tuple(
            replace(entry, mtime_ns=POSTGRES_BIGINT_MAX + 1)
            if entry.name.endswith(".avi")
            else entry
            for entry in entries
        )

    monkeypatch.setattr(
        catalog_paths, "_direct_entries", inventory_with_future_mtime
    )

    snapshot = CatalogScanner(archive).scan()
    by_name = {recording.display_name: recording for recording in snapshot.recordings}

    assert by_name["healthy"].ros_health is RosHealth.READABLE
    out_of_range = by_name["future-mtime"]
    assert out_of_range.ros_health is RosHealth.UNINSPECTABLE
    assert out_of_range.diagnostic is not None
    assert out_of_range.diagnostic.code == "source_fact_out_of_range"
    assert all(component.mtime_ns is None for component in out_of_range.components)


def test_non_utf8_recording_name_is_catalogued_without_identity_collision(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    os.mkdir(os.fsencode(archive) + b"/bad_\xff")
    (archive / "bad_%FF").mkdir()
    with open(os.fsencode(archive) + b"/bad_\xff/source.db3", "wb") as source:
        source.write(b"not sqlite")
    (archive / "bad_%FF" / "source.db3").write_bytes(b"not sqlite")

    snapshot = CatalogScanner(archive).scan()

    assert {item.archive_relative_path for item in snapshot.recordings} == {
        "bad_%FF",
        "bad_%25FF",
    }
    assert all(item.ros_health is RosHealth.MISSING for item in snapshot.recordings)


def test_ambiguous_companion_names_change_source_revision(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording_root = create_recording(archive, "ambiguous")
    second_video = recording_root / "second.avi"
    second_video.write_bytes(b"synthetic video placeholder")
    scanner = CatalogScanner(archive)

    first = scanner.scan().recordings[0]
    (recording_root / "ambiguous.avi").rename(recording_root / "renamed-one.avi")
    second_video.rename(recording_root / "renamed-two.avi")
    second = scanner.scan().recordings[0]

    assert first.source_revision != second.source_revision
    video = next(
        item for item in second.components if item.role is SourceRole.TOPDOWN_VIDEO
    )
    assert video.condition is SourceCondition.AMBIGUOUS
    assert video.revision_facts


def test_recursive_discovery_returns_physical_paths_and_stops_at_recording_root(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    recording = archive / "year" / "month"
    recording.mkdir(parents=True)
    create_recording(recording, "run")
    nested_fake = recording / "run" / "nested"
    nested_fake.mkdir()
    (nested_fake / "metadata.yaml").write_text("invalid: true", encoding="utf-8")

    snapshot = CatalogScanner(archive).scan()

    assert [item.archive_relative_path for item in snapshot.recordings] == [
        "year/month/run"
    ]
    assert snapshot.recordings[0].display_name == "run"


def test_leaf_with_recognized_companion_and_no_metadata_is_damaged_candidate(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    leaf = archive / "folder" / "missing-metadata"
    leaf.mkdir(parents=True)
    (leaf / "recording.db3").write_bytes(b"not sqlite")

    result = CatalogScanner(archive).scan().recordings[0]

    assert result.archive_relative_path == "folder/missing-metadata"
    assert result.ros_health is RosHealth.MISSING
    metadata = next(
        item for item in result.components if item.role is SourceRole.METADATA
    )
    assert metadata.condition is SourceCondition.MISSING


def test_incomplete_depth_or_global_entry_scan_raises_without_snapshot(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    deep = archive / "one" / "two" / "three"
    deep.mkdir(parents=True)
    create_recording(deep, "run")

    with pytest.raises(RootScanError) as depth_error:
        CatalogScanner(
            archive,
            limits=CatalogScanLimits(max_depth=2),
        ).scan()
    assert depth_error.value.diagnostic.code == "archive_depth_limit_exceeded"

    with pytest.raises(RootScanError) as entry_error:
        CatalogScanner(
            archive,
            limits=CatalogScanLimits(max_entries=2),
        ).scan()
    assert entry_error.value.diagnostic.code == "archive_entry_limit_exceeded"


def test_directory_recording_and_direct_entry_bounds_are_distinct(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "one")
    create_recording(archive, "two")

    with pytest.raises(RootScanError) as recording_error:
        CatalogScanner(
            archive,
            limits=CatalogScanLimits(max_recordings=1),
        ).scan()
    assert recording_error.value.diagnostic.code == "archive_recording_limit_exceeded"

    navigation = tmp_path / "navigation"
    (navigation / "first" / "second").mkdir(parents=True)
    with pytest.raises(RootScanError) as directory_error:
        CatalogScanner(
            navigation,
            limits=CatalogScanLimits(max_directories=2),
        ).scan()
    assert directory_error.value.diagnostic.code == "archive_directory_limit_exceeded"

    crowded = tmp_path / "crowded"
    crowded.mkdir()
    (crowded / "one.txt").write_text("one", encoding="utf-8")
    (crowded / "two.txt").write_text("two", encoding="utf-8")
    with pytest.raises(RootScanError) as direct_error:
        CatalogScanner(
            crowded,
            limits=CatalogScanLimits(max_directory_entries=1),
        ).scan()
    assert (
        direct_error.value.diagnostic.code
        == "archive_directory_entry_limit_exceeded"
    )


def test_recording_direct_entry_bound_is_isolated_to_identified_recording(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    create_recording(archive, "crowded")

    snapshot = CatalogScanner(
        archive,
        limits=CatalogScanLimits(max_recording_entries=2),
    ).scan()

    assert len(snapshot.recordings) == 1
    recording = snapshot.recordings[0]
    assert recording.ros_health is RosHealth.UNINSPECTABLE
    assert recording.diagnostic is not None
    assert recording.diagnostic.code == "recording_entry_limit_exceeded"


def test_inaccessible_navigation_branch_makes_snapshot_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "archive"
    blocked = archive / "blocked"
    blocked.mkdir(parents=True)
    original_scandir = catalog_paths.os.scandir

    def selective_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("synthetic inaccessible branch")
        return original_scandir(path)

    monkeypatch.setattr(catalog_paths.os, "scandir", selective_scandir)

    with pytest.raises(RootScanError) as captured:
        CatalogScanner(archive).scan()

    assert captured.value.diagnostic.code == "archive_enumeration_failed"


def test_symlinked_directory_is_never_followed(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    outside = tmp_path / "outside"
    archive.mkdir()
    outside.mkdir()
    create_recording(outside, "run")
    (archive / "linked").symlink_to(outside / "run", target_is_directory=True)

    snapshot = CatalogScanner(archive).scan()

    assert snapshot.recordings == ()


def test_unsafe_navigation_name_makes_root_snapshot_incomplete(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "unsafe\\name").mkdir()

    with pytest.raises(RootScanError) as captured:
        CatalogScanner(archive).scan()

    assert captured.value.diagnostic.code == "unsafe_source_name"
