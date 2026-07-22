from __future__ import annotations

import pytest

from rosbag_analyser.timeline import (
    GlobalTimeline,
    StreamCoverage,
    media_pts_digest_chunk,
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


def test_csv_coverage_can_extend_outside_the_global_recording() -> None:
    coverage = StreamCoverage(
        start_ns=-100,
        end_ns=600,
        timestamp_provenance="csv_unix_timestamp",
    )
    timeline = GlobalTimeline(500)

    assert coverage.timestamp_provenance == "csv_unix_timestamp"
    assert coverage.bounds == "measured"
    assert coverage.media_time_ns(-100) == 0
    assert coverage.media_time_ns(0) == 100
    assert coverage.media_time_ns(600) == 700
    assert timeline.clamp(600) == 500


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
    with pytest.raises(ValueError):
        media_pts_digest_chunk(-1)


def test_media_pts_digest_chunk_is_fixed_width_and_unambiguous() -> None:
    assert media_pts_digest_chunk(1) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert media_pts_digest_chunk(256) == b"\x00\x00\x00\x00\x00\x00\x01\x00"
