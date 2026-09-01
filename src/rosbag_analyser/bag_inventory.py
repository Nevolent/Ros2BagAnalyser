#!/usr/bin/env python3
"""Create a bounded, metadata-only ROS 2 bag inventory.

This utility never opens bag storage files.  It reads directory entries and
``metadata.yaml`` only, so it is suitable for a source archive mounted
read-only.  The JSON output intentionally uses source-relative paths.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any, Sequence

from rosbag_analyser.storage_layout import is_reserved_cache_root_entry

try:
    import yaml
    from yaml.events import AliasEvent
except ImportError:  # pragma: no cover - exercised only outside the release runtime
    yaml = None
    AliasEvent = object  # type: ignore[assignment,misc]


SCHEMA_VERSION = 1
MAX_DEPTH = 64
MAX_ENTRIES = 2_000_000
MAX_METADATA_BYTES = 1_048_576
MAX_YAML_ALIASES = 100
MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 10_000
STORAGE_SUFFIXES = frozenset({".db3", ".mcap"})


class InventoryError(RuntimeError):
    """A safe error that does not reveal the private archive path."""


@dataclass(frozen=True)
class SourceEntry:
    relative_path: str
    name: str
    kind: str
    size_bytes: int
    mtime_ns: int
    absolute_path: Path


class _LimitedSafeLoader(yaml.SafeLoader if yaml is not None else object):
    def __init__(self, stream: Any) -> None:
        super().__init__(stream)  # type: ignore[misc]
        self._alias_count = 0
        self._depth = 0
        self._node_count = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        self._depth += 1
        self._node_count += 1
        try:
            if self._depth > MAX_YAML_DEPTH:
                raise yaml.YAMLError("YAML nesting limit exceeded")
            if self._node_count > MAX_YAML_NODES:
                raise yaml.YAMLError("YAML node limit exceeded")
            if self.check_event(AliasEvent):
                self._alias_count += 1
                if self._alias_count > MAX_YAML_ALIASES:
                    raise yaml.YAMLError("YAML alias limit exceeded")
            return super().compose_node(parent, index)  # type: ignore[misc]
        finally:
            self._depth -= 1


def build_bag_inventory(
    source_root: Path,
    *,
    max_depth: int,
    max_entries: int,
) -> dict[str, object]:
    """Inspect a source tree without following symlinks or opening bag payloads."""

    _validate_bounds(max_depth, max_entries)
    root = _validated_source_root(source_root)
    entries_by_directory, issues, complete = _walk_source_tree(
        root, max_depth=max_depth, max_entries=max_entries
    )

    bags: list[dict[str, object]] = []
    metadata_roots: set[str] = set()
    for directory, entries in sorted(entries_by_directory.items()):
        metadata = next((entry for entry in entries if entry.name == "metadata.yaml"), None)
        if metadata is None:
            continue
        metadata_roots.add(directory)
        bags.append(_metadata_bag(directory, entries, metadata))

    orphan_candidates = _orphan_storage_candidates(
        entries_by_directory, metadata_roots
    )
    bags.extend(orphan_candidates)
    bags.sort(key=lambda item: str(item["path"]))

    error_count = sum(
        1
        for bag in bags
        if isinstance(bag.get("metadata"), dict)
        and bag["metadata"].get("status") != "ok"
    )
    file_count = sum(
        1
        for entries in entries_by_directory.values()
        for entry in entries
        if entry.kind == "file"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "inspection": {
            "source_root_included": False,
            "path_base": "source_root",
            "complete": complete,
            "bounds": {"max_depth": max_depth, "max_entries": max_entries},
            "source_operations": [
                "directory enumeration",
                "lstat-style entry metadata",
                "bounded metadata.yaml reads",
            ],
            "bag_payload_files_opened": False,
            "symlinks_followed": False,
        },
        "summary": {
            "recording_count": len(bags),
            "metadata_bag_count": len(metadata_roots),
            "metadata_missing_candidate_count": len(orphan_candidates),
            "metadata_or_read_error_count": error_count,
            "source_file_count": file_count,
        },
        "issues": issues,
        "recordings": bags,
    }


def write_bag_inventory(
    source_root: Path,
    output_path: Path,
    *,
    max_depth: int,
    max_entries: int,
) -> dict[str, object]:
    """Write inventory JSON atomically outside the source tree without replacement."""

    root = _validated_source_root(source_root)
    output = output_path.absolute()
    if output.exists() or output.is_symlink():
        raise InventoryError("Inventory evidence already exists.")
    _reject_symlink_parent(output.parent)
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise InventoryError("Inventory evidence must be written outside source.")

    inventory = build_bag_inventory(
        root, max_depth=max_depth, max_entries=max_entries
    )
    temporary: Path | None = None
    try:
        output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent,
            prefix=f".{output.name}.", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(inventory, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, output)
    except OSError as error:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass
        raise InventoryError("Inventory evidence could not be written.") from error
    return inventory


def _validate_bounds(max_depth: int, max_entries: int) -> None:
    if not 0 < max_depth <= MAX_DEPTH or not 0 < max_entries <= MAX_ENTRIES:
        raise InventoryError("Inventory bounds must be positive and within supported limits.")


def _validated_source_root(source_root: Path) -> Path:
    try:
        details = source_root.stat(follow_symlinks=False)
        if source_root.is_symlink() or not stat.S_ISDIR(details.st_mode):
            raise InventoryError("The approved source root is not a safe directory.")
        return source_root.resolve(strict=True)
    except InventoryError:
        raise
    except OSError as error:
        raise InventoryError("The approved source root is unavailable.") from error


def _walk_source_tree(
    root: Path, *, max_depth: int, max_entries: int
) -> tuple[dict[str, list[SourceEntry]], list[dict[str, str]], bool]:
    pending: list[tuple[Path, PurePosixPath, int]] = [(root, PurePosixPath("."), 0)]
    result: dict[str, list[SourceEntry]] = {}
    issues: list[dict[str, str]] = []
    entry_count = 0
    complete = True

    while pending:
        directory, relative_directory, depth = pending.pop()
        directory_key = relative_directory.as_posix()
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: item.name)
        except OSError:
            issues.append({"code": "directory_unreadable", "path": directory_key})
            complete = False
            continue

        direct_entries: list[SourceEntry] = []
        child_directories: list[tuple[Path, PurePosixPath]] = []
        for child in children:
            if directory == root and is_reserved_cache_root_entry(child.name):
                continue
            if entry_count >= max_entries:
                issues.append({"code": "entry_limit_exceeded", "path": directory_key})
                return result, issues, False
            entry_count += 1
            relative = relative_directory / child.name
            try:
                details = child.stat(follow_symlinks=False)
            except OSError:
                issues.append({"code": "entry_unreadable", "path": relative.as_posix()})
                complete = False
                continue
            if child.is_symlink():
                kind = "symlink"
            elif stat.S_ISDIR(details.st_mode):
                kind = "directory"
                child_directories.append((Path(child.path), relative))
            elif stat.S_ISREG(details.st_mode):
                kind = "file"
            else:
                kind = "other"
            direct_entries.append(
                SourceEntry(
                    relative_path=relative.as_posix(),
                    name=child.name,
                    kind=kind,
                    size_bytes=int(details.st_size),
                    mtime_ns=int(details.st_mtime_ns),
                    absolute_path=Path(child.path),
                )
            )
        result[directory_key] = direct_entries
        if child_directories and depth >= max_depth:
            issues.append({"code": "depth_limit_exceeded", "path": directory_key})
            complete = False
            continue
        for child_directory, relative in reversed(child_directories):
            pending.append((child_directory, relative, depth + 1))
    return result, issues, complete


def _metadata_bag(
    directory: str, entries: list[SourceEntry], metadata: SourceEntry
) -> dict[str, object]:
    document, error = _read_metadata(metadata)
    metadata_facts: dict[str, object]
    if error is not None:
        metadata_facts = {"status": "error", "error": error}
    else:
        metadata_facts = {"status": "ok", **_metadata_facts(document)}
    return {
        "path": directory,
        "name": Path(directory).name if directory != "." else ".",
        "candidate_kind": "metadata_bag",
        "size_bytes": sum(entry.size_bytes for entry in entries if entry.kind == "file"),
        "files": [_entry_facts(entry, directory) for entry in entries],
        "metadata": metadata_facts,
    }


def _orphan_storage_candidates(
    entries_by_directory: dict[str, list[SourceEntry]], metadata_roots: set[str]
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for directory, entries in entries_by_directory.items():
        if _has_metadata_ancestor(directory, metadata_roots):
            continue
        storage = [
            entry
            for entry in entries
            if entry.kind == "file" and Path(entry.name).suffix.casefold() in STORAGE_SUFFIXES
        ]
        if not storage:
            continue
        candidates.append(
            {
                "path": directory,
                "name": Path(directory).name if directory != "." else ".",
                "candidate_kind": "metadata_missing_storage_candidate",
                "size_bytes": sum(entry.size_bytes for entry in entries if entry.kind == "file"),
                "files": [_entry_facts(entry, directory) for entry in entries],
                "metadata": {
                    "status": "error",
                    "error": {
                        "code": "metadata_missing",
                        "message": "Storage files were found without a readable metadata.yaml.",
                    },
                },
            }
        )
    return candidates


def _has_metadata_ancestor(directory: str, roots: set[str]) -> bool:
    current = PurePosixPath(directory)
    while True:
        if current.as_posix() in roots:
            return True
        if current == current.parent:
            return False
        current = current.parent


def _entry_facts(entry: SourceEntry, directory: str) -> dict[str, object]:
    relative = PurePosixPath(entry.relative_path)
    parent = PurePosixPath(directory)
    try:
        name = relative.relative_to(parent).as_posix()
    except ValueError:
        name = entry.name
    return {
        "path": name,
        "kind": entry.kind,
        "size_bytes": entry.size_bytes,
        "mtime_ns": str(entry.mtime_ns),
    }


def _read_metadata(entry: SourceEntry) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    if entry.kind != "file":
        return None, {"code": "metadata_not_regular_file", "message": "metadata.yaml is not a regular file."}
    if yaml is None:
        return None, {"code": "yaml_dependency_missing", "message": "PyYAML is required to inspect ROS metadata."}
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(entry.absolute_path, flags)
    except OSError:
        return None, {"code": "metadata_unreadable", "message": "metadata.yaml could not be read."}
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_METADATA_BYTES:
            return None, {"code": "metadata_unsupported_file", "message": "metadata.yaml is not a supported regular file."}
        raw = b""
        while len(raw) <= MAX_METADATA_BYTES:
            chunk = os.read(descriptor, min(65_536, MAX_METADATA_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(descriptor)
    except OSError:
        return None, {"code": "metadata_unreadable", "message": "metadata.yaml could not be read."}
    finally:
        os.close(descriptor)
    if len(raw) > MAX_METADATA_BYTES:
        return None, {"code": "metadata_too_large", "message": "metadata.yaml exceeds the read limit."}
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        return None, {"code": "metadata_changed_during_read", "message": "metadata.yaml changed during inspection."}
    try:
        parsed = yaml.load(raw, Loader=_LimitedSafeLoader)
    except (yaml.YAMLError, RecursionError):
        return None, {"code": "metadata_yaml_invalid", "message": "metadata.yaml is not valid YAML."}
    if not isinstance(parsed, dict):
        return None, {"code": "metadata_root_invalid", "message": "metadata.yaml has no mapping root."}
    return parsed, None


def _metadata_facts(document: dict[str, Any] | None) -> dict[str, object]:
    information = document.get("rosbag2_bagfile_information") if document else None
    if not isinstance(information, dict):
        return {"parse_status": "missing_rosbag2_bagfile_information"}
    topics: list[dict[str, object]] = []
    raw_topics = information.get("topics_with_message_count")
    if isinstance(raw_topics, list):
        for item in raw_topics:
            if not isinstance(item, dict):
                topics.append({"error": "topic_entry_invalid"})
                continue
            topic = item.get("topic_metadata")
            if not isinstance(topic, dict):
                topics.append({"error": "topic_metadata_invalid"})
                continue
            topics.append(
                {
                    "name": _text_or_none(topic.get("name")),
                    "type": _text_or_none(topic.get("type")),
                    "serialization_format": _text_or_none(topic.get("serialization_format")),
                    "message_count": _integer_as_string(item.get("message_count")),
                }
            )
    duration = information.get("duration")
    start = information.get("starting_time")
    return {
        "metadata_version": _integer_or_none(information.get("version")),
        "storage_identifier": _text_or_none(information.get("storage_identifier")),
        "relative_file_paths": _string_list(information.get("relative_file_paths")),
        "compression_format": _text_or_none(information.get("compression_format")),
        "compression_mode": _text_or_none(information.get("compression_mode")),
        "start_time_ns": _integer_as_string(
            start.get("nanoseconds_since_epoch") if isinstance(start, dict) else None
        ),
        "duration_ns": _integer_as_string(
            duration.get("nanoseconds") if isinstance(duration, dict) else None
        ),
        "message_count": _integer_as_string(information.get("message_count")),
        "topic_count": len(topics) if isinstance(raw_topics, list) else None,
        "topics": topics,
    }


def _integer_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _integer_as_string(value: object) -> str | None:
    integer = _integer_or_none(value)
    return None if integer is None else str(integer)


def _text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: object) -> list[str] | None:
    return list(value) if isinstance(value, list) and all(isinstance(item, str) for item in value) else None


def _reject_symlink_parent(path: Path) -> None:
    current = path
    while not current.exists():
        if current == current.parent:
            break
        current = current.parent
    try:
        if current.is_symlink() or current.resolve(strict=True) != current:
            raise InventoryError("The evidence path contains a symbolic link.")
    except OSError as error:
        raise InventoryError("The evidence path could not be validated.") from error


def main(arguments: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Capture a bounded, read-only ROS 2 bag metadata inventory."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-depth", type=int, default=32)
    parser.add_argument("--max-entries", type=int, default=500_000)
    parsed = parser.parse_args(arguments)
    try:
        inventory = write_bag_inventory(
            parsed.source_root,
            parsed.output,
            max_depth=parsed.max_depth,
            max_entries=parsed.max_entries,
        )
    except InventoryError as error:
        raise SystemExit(str(error)) from error
    summary = inventory["summary"]
    inspection = inventory["inspection"]
    print(
        "ROS bag inventory captured: "
        f"{summary['recording_count']} candidates, "
        f"{summary['metadata_or_read_error_count']} metadata/read errors, "
        f"complete={inspection['complete']}"
    )


if __name__ == "__main__":
    main()


__all__ = ["InventoryError", "build_bag_inventory", "write_bag_inventory"]
