from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat
import unicodedata

from .types import RootScanError


DEFAULT_MAX_CATALOG_DEPTH = 8
DEFAULT_MAX_CATALOG_ENTRIES = 100_000
DEFAULT_MAX_CATALOG_DIRECTORIES = 10_000
DEFAULT_MAX_RECORDING_DIRECTORIES = 5_000
DEFAULT_MAX_DIRECTORY_ENTRIES = 2_000
DEFAULT_MAX_RECORDING_ENTRIES = 256


class UnsafeSourcePath(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class SourceFileIdentity:
    device_id: int
    inode: int
    mode: int
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True)
class DirectEntry:
    name: str
    path: Path
    is_regular_file: bool
    is_symlink: bool
    size_bytes: int | None
    mtime_ns: int | None
    identity: SourceFileIdentity | None


@dataclass(frozen=True)
class CatalogScanLimits:
    max_depth: int = DEFAULT_MAX_CATALOG_DEPTH
    max_entries: int = DEFAULT_MAX_CATALOG_ENTRIES
    max_directories: int = DEFAULT_MAX_CATALOG_DIRECTORIES
    max_recordings: int = DEFAULT_MAX_RECORDING_DIRECTORIES
    max_directory_entries: int = DEFAULT_MAX_DIRECTORY_ENTRIES
    max_recording_entries: int = DEFAULT_MAX_RECORDING_ENTRIES

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.max_depth,
                self.max_entries,
                self.max_directories,
                self.max_recordings,
                self.max_directory_entries,
                self.max_recording_entries,
            )
        ):
            raise ValueError("Catalog scan limits must be positive.")


@dataclass(frozen=True)
class DiscoveredRecordingDirectory:
    path: Path
    entries: tuple[DirectEntry, ...] | None
    diagnostic_code: str | None = None
    diagnostic_message: str | None = None


def discover_recording_directories(
    archive_root: Path,
    limits: CatalogScanLimits | None = None,
) -> tuple[DiscoveredRecordingDirectory, ...]:
    """Find physical recording roots without following source symlinks.

    Traversal failures are root failures because they may hide an unknown
    recording. Once a directory is identified as a recording candidate, its
    direct-entry problems are returned with that candidate and can be isolated.
    """

    selected_limits = limits or CatalogScanLimits()
    discovered: list[DiscoveredRecordingDirectory] = []
    pending: list[tuple[Path, int]] = [(archive_root, 0)]
    visited_entries = 0
    visited_directories = 0

    while pending:
        directory, depth = pending.pop()
        visited_directories += 1
        if visited_directories > selected_limits.max_directories:
            raise RootScanError(
                "archive_directory_limit_exceeded",
                "The archive contains more directories than the configured scan limit.",
            )

        raw_entries: list[os.DirEntry[str]] = []
        try:
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    visited_entries += 1
                    if visited_entries > selected_limits.max_entries:
                        raise RootScanError(
                            "archive_entry_limit_exceeded",
                            "The archive contains more entries than the configured scan limit.",
                        )
                    _safe_path_segment(entry.name)
                    raw_entries.append(entry)
        except RootScanError:
            raise
        except UnsafeSourcePath as error:
            raise RootScanError(error.code, error.safe_message) from error
        except OSError as error:
            raise RootScanError(
                "archive_enumeration_failed",
                "An archive directory could not be enumerated completely.",
            ) from error

        metadata_candidate = any(entry.name == "metadata.yaml" for entry in raw_entries)
        child_directories: list[Path] = []
        if not metadata_candidate:
            try:
                child_directories = [
                    Path(entry.path)
                    for entry in raw_entries
                    if entry.is_dir(follow_symlinks=False)
                ]
            except OSError as error:
                raise RootScanError(
                    "archive_entry_uninspectable",
                    "An archive entry could not be inspected completely.",
                ) from error

        recognized_companion = any(
            Path(entry.name).suffix.casefold() in {".db3", ".avi", ".csv"}
            for entry in raw_entries
        )
        is_leaf_candidate = not child_directories and recognized_companion
        if metadata_candidate or is_leaf_candidate:
            if len(discovered) >= selected_limits.max_recordings:
                raise RootScanError(
                    "archive_recording_limit_exceeded",
                    "The archive contains more recording candidates than the configured scan limit.",
                )
            if len(raw_entries) > selected_limits.max_recording_entries:
                discovered.append(
                    DiscoveredRecordingDirectory(
                        path=directory,
                        entries=None,
                        diagnostic_code="recording_entry_limit_exceeded",
                        diagnostic_message=(
                            "The recording contains more direct entries than the configured scan limit."
                        ),
                    )
                )
                continue
            discovered.append(
                DiscoveredRecordingDirectory(
                    path=directory,
                    entries=_direct_entries(raw_entries),
                )
            )
            continue

        if len(raw_entries) > selected_limits.max_directory_entries:
            raise RootScanError(
                "archive_directory_entry_limit_exceeded",
                "An archive folder contains more direct entries than the configured scan limit.",
            )
        if child_directories and depth >= selected_limits.max_depth:
            raise RootScanError(
                "archive_depth_limit_exceeded",
                "The archive hierarchy exceeds the configured scan depth.",
            )
        for child in sorted(
            child_directories,
            key=lambda path: safe_filesystem_text(path.name),
            reverse=True,
        ):
            pending.append((child, depth + 1))

    return tuple(
        sorted(
            discovered,
            key=lambda item: archive_relative_path(archive_root, item.path),
        )
    )


