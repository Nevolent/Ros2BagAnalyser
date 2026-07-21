from __future__ import annotations

from fractions import Fraction
import json
import os
from pathlib import Path
import shutil

import av
import numpy as np
import pytest

from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.config import V0_PREVIEW_PROFILE


def _store(derived_root: Path) -> ArtifactStore:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None
    return ArtifactStore(derived_root, Path(ffmpeg), Path(ffprobe))


def _write_preview(path: Path, *, faststart: bool = True) -> None:
    options = {"movflags": "+faststart"} if faststart else None
    container = av.open(path, "w", format="mp4", options=options)
    stream = container.add_stream("libx264")
    stream.width = 4
    stream.height = 2
    stream.pix_fmt = "yuv420p"
    stream.time_base = Fraction(1, 1_000_000)
    stream.codec_context.time_base = stream.time_base
    stream.codec_context.max_b_frames = 0
    for pts in (0, 250_000):
        frame = av.VideoFrame.from_ndarray(
            np.zeros((2, 4, 3), dtype=np.uint8), format="bgr24"
        )
        frame.pts = pts
        frame.time_base = stream.time_base
        for packet in stream.encode(frame):
            container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _manifest(path: Path, identity: str) -> dict[str, object]:
    details = path.stat(follow_symlinks=False)
    return {
        "cache_identity": identity,
        "schema_version": 1,
        "output": {
            "size_bytes": details.st_size,
            "file_identity": {
                "device_id": details.st_dev,
                "inode": details.st_ino,
                "mtime_ns": details.st_mtime_ns,
            },
        },
    }


