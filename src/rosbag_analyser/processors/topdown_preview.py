from __future__ import annotations

import csv
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Iterator, TextIO

import av
from av.video.frame import PictureType

from rosbag_analyser.catalog.limits import is_postgres_bigint
from rosbag_analyser.catalog.paths import SourceFileIdentity, source_file_identity
from rosbag_analyser.config import PreviewProfile
from rosbag_analyser.job_control import JobControlToken
from rosbag_analyser.timeline import media_pts_digest_chunk, nanoseconds_to_media_pts
from rosbag_analyser.topdown_preview import TopdownSourceDescriptor


MAX_TIMESTAMP_CSV_BYTES = 64 * 1024 * 1024
MAX_CSV_ROW_CHARACTERS = 16 * 1024
MAX_TIMESTAMP_CHARACTERS = 64
MAX_VIDEO_WIDTH = 8_192
MAX_VIDEO_HEIGHT = 8_192
MAX_VIDEO_PIXELS = MAX_VIDEO_WIDTH * MAX_VIDEO_HEIGHT
TIMESTAMP_PATTERN = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]{1,9})?$", re.ASCII)


class TopdownPreviewProcessingError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class TopdownPreviewResult:
    input_frame_count: int
    timestamp_count: int
    encoded_frame_count: int
    coverage_start_ns: int
    coverage_end_ns: int
    output_width: int
    output_height: int
    measured_span_ns: int
    media_pts_sha256: str
    warnings: tuple[str, ...]