def inventory_direct_entries(
    recording_root: Path,
    *,
    max_entries: int = DEFAULT_MAX_RECORDING_ENTRIES,
) -> tuple[DirectEntry, ...]:
    raw_entries: list[os.DirEntry[str]] = []
    try:
        with os.scandir(recording_root) as iterator:
            for entry in iterator:
                if len(raw_entries) >= max_entries:
                    raise UnsafeSourcePath(
                        "recording_entry_limit_exceeded",
                        "The recording contains more direct entries than the configured scan limit.",
                    )
                raw_entries.append(entry)
    except OSError as error:
        raise UnsafeSourcePath(
            "recording_enumeration_failed",
            "The recording directory could not be enumerated.",
        ) from error

    return _direct_entries(raw_entries)


def _direct_entries(raw_entries: list[os.DirEntry[str]]) -> tuple[DirectEntry, ...]:
    results: list[DirectEntry] = []
    for entry in sorted(raw_entries, key=lambda item: safe_filesystem_text(item.name)):
        try:
            details = entry.stat(follow_symlinks=False)
        except OSError:
            results.append(
                DirectEntry(
                    name=entry.name,
                    path=Path(entry.path),
                    is_regular_file=False,
                    is_symlink=entry.is_symlink(),
                    size_bytes=None,
                    mtime_ns=None,
                    identity=None,
                )
            )
            continue
        results.append(
            DirectEntry(
                name=entry.name,
                path=Path(entry.path),
                is_regular_file=stat.S_ISREG(details.st_mode),
                is_symlink=stat.S_ISLNK(details.st_mode),
                size_bytes=details.st_size,
                mtime_ns=details.st_mtime_ns,
                identity=source_file_identity(details),
            )
        )
    return tuple(results)


def resolve_declared_source(
    archive_root: Path, recording_root: Path, declared_path: str
) -> Path:
    raw_parts = declared_path.split("/")
    if (
        not declared_path
        or "\\" in declared_path
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise UnsafeSourcePath(
            "unsafe_source_path", "A declared source path is not a safe relative path."
        )
    relative = PurePosixPath(declared_path)
    if relative.is_absolute():
        raise UnsafeSourcePath(
            "unsafe_source_path", "A declared source path is not a safe relative path."
        )

    current = recording_root
    try:
        for part in relative.parts:
            current = current / part
            details = current.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise UnsafeSourcePath(
                    "source_symlink_rejected", "Source symlinks are not supported in V0."
                )
        resolved = current.resolve(strict=True)
    except FileNotFoundError:
        raise
    except UnsafeSourcePath:
        raise
    except OSError as error:
        raise UnsafeSourcePath(
            "source_path_uninspectable", "A declared source path could not be inspected."
        ) from error

    if archive_root not in resolved.parents or recording_root not in resolved.parents:
        raise UnsafeSourcePath(
            "source_path_escape", "A declared source path escapes its recording directory."
        )
    if not resolved.is_file():
        raise UnsafeSourcePath(
            "source_not_regular_file", "A declared source is not a regular file."
        )
    return resolved


def archive_relative_path(archive_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(archive_root)
    except ValueError as error:
        raise UnsafeSourcePath(
            "source_path_escape", "A source path escapes the configured archive root."
        ) from error
    if not relative.parts:
        raise UnsafeSourcePath(
            "unsafe_source_path", "A recording path cannot be the archive root."
        )
    return "/".join(_safe_path_segment(part) for part in relative.parts)


def _safe_path_segment(value: str) -> str:
    if value in {"", ".", ".."} or "/" in value or "\\" in value:
        raise UnsafeSourcePath(
            "unsafe_source_name",
            "An archive entry name cannot be represented safely.",
        )
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            continue
        if unicodedata.category(character) in {"Cc", "Cf"}:
            raise UnsafeSourcePath(
                "unsafe_source_name",
                "An archive entry name contains unsafe control text.",
            )
    return safe_filesystem_text(value)


def safe_filesystem_text(value: str) -> str:
    """Return reversible UTF-8 text for a possibly surrogate-escaped filename."""
    escaped: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "%":
            escaped.append("%25")
        elif 0xDC80 <= codepoint <= 0xDCFF:
            escaped.append(f"%{codepoint - 0xDC00:02X}")
        elif 0xD800 <= codepoint <= 0xDFFF:
            escaped.append(f"%u{codepoint:04X}")
        else:
            escaped.append(character)
    return "".join(escaped)


def filesystem_text_from_safe(value: str) -> str:
    """Reverse ``safe_filesystem_text`` without treating encoded text as a path."""
    decoded: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "%":
            decoded.append(value[index])
            index += 1
            continue
        if value.startswith("%25", index):
            decoded.append("%")
            index += 3
            continue
        if value.startswith("%u", index) and index + 6 <= len(value):
            raw_codepoint = value[index + 2 : index + 6]
            if all(character in "0123456789abcdefABCDEF" for character in raw_codepoint):
                codepoint = int(raw_codepoint, 16)
                if 0xD800 <= codepoint <= 0xDFFF:
                    decoded.append(chr(codepoint))
                    index += 6
                    continue
        if index + 3 <= len(value):
            raw_byte = value[index + 1 : index + 3]
            if all(character in "0123456789abcdefABCDEF" for character in raw_byte):
                byte = int(raw_byte, 16)
                if 0x80 <= byte <= 0xFF:
                    decoded.append(chr(0xDC00 + byte))
                    index += 3
                    continue
        raise UnsafeSourcePath(
            "stored_source_path_invalid",
            "A stored source path has invalid filesystem escaping.",
        )
    return "".join(decoded)


def source_file_identity(details: os.stat_result) -> SourceFileIdentity:
    return SourceFileIdentity(
        device_id=details.st_dev,
        inode=details.st_ino,
        mode=details.st_mode,
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
    )
