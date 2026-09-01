from __future__ import annotations

import json
from pathlib import Path

import pytest

from rosbag_analyser.source_manifest import (
    ManifestError,
    build_source_manifest,
    write_source_manifest,
)


def test_manifest_records_only_relative_metadata_and_never_follows_symlinks(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    nested = source / "folder"
    nested.mkdir()
    payload = nested / "recording.db3"
    payload.write_bytes(b"payload-not-hashed")
    (source / "outside-link").symlink_to(outside, target_is_directory=True)

    entries = build_source_manifest(source, max_depth=4, max_entries=20)

    assert [(entry.relative_path, entry.kind) for entry in entries] == [
        ("folder", "directory"),
        ("folder/recording.db3", "file"),
        ("outside-link", "symlink"),
    ]
    file_entry = entries[1]
    assert file_entry.size_bytes == len(b"payload-not-hashed")
    assert isinstance(file_entry.mtime_ns, int)
    assert not hasattr(file_entry, "sha256")


def test_manifest_excludes_reserved_cache_before_bounds_and_digest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    source_file = source / "recording.db3"
    source_file.write_bytes(b"source")
    cache = source / "Rosbag_Analyser_Cache"
    cache.mkdir()
    for number in range(10):
        (cache / f"artifact-{number}.mp4").write_bytes(b"cache")

    before = build_source_manifest(source, max_depth=1, max_entries=1)
    (cache / "new-artifact.json").write_text("{}", encoding="utf-8")
    after = build_source_manifest(source, max_depth=1, max_entries=1)

    assert before == after
    assert [entry.relative_path for entry in after] == ["recording.db3"]


def test_manifest_bounds_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one").mkdir()
    (source / "one" / "two").mkdir()

    with pytest.raises(ManifestError, match="depth"):
        build_source_manifest(source, max_depth=1, max_entries=20)
    with pytest.raises(ManifestError, match="entry"):
        build_source_manifest(source, max_depth=4, max_entries=1)


def test_manifest_output_must_be_outside_source_and_is_deterministic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "b").write_bytes(b"b")
    (source / "a").write_bytes(b"a")
    output = tmp_path / "evidence" / "before.json"

    first = write_source_manifest(
        source, output, max_depth=2, max_entries=10
    )
    second = write_source_manifest(
        source, output.with_name("second.json"), max_depth=2, max_entries=10
    )

    assert first.digest_sha256 == second.digest_sha256
    document = json.loads(output.read_text(encoding="utf-8"))
    assert [entry["relative_path"] for entry in document["entries"]] == ["a", "b"]
    assert "source_root" not in document

    with pytest.raises(ManifestError, match="already exists"):
        write_source_manifest(
            source,
            output,
            max_depth=2,
            max_entries=10,
        )

    with pytest.raises(ManifestError, match="outside"):
        write_source_manifest(
            source,
            source / "forbidden.json",
            max_depth=2,
            max_entries=10,
        )