class TopdownPreviewProcessor:
    def __init__(self, profile: PreviewProfile) -> None:
        self.profile = profile

    def process(
        self,
        descriptor: TopdownSourceDescriptor,
        output_path: Path,
        *,
        control: JobControlToken | None = None,
    ) -> TopdownPreviewResult:
        if descriptor.timestamps_identity.size_bytes > MAX_TIMESTAMP_CSV_BYTES:
            raise TopdownPreviewProcessingError(
                "topdown_timestamps_too_large",
                "The top-down timestamp file exceeds the supported size.",
            )
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
            os, "O_NOFOLLOW", 0
        )
        try:
            video_descriptor = os.open(descriptor.video_path, flags)
            try:
                timestamps_descriptor = os.open(descriptor.timestamps_path, flags)
            except BaseException:
                os.close(video_descriptor)
                raise
        except OSError as error:
            raise TopdownPreviewProcessingError(
                "topdown_source_open_failed",
                "The top-down sources could not be opened safely.",
            ) from error

        try:
            with os.fdopen(
                video_descriptor, "rb", closefd=True
            ) as video_file, os.fdopen(
                timestamps_descriptor,
                "r",
                encoding="utf-8-sig",
                errors="strict",
                newline="",
                closefd=True,
            ) as timestamps_file:
                self._validate_open_identity(
                    video_file.fileno(), descriptor.video_identity, "video"
                )
                self._validate_open_identity(
                    timestamps_file.fileno(),
                    descriptor.timestamps_identity,
                    "timestamps",
                )
                result = self._convert(
                    descriptor, video_file, timestamps_file, output_path, control
                )
                self._validate_open_identity(
                    video_file.fileno(), descriptor.video_identity, "video"
                )
                self._validate_open_identity(
                    timestamps_file.fileno(),
                    descriptor.timestamps_identity,
                    "timestamps",
                )
                return result
        except TopdownPreviewProcessingError:
            raise
        except (OSError, UnicodeError, csv.Error) as error:
            raise TopdownPreviewProcessingError(
                "topdown_source_read_failed",
                "The top-down sources could not be read safely.",
            ) from error

    def _convert(
        self,
        descriptor: TopdownSourceDescriptor,
        video_file: object,
        timestamps_file: TextIO,
        output_path: Path,
        control: JobControlToken | None,
    ) -> TopdownPreviewResult:
        timestamps = _iter_csv_timestamps(timestamps_file)
        input_frames = 0
        encoded_frames = 0
        first_timestamp: int | None = None
        last_timestamp: int | None = None
        last_pts: int | None = None
        source_size: tuple[int, int] | None = None
        output_size: tuple[int, int] | None = None
        output_container: av.container.OutputContainer | None = None
        output_stream: av.video.stream.VideoStream | None = None
        input_container: av.container.InputContainer | None = None
        time_base = Fraction(1, self.profile.media_timescale)
        keyframe_interval_ns = self.profile.keyframe_interval_seconds * 1_000_000_000
        last_keyframe_elapsed_ns: int | None = None
        media_pts_digest = hashlib.sha256()
        processing_failure: BaseException | None = None

        try:
            try:
                input_container = av.open(video_file, mode="r")
            except (av.error.FFmpegError, OSError, ValueError) as error:
                raise TopdownPreviewProcessingError(
                    "topdown_video_open_failed",
                    "The top-down video could not be decoded.",
                ) from error
            video_streams = tuple(input_container.streams.video)
            if len(video_streams) != 1:
                raise TopdownPreviewProcessingError(
                    "topdown_video_stream_unsupported",
                    "The top-down video must contain exactly one video stream.",
                )
            video_stream = video_streams[0]
            source_size = (
                video_stream.codec_context.width,
                video_stream.codec_context.height,
            )
            output_size = _output_dimensions(*source_size, self.profile)
            video_stream.codec_context.options = {
                **video_stream.codec_context.options,
                "max_pixels": str(MAX_VIDEO_PIXELS),
            }
            for frame in input_container.decode(video_stream):
                if control is not None:
                    control.checkpoint("processing")
                input_frames += 1
                try:
                    timestamp = next(timestamps)
                except StopIteration as error:
                    raise TopdownPreviewProcessingError(
                        "topdown_frame_count_mismatch",
                        "The top-down video and timestamp row counts do not match.",
                    ) from error
                dimensions = (frame.width, frame.height)
                if input_frames == 1:
                    if dimensions != source_size:
                        raise TopdownPreviewProcessingError(
                            "topdown_dimensions_changed",
                            "The top-down video dimensions changed during decoding.",
                        )
                    output_container, output_stream = _open_output(
                        output_path, output_size, self.profile, time_base
                    )
                elif dimensions != source_size:
                    raise TopdownPreviewProcessingError(
                        "topdown_dimensions_changed",
                        "The top-down video dimensions changed during decoding.",
                    )

                if first_timestamp is None:
                    first_timestamp = timestamp
                elapsed_ns = timestamp - first_timestamp
                pts = nanoseconds_to_media_pts(
                    elapsed_ns, self.profile.media_timescale
                )
                if last_pts is not None and pts <= last_pts:
                    raise TopdownPreviewProcessingError(
                        "topdown_media_timestamp_collision",
                        "Top-down timestamps exceed the supported media precision.",
                    )
                assert output_container is not None
                assert output_stream is not None
                force_keyframe = (
                    last_keyframe_elapsed_ns is None
                    or elapsed_ns - last_keyframe_elapsed_ns >= keyframe_interval_ns
                )
                _encode_frame(
                    output_container,
                    output_stream,
                    frame,
                    pts,
                    time_base,
                    self.profile,
                    force_keyframe=force_keyframe,
                )
                if force_keyframe:
                    last_keyframe_elapsed_ns = elapsed_ns
                encoded_frames += 1
                media_pts_digest.update(media_pts_digest_chunk(pts))
                last_timestamp = timestamp
                last_pts = pts

            if control is not None:
                control.checkpoint("processing", force=True)
            try:
                next(timestamps)
            except StopIteration:
                pass
            else:
                raise TopdownPreviewProcessingError(
                    "topdown_frame_count_mismatch",
                    "The top-down video and timestamp row counts do not match.",
                )
            if input_frames == 0 or first_timestamp is None or last_timestamp is None:
                raise TopdownPreviewProcessingError(
                    "topdown_video_empty",
                    "The top-down video contains no decodable frames.",
                )
            assert output_stream is not None
            assert output_container is not None
            for packet in output_stream.encode():
                output_container.mux(packet)
        except TopdownPreviewProcessingError as error:
            processing_failure = error
            raise
        except (av.error.FFmpegError, OSError, ValueError) as error:
            processing_failure = error
            raise TopdownPreviewProcessingError(
                "topdown_processing_failed",
                "The top-down preview could not be generated.",
            ) from error
        except BaseException as error:
            processing_failure = error
            raise
        finally:
            if input_container is not None:
                input_container.close()
            if output_container is not None:
                try:
                    output_container.close()
                except (av.error.FFmpegError, OSError, ValueError) as error:
                    if processing_failure is None:
                        raise TopdownPreviewProcessingError(
                            "topdown_processing_failed",
                            "The top-down preview could not be generated.",
                        ) from error

        assert output_size is not None
        coverage_start_ns = first_timestamp - descriptor.bag_start_ns
        coverage_end_ns = last_timestamp - descriptor.bag_start_ns
        if not is_postgres_bigint(coverage_start_ns) or not is_postgres_bigint(
            coverage_end_ns
        ):
            raise TopdownPreviewProcessingError(
                "topdown_coverage_out_of_range",
                "The top-down coverage is outside the supported time range.",
            )
        return TopdownPreviewResult(
            input_frame_count=input_frames,
            timestamp_count=input_frames,
            encoded_frame_count=encoded_frames,
            coverage_start_ns=coverage_start_ns,
            coverage_end_ns=coverage_end_ns,
            output_width=output_size[0],
            output_height=output_size[1],
            measured_span_ns=last_timestamp - first_timestamp,
            media_pts_sha256=media_pts_digest.hexdigest(),
            warnings=_coverage_warnings(
                coverage_start_ns, coverage_end_ns, descriptor.bag_duration_ns
            ),
        )

    @staticmethod
    def _validate_open_identity(
        file_descriptor: int, expected: SourceFileIdentity, label: str
    ) -> None:
        details = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or source_file_identity(details) != expected
        ):
            raise TopdownPreviewProcessingError(
                "topdown_source_changed",
                f"The top-down {label} changed during preview generation.",
            )


