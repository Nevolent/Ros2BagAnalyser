from __future__ import annotations

from fractions import Fraction
import hashlib
from pathlib import Path
import shutil
import time

import av
import numpy as np
import pytest

import rosbag_analyser.processors.topdown_preview as topdown_processor_module
from rosbag_analyser.catalog.paths import source_file_identity
from rosbag_analyser.artifact_store import ArtifactStore
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.processors.topdown_preview import (
    TopdownPreviewProcessingError,
    TopdownPreviewProcessor,
    parse_unix_timestamp_ns,
)
from rosbag_analyser.topdown_preview import TopdownSourceDescriptor
from rosbag_analyser.timeline import media_pts_digest_chunk


BAG_START_NS = 1_700_000_000_000_000_000


def _media_pts_sha256(values: tuple[int, ...]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(media_pts_digest_chunk(value))
    return digest.hexdigest()


def _write_avi(path: Path, frame_count: int = 3) -> None:
    container = av.open(path, "w", format="avi")
    stream = container.add_stream("mpeg4", rate=30)
    stream.width = 8
    stream.height = 6
    stream.pix_fmt = "yuv420p"
    for index in range(frame_count):
        pixels = np.full((6, 8, 3), index * 60, dtype=np.uint8)
        frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
        frame.pts = index
        frame.time_base = Fraction(1, 30)
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _write_csv(path: Path, timestamps: list[str]) -> None:
    path.write_text(
        "unix_timestamp,human_timestamp\n"
        + "".join(f"{timestamp},ignored\n" for timestamp in timestamps),
        encoding="utf-8",
    )


def _descriptor(root: Path) -> TopdownSourceDescriptor:
    video = root / "camera.avi"
    timestamps = root / "camera.csv"
    metadata = root / "metadata.yaml"
    metadata.write_text("synthetic", encoding="utf-8")
    return TopdownSourceDescriptor(
        recording_id=7,
        archive_relative_path="run",
        metadata_path=metadata,
        video_path=video,
        timestamps_path=timestamps,
        metadata_identity=source_file_identity(metadata.stat()),
        video_identity=source_file_identity(video.stat()),
        timestamps_identity=source_file_identity(timestamps.stat()),
        bag_start_ns=BAG_START_NS,
        bag_duration_ns=2_000_000_000,
        cache_identity="a" * 64,
    )


def _inventory(root: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (path.name, path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.iterdir())
        if path.is_file()
    )


class _CancelAtFirstCheckpoint:
    phases: list[str]

    def __init__(self) -> None:
        self.phases = []

    def checkpoint(self, phase: str, *, force: bool = False) -> None:
        del force
        self.phases.append(phase)
        raise JobCanceled("synthetic cancellation")


def test_topdown_control_reaches_a_bounded_processing_checkpoint(
    tmp_path: Path,
) -> None:
    _write_avi(tmp_path / "camera.avi", frame_count=1)
    _write_csv(tmp_path / "camera.csv", ["1700000000.1"])
    control = _CancelAtFirstCheckpoint()
    started = time.perf_counter()

    with pytest.raises(JobCanceled):
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            _descriptor(tmp_path),
            tmp_path / "preview.mp4",
            control=control,  # type: ignore[arg-type]
        )

    assert time.perf_counter() - started < 2
    assert control.phases == ["processing"]


def test_exact_unix_timestamp_parsing_never_uses_float() -> None:
    assert parse_unix_timestamp_ns("1700000000.123456789") == 1_700_000_000_123_456_789
    assert parse_unix_timestamp_ns("-1.000000001") == -1_000_000_001
    assert parse_unix_timestamp_ns("+2") == 2_000_000_000


@pytest.mark.parametrize(
    "value",
    [None, "", "nan", "inf", "1e3", "1.1234567890", "1.", ".5"],
)
def test_invalid_unix_timestamps_fail_safely(value: str | None) -> None:
    with pytest.raises(TopdownPreviewProcessingError) as captured:
        parse_unix_timestamp_ns(value)
    assert captured.value.code == "topdown_timestamp_invalid"


