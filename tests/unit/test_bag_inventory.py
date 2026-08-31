from __future__ import annotations

import json
from pathlib import Path

import pytest

from rosbag_analyser.bag_inventory import (
    InventoryError,
    build_bag_inventory,
    write_bag_inventory,
)


def _metadata(*, storage: str = "sqlite3") -> str:
    return f"""rosbag2_bagfile_information:
  version: 5
  storage_identifier: {storage}
  relative_file_paths:
    - run_0.db3
  duration:
    nanoseconds: 4500000000
  starting_time:
    nanoseconds_since_epoch: 1700000000000000000
  message_count: 17
  topics_with_message_count:
    - topic_metadata:
        name: /robot/front/image_raw
        type: sensor_msgs/msg/Image
        serialization_format: cdr
      message_count: 12
    - topic_metadata:
        name: /robot/imu
        type: sensor_msgs/msg/Imu
        serialization_format: cdr
      message_count: 5
"""


def test_inventory_reads_metadata_and_never_follows_storage_symlink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    recording = source / "day" / "run"
    recording.mkdir(parents=True)
    (recording / "metadata.yaml").write_text(_metadata(), encoding="utf-8")
    (recording / "run_0.db3").write_bytes(b"not opened as sqlite")
    (recording / "top.avi").write_bytes(b"not decoded")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.mcap").write_bytes(b"not inventoried")
    (source / "outside-link").symlink_to(outside, target_is_directory=True)

    inventory = build_bag_inventory(source, max_depth=8, max_entries=100)

    assert inventory["inspection"] == {
        "source_root_included": False,
        "path_base": "source_root",
        "complete": True,
        "bounds": {"max_depth": 8, "max_entries": 100},
        "source_operations": [
            "directory enumeration",
            "lstat-style entry metadata",
            "bounded metadata.yaml reads",
        ],
        "bag_payload_files_opened": False,
        "symlinks_followed": False,
    }
    assert inventory["issues"] == []
    recordings = inventory["recordings"]
    assert isinstance(recordings, list)
    assert len(recordings) == 1
    bag = recordings[0]
    assert bag["path"] == "day/run"
    assert bag["size_bytes"] == len(_metadata().encode()) + len(b"not opened as sqlite") + len(b"not decoded")
    assert [entry["path"] for entry in bag["files"]] == [
        "metadata.yaml",
        "run_0.db3",
        "top.avi",
    ]
    metadata = bag["metadata"]
    assert metadata["storage_identifier"] == "sqlite3"
    assert metadata["start_time_ns"] == "1700000000000000000"
    assert metadata["duration_ns"] == "4500000000"
    assert metadata["message_count"] == "17"
    assert metadata["topics"] == [
        {
            "name": "/robot/front/image_raw",
            "type": "sensor_msgs/msg/Image",
            "serialization_format": "cdr",
            "message_count": "12",
        },
        {
            "name": "/robot/imu",
            "type": "sensor_msgs/msg/Imu",
            "serialization_format": "cdr",
            "message_count": "5",
        },
    ]
    assert "hidden.mcap" not in json.dumps(inventory)


def test_inventory_reports_malformed_metadata_and_storage_without_metadata(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    damaged = source / "damaged"
    damaged.mkdir(parents=True)
    (damaged / "metadata.yaml").write_text("not: [valid", encoding="utf-8")
    orphan = source / "legacy"
    orphan.mkdir()
    (orphan / "legacy_0.mcap").write_bytes(b"not opened")

    inventory = build_bag_inventory(source, max_depth=8, max_entries=100)

    assert inventory["summary"] == {
        "recording_count": 2,
        "metadata_bag_count": 1,
        "metadata_missing_candidate_count": 1,
        "metadata_or_read_error_count": 2,
        "source_file_count": 2,
    }
    bags = {bag["path"]: bag for bag in inventory["recordings"]}
    assert bags["damaged"]["metadata"] == {
        "status": "error",
        "error": {
            "code": "metadata_yaml_invalid",
            "message": "metadata.yaml is not valid YAML.",
        },
    }
    assert bags["legacy"]["candidate_kind"] == "metadata_missing_storage_candidate"
    assert bags["legacy"]["metadata"]["error"]["code"] == "metadata_missing"


def test_inventory_marks_a_bounded_traversal_incomplete(tmp_path: Path) -> None:
    source = tmp_path / "source"
    nested = source / "one" / "two"
    nested.mkdir(parents=True)
    (nested / "recording.mcap").write_bytes(b"not opened")

    inventory = build_bag_inventory(source, max_depth=1, max_entries=100)

    assert inventory["inspection"]["complete"] is False
    assert inventory["issues"] == [{"code": "depth_limit_exceeded", "path": "one"}]


def test_inventory_evidence_is_atomic_relative_and_outside_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    recording = source / "run"
    recording.mkdir()
    (recording / "metadata.yaml").write_text(_metadata(), encoding="utf-8")
    (recording / "run_0.db3").write_bytes(b"not opened")
    output = tmp_path / "evidence" / "bags.json"

    inventory = write_bag_inventory(source, output, max_depth=8, max_entries=100)

    assert output.exists()
    assert output.stat().st_mode & 0o777 == 0o600
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["summary"] == inventory["summary"]
    assert str(source) not in output.read_text(encoding="utf-8")
    with pytest.raises(InventoryError, match="already exists"):
        write_bag_inventory(source, output, max_depth=8, max_entries=100)
    with pytest.raises(InventoryError, match="outside source"):
        write_bag_inventory(source, source / "forbidden.json", max_depth=8, max_entries=100)