def _bounded_lines(file: TextIO) -> Iterator[str]:
    for line in file:
        if len(line) > MAX_CSV_ROW_CHARACTERS:
            raise TopdownPreviewProcessingError(
                "topdown_timestamp_row_too_large",
                "A top-down timestamp row exceeds the supported size.",
            )
        if not line.strip():
            raise TopdownPreviewProcessingError(
                "topdown_timestamp_row_invalid",
                "The top-down timestamp file contains an empty row.",
            )
        yield line


def _iter_csv_timestamps(file: TextIO) -> Iterator[int]:
    reader = csv.DictReader(_bounded_lines(file))
    fieldnames = reader.fieldnames
    if fieldnames is None or fieldnames.count("unix_timestamp") != 1:
        raise TopdownPreviewProcessingError(
            "topdown_timestamp_column_invalid",
            "The top-down timestamp file must contain one unix_timestamp column.",
        )
    previous: int | None = None
    count = 0
    for row in reader:
        count += 1
        raw = row.get("unix_timestamp")
        timestamp = parse_unix_timestamp_ns(raw)
        if previous is not None:
            if timestamp == previous:
                raise TopdownPreviewProcessingError(
                    "topdown_timestamp_duplicate",
                    "Top-down timestamps must not contain duplicate values.",
                )
            if timestamp < previous:
                raise TopdownPreviewProcessingError(
                    "topdown_timestamps_unordered",
                    "Top-down timestamps must be strictly increasing.",
                )
        previous = timestamp
        yield timestamp
    if count == 0:
        raise TopdownPreviewProcessingError(
            "topdown_timestamps_empty",
            "The top-down timestamp file contains no timestamp rows.",
        )


def parse_unix_timestamp_ns(value: str | None) -> int:
    text = "" if value is None else value.strip()
    if (
        not text
        or len(text) > MAX_TIMESTAMP_CHARACTERS
        or TIMESTAMP_PATTERN.fullmatch(text) is None
    ):
        raise TopdownPreviewProcessingError(
            "topdown_timestamp_invalid",
            "A top-down Unix timestamp is invalid.",
        )
    sign = -1 if text.startswith("-") else 1
    unsigned = text.lstrip("+-")
    whole_text, separator, fraction_text = unsigned.partition(".")
    fraction_ns = int(fraction_text.ljust(9, "0")) if separator else 0
    timestamp_ns = sign * (int(whole_text) * 1_000_000_000 + fraction_ns)
    if not is_postgres_bigint(timestamp_ns):
        raise TopdownPreviewProcessingError(
            "topdown_timestamp_out_of_range",
            "A top-down Unix timestamp is outside the supported range.",
        )
    return timestamp_ns


def _output_dimensions(
    width: int, height: int, profile: PreviewProfile
) -> tuple[int, int]:
    if (
        width <= 0
        or height <= 0
        or width > MAX_VIDEO_WIDTH
        or height > MAX_VIDEO_HEIGHT
    ):
        raise TopdownPreviewProcessingError(
            "topdown_dimensions_invalid",
            "The top-down video has invalid dimensions.",
        )
    scale = min(1.0, profile.max_width / width, profile.max_height / height)
    output_width = max(2, int(width * scale))
    output_height = max(2, int(height * scale))
    output_width -= output_width % 2
    output_height -= output_height % 2
    return output_width, output_height


def _open_output(
    output_path: Path,
    output_size: tuple[int, int],
    profile: PreviewProfile,
    time_base: Fraction,
) -> tuple[av.container.OutputContainer, av.video.stream.VideoStream]:
    container = av.open(
        os.fspath(output_path),
        mode="w",
        format=profile.container,
        options={"movflags": "+faststart"},
    )
    stream = container.add_stream(profile.codec)
    stream.width = output_size[0]
    stream.height = output_size[1]
    stream.pix_fmt = profile.pixel_format
    stream.time_base = time_base
    stream.codec_context.time_base = time_base
    stream.codec_context.max_b_frames = 0
    stream.options = {
        "crf": str(profile.crf),
        "preset": profile.preset,
        "sc_threshold": "0",
    }
    return container, stream


def _encode_frame(
    container: av.container.OutputContainer,
    stream: av.video.stream.VideoStream,
    source: av.VideoFrame,
    pts: int,
    time_base: Fraction,
    profile: PreviewProfile,
    *,
    force_keyframe: bool,
) -> None:
    frame = source.reformat(
        width=stream.width,
        height=stream.height,
        format=profile.pixel_format,
    )
    frame.pts = pts
    frame.time_base = time_base
    if force_keyframe:
        frame.pict_type = PictureType.I
    for packet in stream.encode(frame):
        container.mux(packet)


def _coverage_warnings(
    coverage_start_ns: int, coverage_end_ns: int, bag_duration_ns: int
) -> tuple[str, ...]:
    warnings: list[str] = []
    if coverage_start_ns < 0:
        warnings.append("coverage_starts_before_recording")
    elif coverage_start_ns > 0:
        warnings.append("coverage_starts_after_recording")
    if coverage_end_ns < bag_duration_ns:
        warnings.append("coverage_ends_before_recording")
    elif coverage_end_ns > bag_duration_ns:
        warnings.append("coverage_ends_after_recording")
    return tuple(warnings)