def test_processor_uses_csv_timing_and_preserves_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    derived = tmp_path / "derived"
    source.mkdir()
    derived.mkdir()
    _write_avi(source / "camera.avi")
    _write_csv(
        source / "camera.csv",
        ["1700000000.100000000", "1700000000.350000000", "1700000001.000000000"],
    )
    descriptor = _descriptor(source)
    before = _inventory(source)
    output = derived / "preview.mp4"

    result = TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(descriptor, output)

    assert result.input_frame_count == 3
    assert result.timestamp_count == 3
    assert result.encoded_frame_count == 3
    assert result.coverage_start_ns == 100_000_000
    assert result.coverage_end_ns == 1_000_000_000
    assert result.measured_span_ns == 900_000_000
    assert result.media_pts_sha256 == _media_pts_sha256((0, 250_000, 900_000))
    assert result.warnings == (
        "coverage_starts_after_recording",
        "coverage_ends_before_recording",
    )
    with av.open(output) as container:
        frames = list(container.decode(video=0))
    assert len(frames) == 3
    times = [float(frame.pts * frame.time_base) for frame in frames]
    assert times == pytest.approx([0.0, 0.25, 0.9], abs=0.000002)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None
    validation = ArtifactStore(
        derived,
        Path(ffmpeg),
        Path(ffprobe),
        "topdown_preview",
    ).validate_preview(
        output,
        V0_PREVIEW_PROFILE,
        expected_width=result.output_width,
        expected_height=result.output_height,
        expected_frame_count=result.encoded_frame_count,
        measured_span_ns=result.measured_span_ns,
        expected_media_pts_sha256=result.media_pts_sha256,
    )
    assert validation.frame_count == 3
    assert _inventory(source) == before


def test_declared_oversized_video_is_rejected_before_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    derived = tmp_path / "derived"
    source.mkdir()
    derived.mkdir()
    (source / "camera.avi").write_bytes(b"synthetic-video")
    _write_csv(source / "camera.csv", ["1700000000.1"])
    descriptor = _descriptor(source)

    class FakeCodecContext:
        width = topdown_processor_module.MAX_VIDEO_WIDTH + 1
        height = 2
        options: dict[str, str] = {}

    class FakeStream:
        codec_context = FakeCodecContext()

    class FakeStreams:
        video = (FakeStream(),)

    class FakeContainer:
        streams = FakeStreams()
        decode_called = False

        def decode(self, stream: object):
            del stream
            self.decode_called = True
            raise AssertionError("Oversized video must be rejected before decode.")

        def close(self) -> None:
            pass

    fake_container = FakeContainer()
    monkeypatch.setattr(
        topdown_processor_module.av,
        "open",
        lambda *args, **kwargs: fake_container,
    )

    with pytest.raises(TopdownPreviewProcessingError) as captured:
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            descriptor, derived / "preview.mp4"
        )

    assert captured.value.code == "topdown_dimensions_invalid"
    assert not fake_container.decode_called


@pytest.mark.parametrize(
    ("timestamps", "expected_code"),
    [
        (
            ["1700000000.1", "1700000000.1", "1700000000.3"],
            "topdown_timestamp_duplicate",
        ),
        (
            ["1700000000.2", "1700000000.1", "1700000000.3"],
            "topdown_timestamps_unordered",
        ),
        (
            [
                "1700000000.000000001",
                "1700000000.000000002",
                "1700000000.000001000",
            ],
            "topdown_media_timestamp_collision",
        ),
    ],
)
def test_duplicate_and_unordered_timestamps_are_rejected(
    tmp_path: Path, timestamps: list[str], expected_code: str
) -> None:
    _write_avi(tmp_path / "camera.avi")
    _write_csv(tmp_path / "camera.csv", timestamps)
    descriptor = _descriptor(tmp_path)

    with pytest.raises(TopdownPreviewProcessingError) as captured:
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            descriptor, tmp_path / "preview.mp4"
        )

    assert captured.value.code == expected_code


@pytest.mark.parametrize("timestamp_count", [2, 4])
def test_frame_count_mismatch_is_rejected(
    tmp_path: Path, timestamp_count: int
) -> None:
    _write_avi(tmp_path / "camera.avi", frame_count=3)
    _write_csv(
        tmp_path / "camera.csv",
        [f"1700000000.{index + 1}" for index in range(timestamp_count)],
    )
    descriptor = _descriptor(tmp_path)

    with pytest.raises(TopdownPreviewProcessingError) as captured:
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            descriptor, tmp_path / "preview.mp4"
        )

    assert captured.value.code == "topdown_frame_count_mismatch"


def test_missing_timestamp_column_and_changed_source_fail_safely(
    tmp_path: Path,
) -> None:
    _write_avi(tmp_path / "camera.avi")
    (tmp_path / "camera.csv").write_text("wrong\n1\n", encoding="utf-8")
    descriptor = _descriptor(tmp_path)

    with pytest.raises(TopdownPreviewProcessingError) as missing:
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            descriptor, tmp_path / "missing.mp4"
        )
    assert missing.value.code == "topdown_timestamp_column_invalid"

    (tmp_path / "camera.csv").write_text(
        "unix_timestamp\n1700000000.1\n", encoding="utf-8"
    )
    with pytest.raises(TopdownPreviewProcessingError) as changed:
        TopdownPreviewProcessor(V0_PREVIEW_PROFILE).process(
            descriptor, tmp_path / "changed.mp4"
        )
    assert changed.value.code == "topdown_source_changed"
