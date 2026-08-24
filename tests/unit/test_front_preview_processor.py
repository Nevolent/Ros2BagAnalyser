from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import weakref

import pytest

from conftest import inventory
from rosbag_analyser.artifact_store import ArtifactStore
from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.front_preview import FrontSourceDescriptor
from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.processors.front_preview import (
    DecodedImage,
    FrontPreviewProcessingError,
    FrontPreviewProcessor,
)
from rosbag_analyser.processors import front_preview as front_preview_module


def _create_image_database(path: Path, timestamps: list[int]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE topics (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                serialization_format TEXT NOT NULL,
                offered_qos_profiles TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                topic_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                data BLOB NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO topics VALUES (1, '/camera/image_raw', 'sensor_msgs/msg/Image', 'cdr', '')"
        )
        for index, timestamp in enumerate(timestamps, start=1):
            connection.execute(
                "INSERT INTO messages VALUES (?, 1, ?, ?)",
                (index, timestamp, bytes([index])),
            )
        connection.commit()
    finally:
        connection.close()


def _descriptor(database: Path, bag_start: int, message_count: int) -> FrontSourceDescriptor:
    details = database.stat()
    return FrontSourceDescriptor(
        recording_id=1,
        archive_relative_path="run",
        metadata_path=database.parent / "metadata.yaml",
        database_path=database,
        metadata_identity=source_file_identity(details),
        database_identity=source_file_identity(details),
        bag_start_ns=bag_start,
        bag_duration_ns=1_000_000_000,
        topic=TopicFact(
            name="/camera/image_raw",
            message_type="sensor_msgs/msg/Image",
            serialization_format="cdr",
            message_count=message_count,
        ),
        cache_identity="a" * 64,
    )


def _decoder(serialized: bytes) -> DecodedImage:
    value = serialized[0]
    return DecodedImage(
        width=4,
        height=2,
        encoding="bgr8",
        step=14,
        data=bytes([value, 0, 255] * 4 + [0, 0]) * 2,
        header_timestamp_ns=2_000_000_000 + value * 100_000_000,
    )


class _CancelAtFirstCheckpoint:
    phases: list[str]

    def __init__(self) -> None:
        self.phases = []

    def checkpoint(self, phase: str, *, force: bool = False) -> None:
        del force
        self.phases.append(phase)
        raise JobCanceled("synthetic cancellation")


def test_front_control_reaches_a_bounded_processing_checkpoint(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [100, 200])
    control = _CancelAtFirstCheckpoint()
    started = time.perf_counter()

    with pytest.raises(JobCanceled):
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
            _descriptor(database, 0, 2),
            tmp_path / "preview.mp4",
            control=control,  # type: ignore[arg-type]
        )

    assert time.perf_counter() - started < 2
    assert control.phases == ["processing"]
    assert not (tmp_path / "preview.mp4").exists()


def _probe_frames(path: Path) -> list[dict[str, str]]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time,pict_type",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)["frames"]


def test_irregular_record_times_use_smooth_header_cadence_and_leave_source_unchanged(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    database = archive / "recording.db3"
    bag_start = 1_700_000_000_000_000_000
    timestamps = [bag_start + 100_000_000, bag_start + 140_000_000, bag_start + 400_000_000]
    _create_image_database(database, timestamps)
    before = inventory(archive)

    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
        _descriptor(database, bag_start, len(timestamps)),
        derived / "preview.mp4",
    )

    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 400_000_000
    assert result.measured_span_ns == 300_000_000
    assert result.input_frame_count == 3
    assert result.encoded_frame_count == 3
    assert result.header_span_ns == 200_000_000
    assert result.maximum_presentation_gap_ns == 150_000_000
    assert len(result.media_pts_sha256) == 64
    assert (derived / "preview.mp4").stat().st_size > 0
    frames = _probe_frames(derived / "preview.mp4")
    assert [float(frame["best_effort_timestamp_time"]) for frame in frames] == pytest.approx(
        [0.0, 0.15, 0.3], abs=0.000_001
    )
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None
    validation = ArtifactStore(
        derived,
        Path(ffmpeg),
        Path(ffprobe),
    ).validate_preview(
        derived / "preview.mp4",
        V0_PREVIEW_PROFILE,
        expected_width=result.output_width,
        expected_height=result.output_height,
        expected_frame_count=result.encoded_frame_count,
        measured_span_ns=result.measured_span_ns,
        expected_media_pts_sha256=result.media_pts_sha256,
    )
    assert validation.frame_count == 3
    assert inventory(archive) == before
    assert not (archive / "recording.db3-journal").exists()
    assert not (archive / "recording.db3-wal").exists()
    assert not (archive / "recording.db3-shm").exists()


def test_duplicate_record_time_keeps_one_encoded_frame(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    bag_start = 1_700_000_000_000_000_000
    _create_image_database(
        database,
        [bag_start + 100_000_000, bag_start + 100_000_000, bag_start + 200_000_000],
    )

    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
        _descriptor(database, bag_start, 3),
        tmp_path / "preview.mp4",
    )

    assert result.input_frame_count == 3
    assert result.encoded_frame_count == 2
    assert result.duplicate_timestamp_count == 1


def test_preview_forces_seek_keyframes_at_the_profile_interval(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    bag_start = 1_700_000_000_000_000_000
    timestamps = [
        bag_start,
        bag_start + 1_000_000_000,
        bag_start + 2_100_000_000,
        bag_start + 2_200_000_000,
    ]
    _create_image_database(database, timestamps)
    output = tmp_path / "preview.mp4"

    FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
        _descriptor(database, bag_start, len(timestamps)),
        output,
    )

    keyframe_times = [
        float(frame["best_effort_timestamp_time"])
        for frame in _probe_frames(output)
        if frame["pict_type"] == "I"
    ]
    assert keyframe_times == pytest.approx([0.0, 2.2], abs=0.000_001)


