from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import inventory, require_optional_prerequisite
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.catalog.types import RosHealth, SourceRole


@pytest.mark.real_archive
def test_opt_in_real_archive_is_six_five_one_and_unchanged(
    pytestconfig: pytest.Config,
) -> None:
    require_optional_prerequisite(
        pytestconfig,
        option_name="require_real_archive",
        ready=os.environ.get("RUN_REAL_ARCHIVE_TESTS") == "1",
        message="Real-archive checks require RUN_REAL_ARCHIVE_TESTS=1",
    )
    root_value = os.environ.get("ROS_BAG_ANALYSER_ARCHIVE_ROOT")
    if not root_value:
        pytest.fail("ROS_BAG_ANALYSER_ARCHIVE_ROOT must be configured explicitly")
    archive_root = Path(root_value).resolve(strict=True)
    expected_damaged_database = os.environ.get(
        "ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE"
    )
    if not expected_damaged_database:
        pytest.fail(
            "ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE must identify the "
            "acceptance case"
        )
    before = inventory(archive_root)

    try:
        snapshot = CatalogScanner(archive_root).scan()
    finally:
        assert inventory(archive_root) == before

    assert len(snapshot.recordings) == 6
    assert (
        sum(item.ros_health is RosHealth.READABLE for item in snapshot.recordings)
        == 5
    )
    assert (
        sum(item.ros_health is RosHealth.DAMAGED for item in snapshot.recordings)
        == 1
    )
    damaged = next(
        item for item in snapshot.recordings if item.ros_health is RosHealth.DAMAGED
    )
    database = next(
        component
        for component in damaged.components
        if component.role is SourceRole.ROS_DATABASE
    )
    assert database.display_name == expected_damaged_database
    assert database.diagnostic is not None
    assert database.diagnostic.code == "sqlite_size_mismatch"
