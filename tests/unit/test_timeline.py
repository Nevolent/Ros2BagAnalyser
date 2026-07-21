from __future__ import annotations

import pytest

from rosbag_analyser.timeline import (
    GlobalTimeline,
    StreamCoverage,
    nanoseconds_to_media_pts,
    record_time_to_bag_time_ns,
)


def test_record_and_media_time_mapping_preserves_integer_precision() -> None:
    bag_start = 1_700_000_000_000_000_000

    assert record_time_to_bag_time_ns(bag_start - 10, bag_start) == -10
    assert record_time_to_bag_time_ns(bag_start + 123_456_789, bag_start) == 123_456_789
    assert nanoseconds_to_media_pts(123_456_789, 1_000_000) == 123_457


def test_coverage_maps_only_measured_global_time() -> None:
    coverage = StreamCoverage(start_ns=100, end_ns=400)

    assert coverage.media_time_ns(99) is None
    assert coverage.media_time_ns(100) == 0
    assert coverage.media_time_ns(250) == 150
    assert coverage.media_time_ns(400) == 300
    assert coverage.media_time_ns(401) is None


def test_global_timeline_clamps_to_bag_duration() -> None:
    timeline = GlobalTimeline(500)

    assert timeline.clamp(-1) == 0
    assert timeline.clamp(200) == 200
    assert timeline.clamp(501) == 500


def test_invalid_timeline_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        StreamCoverage(10, 9)
    with pytest.raises(ValueError):
        GlobalTimeline(-1)
    with pytest.raises(ValueError):
        nanoseconds_to_media_pts(-1, 1_000_000)
