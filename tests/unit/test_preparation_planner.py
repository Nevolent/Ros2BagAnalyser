from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from conftest import create_recording, metadata_document
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.preparation_planner import (
    PREPARATION_KINDS,
    PreparationPlanner,
)


FRONT_TOPIC = "/camera/image_raw"
IMU_TOPIC = "/imu/raw"


def _planner(*, imu_topic: str = IMU_TOPIC, encoder: str = "encoder-v1"):
    return PreparationPlanner(
        front_topic=FRONT_TOPIC,
        imu_topic=imu_topic,
        imu_component="angular_velocity.z",
        profile=V0_PREVIEW_PROFILE,
        encoder_identity=encoder,
    )


def _scanned_recording(tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    document = metadata_document("run_0.db3")
    document["rosbag2_bagfile_information"]["topics_with_message_count"].append(
        {
            "topic_metadata": {
                "name": IMU_TOPIC,
                "type": "sensor_msgs/msg/Imu",
                "serialization_format": "cdr",
                "offered_qos_profiles": "",
            },
            "message_count": 25,
        }
    )
    create_recording(
        archive,
        "run",
        metadata_overrides=document["rosbag2_bagfile_information"],
    )
    return CatalogScanner(archive).scan().recordings[0]


def test_plans_all_three_available_targets_from_one_scan(tmp_path: Path) -> None:
    recording = _scanned_recording(tmp_path)

    targets = _planner().plan_recording(11, recording)

    assert tuple(target.kind for target in targets) == PREPARATION_KINDS
    assert all(target.target_state == "available" for target in targets)
    assert all(target.cache_identity is not None for target in targets)
    assert all(target.work_units is not None and target.work_units > 0 for target in targets)
    assert all(target.diagnostic is None for target in targets)


def test_missing_configured_topic_is_unavailable_without_hiding_other_targets(
    tmp_path: Path,
) -> None:
    recording = _scanned_recording(tmp_path)

    targets = _planner(imu_topic="/missing/imu").plan_recording(11, recording)
    by_kind = {target.kind: target for target in targets}

    assert by_kind["front_preview"].target_state == "available"
    assert by_kind["topdown_preview"].target_state == "available"
    assert by_kind["imu_series"].target_state == "unavailable"
    assert by_kind["imu_series"].diagnostic is not None
    assert by_kind["imu_series"].diagnostic.code == "imu_topic_unavailable"


def test_planner_and_cache_identity_change_only_for_relevant_configuration(
    tmp_path: Path,
) -> None:
    recording = _scanned_recording(tmp_path)
    first = _planner(encoder="encoder-v1")
    second = _planner(encoder="encoder-v2")

    first_targets = {item.kind: item for item in first.plan_recording(11, recording)}
    second_targets = {item.kind: item for item in second.plan_recording(11, recording)}

    assert first.planner_identity("front_preview") != second.planner_identity(
        "front_preview"
    )
    assert first.planner_identity("topdown_preview") != second.planner_identity(
        "topdown_preview"
    )
    assert first.planner_identity("imu_series") == second.planner_identity(
        "imu_series"
    )
    assert (
        first_targets["front_preview"].cache_identity
        != second_targets["front_preview"].cache_identity
    )
    assert (
        first_targets["topdown_preview"].cache_identity
        != second_targets["topdown_preview"].cache_identity
    )
    assert (
        first_targets["imu_series"].cache_identity
        == second_targets["imu_series"].cache_identity
    )


def test_recording_id_remains_part_of_existing_cache_contract(tmp_path: Path) -> None:
    recording = _scanned_recording(tmp_path)

    first = _planner().plan_recording(11, recording)
    second = _planner().plan_recording(12, recording)

    assert [item.cache_identity for item in first] != [
        item.cache_identity for item in second
    ]


def test_private_cache_anchors_preserve_identity_across_a_path_move(
    tmp_path: Path,
) -> None:
    recording = _scanned_recording(tmp_path)
    planner = _planner()
    original = planner.plan_recording(11, recording)
    moved_path = "site/day/run"
    moved = replace(
        recording,
        archive_relative_path=moved_path,
        components=tuple(
            replace(
                component,
                relative_path=(
                    None
                    if component.relative_path is None
                    else f"{moved_path}/{component.display_name}"
                ),
            )
            for component in recording.components
        ),
    )

    after_move = planner.plan_recording(
        99,
        moved,
        cache_identity_recording_id=11,
        cache_identity_relative_path=recording.archive_relative_path,
    )

    assert [item.cache_identity for item in after_move] == [
        item.cache_identity for item in original
    ]
