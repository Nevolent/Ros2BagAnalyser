from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat

from .types import RootScanError


MAX_ARCHIVE_ENTRIES = 2_000
MAX_RECORDING_DIRECTORIES = 1_000
MAX_RECORDING_ENTRIES = 256


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


def discover_recording_directories(archive_root: Path) -> tuple[Path, ...]:
    directories: list[Path] = []
    try:
        with os.scandir(archive_root) as iterator:
            for entry_number, entry in enumerate(iterator, start=1):
                if entry_number > MAX_ARCHIVE_ENTRIES:
                    raise RootScanError(
                        "archive_entry_limit_exceeded",
                        "The archive contains more direct entries than the V0 "
                        "scan limit.",
                    )
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path))
                    if len(directories) > MAX_RECORDING_DIRECTORIES:
                        raise RootScanError(
                            "archive_directory_limit_exceeded",
                            "The archive contains more recording directories than "
                            "the V0 scan limit.",
                        )
    except OSError as error:
        raise RootScanError(
            "archive_enumeration_failed", "The archive root could not be enumerated."
        ) from error
    return tuple(sorted(directories, key=lambda path: path.name))


def inventory_direct_entries(recording_root: Path) -> tuple[DirectEntry, ...]:
    raw_entries: list[os.DirEntry[str]] = []
    try:
        with os.scandir(recording_root) as iterator:
            for entry in iterator:
                if len(raw_entries) >= MAX_RECORDING_ENTRIES:
                    raise UnsafeSourcePath(
                        "recording_entry_limit_exceeded",
                        "The recording contains more direct entries than the V0 "
                        "scan limit.",
                    )
                raw_entries.append(entry)
    except OSError as error:
        raise UnsafeSourcePath(
            "recording_enumeration_failed",
            "The recording directory could not be enumerated.",
        ) from error

    results: list[DirectEntry] = []
    for entry in sorted(raw_entries, key=lambda item: item.name):
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
    return safe_filesystem_text(relative.as_posix())


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


def source_file_identity(details: os.stat_result) -> SourceFileIdentity:
    return SourceFileIdentity(
        device_id=details.st_dev,
        inode=details.st_ino,
        mode=details.st_mode,
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
    )