def test_dimension_change_fails_before_publication(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [100, 200])

    def changing_decoder(serialized: bytes) -> DecodedImage:
        width = 4 if serialized == b"\x01" else 6
        return DecodedImage(
            width=width,
            height=2,
            encoding="bgr8",
            step=width * 3,
            data=b"x" * width * 3 * 2,
            header_timestamp_ns=1_000_000_000 + serialized[0] * 100_000_000,
        )

    with pytest.raises(FrontPreviewProcessingError) as captured:
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, changing_decoder).process(
            _descriptor(database, 0, 2),
            tmp_path / "preview.mp4",
        )

    assert captured.value.code == "front_image_dimensions_changed"


def test_decoded_frames_are_streamed_instead_of_accumulated(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    timestamps = list(range(1_000_000_000, 2_000_000_000, 5_000_000))
    _create_image_database(database, timestamps)
    live_images: list[weakref.ReferenceType[DecodedImage]] = []
    maximum_live = 0

    def tracking_decoder(serialized: bytes) -> DecodedImage:
        nonlocal maximum_live
        image = _decoder(serialized)
        live_images.append(weakref.ref(image))
        maximum_live = max(
            maximum_live,
            sum(reference() is not None for reference in live_images),
        )
        return image

    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE, tracking_decoder).process(
        _descriptor(database, 1_000_000_000, len(timestamps)),
        tmp_path / "preview.mp4",
    )

    assert result.encoded_frame_count == len(timestamps)
    assert maximum_live <= 2


def test_non_monotonic_header_timestamps_fail_instead_of_publishing(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(
        database,
        [100_000_000, 200_000_000, 300_000_000, 400_000_000],
    )
    headers = {
        1: 1_000_000_000,
        2: 1_300_000_000,
        3: 1_200_000_000,
        4: 1_400_000_000,
    }

    def decoder(serialized: bytes) -> DecodedImage:
        image = _decoder(serialized)
        return DecodedImage(
            **{**image.__dict__, "header_timestamp_ns": headers[serialized[0]]}
        )

    with pytest.raises(FrontPreviewProcessingError) as captured:
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, decoder).process(
            _descriptor(database, 0, 4), tmp_path / "preview.mp4"
        )

    assert captured.value.code == "front_header_timestamps_invalid"


def test_missing_header_timestamp_fails_before_publication(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [100, 200])

    def decoder(serialized: bytes) -> DecodedImage:
        image = _decoder(serialized)
        return DecodedImage(**{**image.__dict__, "header_timestamp_ns": None})

    with pytest.raises(FrontPreviewProcessingError) as captured:
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, decoder).process(
            _descriptor(database, 0, 2), tmp_path / "preview.mp4"
        )

    assert captured.value.code == "front_header_timestamp_invalid"


def test_media_timescale_collision_fails_instead_of_reordering_frames(
    tmp_path: Path,
) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [1_000_000_000, 1_000_000_500, 1_000_001_000])

    with pytest.raises(FrontPreviewProcessingError) as captured:
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
            _descriptor(database, 0, 3), tmp_path / "preview.mp4"
        )

    assert captured.value.code == "front_presentation_timestamps_invalid"


def test_single_frame_header_timing_maps_to_zero(tmp_path: Path) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [1_100_000_000])

    result = FrontPreviewProcessor(V0_PREVIEW_PROFILE, _decoder).process(
        _descriptor(database, 1_000_000_000, 1), tmp_path / "preview.mp4"
    )

    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 100_000_000
    assert result.measured_span_ns == 0
    assert result.header_span_ns == 0
    assert result.maximum_presentation_gap_ns == 0


def test_oversized_serialized_frame_is_rejected_before_deserialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [100])
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE messages SET data = ?", (b"x" * 10,))
    monkeypatch.setattr(front_preview_module, "MAX_SERIALIZED_IMAGE_BYTES", 4)
    decoder_called = False

    def decoder(serialized: bytes) -> DecodedImage:
        nonlocal decoder_called
        del serialized
        decoder_called = True
        return _decoder(b"\x01")

    with pytest.raises(FrontPreviewProcessingError) as captured:
        FrontPreviewProcessor(V0_PREVIEW_PROFILE, decoder).process(
            _descriptor(database, 0, 1), tmp_path / "preview.mp4"
        )

    assert captured.value.code == "front_serialized_payload_invalid"
    assert not decoder_called


@pytest.mark.parametrize(
    ("image", "code"),
    [
        (DecodedImage(4, 2, "rgb8", 12, b"x" * 24), "front_encoding_unsupported"),
        (DecodedImage(0, 2, "bgr8", 12, b"x" * 24), "front_dimensions_invalid"),
        (DecodedImage(4, 2, "bgr8", 11, b"x" * 22), "front_step_invalid"),
        (DecodedImage(4, 2, "bgr8", 12, b"x" * 23), "front_payload_invalid"),
    ],
)
def test_malformed_images_fail_safely(
    tmp_path: Path, image: DecodedImage, code: str
) -> None:
    database = tmp_path / "recording.db3"
    _create_image_database(database, [100])
    processor = FrontPreviewProcessor(V0_PREVIEW_PROFILE, lambda serialized: image)

    with pytest.raises(FrontPreviewProcessingError) as captured:
        processor.process(_descriptor(database, 0, 1), tmp_path / "preview.mp4")

    assert captured.value.code == code