def test_validation_checks_profile_duration_and_representative_seeks(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(4)
    output = workspace / "preview.mp4"
    _write_preview(output)

    validation = store.validate_preview(
        output,
        V0_PREVIEW_PROFILE,
        expected_width=4,
        expected_height=2,
        expected_frame_count=2,
        measured_span_ns=250_000_000,
    )

    assert validation.size_bytes == output.stat().st_size
    assert validation.codec == "h264"
    assert validation.pixel_format == "yuv420p"
    assert validation.width == 4
    assert validation.height == 2

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_preview(
            output,
            V0_PREVIEW_PROFILE,
            expected_width=6,
            expected_height=2,
            expected_frame_count=2,
            measured_span_ns=250_000_000,
        )
    assert captured.value.code == "preview_validation_mismatch"


def test_validation_rejects_mp4_that_requires_a_complete_download(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(5)
    output = workspace / "preview.mp4"
    _write_preview(output, faststart=False)

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_preview(
            output,
            V0_PREVIEW_PROFILE,
            expected_width=4,
            expected_height=2,
            expected_frame_count=2,
            measured_span_ns=250_000_000,
        )

    assert captured.value.code == "preview_faststart_validation_failed"


def test_validation_rejects_incomplete_frame_count(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(6)
    output = workspace / "preview.mp4"
    _write_preview(output)

    with pytest.raises(ArtifactStoreError) as captured:
        store.validate_preview(
            output,
            V0_PREVIEW_PROFILE,
            expected_width=4,
            expected_height=2,
            expected_frame_count=3,
            measured_span_ns=250_000_000,
        )

    assert captured.value.code == "preview_validation_mismatch"


def test_partial_workspace_is_not_visible_until_atomic_publication(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    identity = "a" * 64
    workspace = store.create_workspace(7)
    media = workspace / "preview.mp4"
    media.write_bytes(b"validated-media-placeholder")
    manifest = _manifest(media, identity)

    final_media = (
        store.artifacts_root / identity[:2] / identity / "preview.mp4"
    )
    assert not final_media.exists()

    published = store.publish(
        workspace,
        7,
        identity,
        manifest,
    )

    assert not workspace.exists()
    assert final_media.is_file()
    store.validate_media(
        published.output_relative_path,
        published.size_bytes,
        identity,
        manifest,
    )
    assert json.loads((final_media.parent / "manifest.json").read_text())[
        "cache_identity"
    ] == identity


def test_conflicting_published_directory_is_never_replaced(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    identity = "b" * 64
    existing = store.artifacts_root / identity[:2] / identity
    existing.mkdir(parents=True)
    (existing / "preview.mp4").write_bytes(b"existing")
    (existing / "manifest.json").write_text(
        json.dumps({"cache_identity": "c" * 64}), encoding="utf-8"
    )
    workspace = store.create_workspace(8)
    media = workspace / "preview.mp4"
    media.write_bytes(b"replacement")

    with pytest.raises(ArtifactStoreError) as captured:
        store.publish(
            workspace,
            8,
            identity,
            _manifest(media, identity),
        )

    assert captured.value.code == "artifact_collision"
    assert (existing / "preview.mp4").read_bytes() == b"existing"
    assert workspace.exists()


def test_validated_retry_can_replace_conflicting_owned_artifact(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    identity = "c" * 64
    existing = store.artifacts_root / identity[:2] / identity
    existing.mkdir(parents=True)
    (existing / "preview.mp4").write_bytes(b"invalid-old-media")
    (existing / "manifest.json").write_text("{}", encoding="utf-8")
    workspace = store.create_workspace(9)
    media = workspace / "preview.mp4"
    media.write_bytes(b"validated-replacement")
    size = media.stat().st_size
    manifest = _manifest(media, identity)

    published = store.publish(
        workspace,
        9,
        identity,
        manifest,
        replace_conflicting=True,
    )

    assert not workspace.exists()
    assert (existing / "preview.mp4").read_bytes() == b"validated-replacement"
    assert published.size_bytes == size


def test_initialization_does_not_follow_preexisting_owned_root_symlink(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    outside = tmp_path / "outside"
    derived.mkdir()
    outside.mkdir()
    (derived / "rosbag-analyser").symlink_to(outside, target_is_directory=True)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None
    assert ffprobe is not None

    with pytest.raises(ArtifactStoreError) as captured:
        ArtifactStore(derived, Path(ffmpeg), Path(ffprobe))

    assert captured.value.code == "derived_path_invalid"
    assert not (outside / "work").exists()
    assert not (outside / "artifacts").exists()


def test_open_media_rejects_symlinked_artifact_directory(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    outside = tmp_path / "outside"
    derived.mkdir()
    outside.mkdir()
    identity = "d" * 64
    (outside / "preview.mp4").write_bytes(b"outside")
    store = _store(derived)
    prefix = store.artifacts_root / identity[:2]
    prefix.mkdir()
    (prefix / identity).symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactStoreError) as captured:
        store.open_media(
            (
                f"rosbag-analyser/artifacts/front_preview/{identity[:2]}/"
                f"{identity}/preview.mp4"
            ),
            7,
            identity,
            {"cache_identity": identity, "output": {"size_bytes": 7}},
        )

    assert captured.value.code == "artifact_path_invalid"


def test_ready_media_rejects_same_size_replacement_and_stripped_manifest(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    identity = "e" * 64
    workspace = store.create_workspace(10)
    media = workspace / "preview.mp4"
    media.write_bytes(b"validated-media")
    manifest = _manifest(media, identity)
    published = store.publish(workspace, 10, identity, manifest)
    published_media = derived / published.output_relative_path

    replacement = published_media.with_name("replacement.mp4")
    replacement.write_bytes(b"changed-content")
    assert replacement.stat().st_size == published.size_bytes
    replacement.replace(published_media)

    with pytest.raises(ArtifactStoreError) as changed:
        store.validate_media(
            published.output_relative_path,
            published.size_bytes,
            identity,
            manifest,
        )
    assert changed.value.code == "artifact_file_changed"

    output = manifest["output"]
    assert isinstance(output, dict)
    output["file_identity"] = {
        "device_id": published_media.stat().st_dev,
        "inode": published_media.stat().st_ino,
        "mtime_ns": published_media.stat().st_mtime_ns,
    }
    (published_media.parent / "manifest.json").write_text(
        json.dumps(
            {
                "cache_identity": identity,
                "output": {"size_bytes": published.size_bytes},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ArtifactStoreError) as stripped:
        store.validate_media(
            published.output_relative_path,
            published.size_bytes,
            identity,
            manifest,
        )
    assert stripped.value.code == "artifact_manifest_mismatch"


def test_opened_media_descriptor_cannot_be_redirected_by_parent_symlink(
    tmp_path: Path,
) -> None:
    derived = tmp_path / "derived"
    outside = tmp_path / "outside"
    derived.mkdir()
    outside.mkdir()
    store = _store(derived)
    identity = "f" * 64
    workspace = store.create_workspace(11)
    media = workspace / "preview.mp4"
    media.write_bytes(b"inside")
    manifest = _manifest(media, identity)
    published = store.publish(workspace, 11, identity, manifest)
    opened = store.open_media(
        published.output_relative_path,
        published.size_bytes,
        identity,
        manifest,
    )

    artifacts_parent = derived / "rosbag-analyser" / "artifacts"
    artifacts_parent.rename(artifacts_parent.with_name("artifacts-original"))
    outside_final = outside / "front_preview" / identity[:2] / identity
    outside_final.mkdir(parents=True)
    (outside_final / "preview.mp4").write_bytes(b"outside")
    artifacts_parent.symlink_to(outside, target_is_directory=True)

    try:
        assert os.read(opened.descriptor, 20) == b"inside"
    finally:
        os.close(opened.descriptor)


def test_cleanup_rejects_workspace_not_owned_by_job(tmp_path: Path) -> None:
    derived = tmp_path / "derived"
    derived.mkdir()
    store = _store(derived)
    workspace = store.create_workspace(9)

    with pytest.raises(ArtifactStoreError) as captured:
        store.clean_workspace(workspace, 10)

    assert captured.value.code == "workspace_ownership_invalid"
    assert workspace.exists()
