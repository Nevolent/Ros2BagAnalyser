from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import stat

from .types import SafeDiagnostic, SourceCondition


SQLITE_HEADER_BYTES = 100
SQLITE_VM_INSTRUCTION_BUDGET = 10_000
SQLITE_PROGRESS_INTERVAL = 100
REQUIRED_ROS_COLUMNS = {
    "topics": {"id", "name", "type", "serialization_format"},
    "messages": {"id", "topic_id", "timestamp", "data"},
}
STABLE_DESCRIPTOR_ROOT = Path("/proc/self/fd")


@dataclass(frozen=True)
class SQLiteProbeResult:
    condition: SourceCondition
    diagnostic: SafeDiagnostic | None
    size_bytes: int | None
    mtime_ns: int | None
    revision_facts: tuple[tuple[str, int | str], ...]


def probe_sqlite_database(path: Path) -> SQLiteProbeResult:
    try:
        descriptor, header, before = _open_database(path)
    except OSError:
        return SQLiteProbeResult(
            condition=SourceCondition.UNINSPECTABLE,
            diagnostic=SafeDiagnostic(
                "sqlite_unreadable", "The ROS database could not be read safely."
            ),
            size_bytes=None,
            mtime_ns=None,
            revision_facts=(),
        )
    except ValueError as error:
        return SQLiteProbeResult(
            condition=SourceCondition.INVALID,
            diagnostic=SafeDiagnostic("sqlite_not_regular_file", str(error)),
            size_bytes=None,
            mtime_ns=None,
            revision_facts=(),
        )

    try:
        result = _probe_open_database(descriptor, header, before)
        return _verify_unchanged(path, descriptor, before, result)
    finally:
        os.close(descriptor)


def _open_database(path: Path) -> tuple[int, bytes, os.stat_result]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise ValueError("The ROS database is not a regular file.")
        header = os.read(descriptor, SQLITE_HEADER_BYTES)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, header, details


def _probe_open_database(
    descriptor: int, header: bytes, details: os.stat_result
) -> SQLiteProbeResult:
    if len(header) < SQLITE_HEADER_BYTES:
        return _damaged(
            details,
            (),
            "sqlite_header_truncated",
            "The SQLite header is truncated.",
        )
    if header[:16] != b"SQLite format 3\x00":
        return _invalid(
            details,
            (),
            "sqlite_header_invalid",
            "The ROS database has an invalid SQLite header.",
        )

    page_size_raw = int.from_bytes(header[16:18], "big")
    page_size = 65_536 if page_size_raw == 1 else page_size_raw
    change_counter = int.from_bytes(header[24:28], "big")
    page_count = int.from_bytes(header[28:32], "big")
    version_valid_for = int.from_bytes(header[92:96], "big")
    facts = (
        ("page_size", page_size),
        ("page_count", page_count),
        ("change_counter", change_counter),
        ("version_valid_for", version_valid_for),
        ("schema_cookie", int.from_bytes(header[40:44], "big")),
        ("schema_format", int.from_bytes(header[44:48], "big")),
        ("text_encoding", int.from_bytes(header[56:60], "big")),
        ("user_version", int.from_bytes(header[60:64], "big")),
        ("application_id", int.from_bytes(header[68:72], "big")),
    )

    if not _valid_page_size(page_size):
        return _invalid(
            details,
            facts,
            "sqlite_page_size_invalid",
            "The SQLite page size is invalid.",
        )
    page_count_is_authoritative = (
        page_count != 0 and change_counter == version_valid_for
    )
    if details.st_size % page_size != 0:
        return _damaged(
            details,
            facts,
            "sqlite_size_mismatch",
            "The SQLite header declares a different database size than the source file.",
        )
    expected_size = page_size * page_count
    if page_count_is_authoritative and expected_size != details.st_size:
        return _damaged(
            details,
            facts,
            "sqlite_size_mismatch",
            "The SQLite header declares a different database size than the source file.",
        )
    return _probe_schema_readonly(descriptor, details, facts)


def _probe_schema_readonly(
    descriptor: int,
    details: os.stat_result,
    facts: tuple[tuple[str, int | str], ...],
) -> SQLiteProbeResult:
    completed_instructions = 0

    def progress_handler() -> int:
        nonlocal completed_instructions
        completed_instructions += SQLITE_PROGRESS_INTERVAL
        return int(completed_instructions > SQLITE_VM_INSTRUCTION_BUDGET)

    try:
        # SQLite opens its own handle. On the Linux/WSL V0 runtime, the procfs
        # descriptor path makes that second open target the already verified inode
        # rather than looking up the source pathname again.
        descriptor_path = STABLE_DESCRIPTOR_ROOT / str(descriptor)
        if not _same_file(os.stat(descriptor_path), details):
            raise OSError("The stable descriptor identity changed.")
        uri = f"{descriptor_path.as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(
            uri,
            uri=True,
            timeout=0.0,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.set_progress_handler(progress_handler, SQLITE_PROGRESS_INTERVAL)
            rows = connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type = 'table' AND name IN ('topics', 'messages') LIMIT 2"
            ).fetchall()
            table_columns = {
                table_name: {
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA table_info('{table_name}')"
                    ).fetchall()
                }
                for table_name in REQUIRED_ROS_COLUMNS
            }
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        code = getattr(error, "sqlite_errorcode", None)
        damaged_codes = {
            getattr(sqlite3, "SQLITE_CORRUPT", 11),
            getattr(sqlite3, "SQLITE_NOTADB", 26),
        }
        if code in damaged_codes or any(
            word in str(error).casefold() for word in ("malformed", "corrupt")
        ):
            return _damaged(
                details,
                facts,
                "sqlite_malformed",
                "The ROS database is malformed or corrupt.",
            )
        return SQLiteProbeResult(
            condition=SourceCondition.UNINSPECTABLE,
            diagnostic=SafeDiagnostic(
                "sqlite_probe_failed", "The ROS database could not be inspected safely."
            ),
            size_bytes=details.st_size,
            mtime_ns=details.st_mtime_ns,
            revision_facts=facts,
        )
    except OSError:
        return SQLiteProbeResult(
            condition=SourceCondition.UNINSPECTABLE,
            diagnostic=SafeDiagnostic(
                "sqlite_probe_failed", "The ROS database could not be inspected safely."
            ),
            size_bytes=details.st_size,
            mtime_ns=details.st_mtime_ns,
            revision_facts=facts,
        )

    if {row[0] for row in rows} != {"topics", "messages"}:
        return _invalid(
            details,
            facts,
            "sqlite_ros_schema_missing",
            "The SQLite database does not contain the expected ROS bag tables.",
        )
    if any(
        not required_columns.issubset(table_columns[table_name])
        for table_name, required_columns in REQUIRED_ROS_COLUMNS.items()
    ):
        return _invalid(
            details,
            facts,
            "sqlite_ros_schema_invalid",
            "The SQLite database does not contain the expected ROS bag columns.",
        )
    return SQLiteProbeResult(
        condition=SourceCondition.READABLE,
        diagnostic=None,
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
        revision_facts=facts,
    )


def _verify_unchanged(
    path: Path,
    descriptor: int,
    before: os.stat_result,
    result: SQLiteProbeResult,
) -> SQLiteProbeResult:
    try:
        descriptor_after = os.fstat(descriptor)
        path_after = os.stat(path, follow_symlinks=False)
    except OSError:
        return _changed(before, result.revision_facts)
    if not _same_file(before, descriptor_after) or not _same_file(before, path_after):
        return _changed(before, result.revision_facts)
    return result


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_size,
        left.st_mtime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_size,
        right.st_mtime_ns,
    )


def _changed(
    details: os.stat_result,
    facts: tuple[tuple[str, int | str], ...],
) -> SQLiteProbeResult:
    return SQLiteProbeResult(
        condition=SourceCondition.UNINSPECTABLE,
        diagnostic=SafeDiagnostic(
            "sqlite_changed_during_scan", "The ROS database changed during the scan."
        ),
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
        revision_facts=facts,
    )


def _valid_page_size(page_size: int) -> bool:
    return 512 <= page_size <= 65_536 and page_size & (page_size - 1) == 0


def _damaged(
    details: os.stat_result,
    facts: tuple[tuple[str, int | str], ...],
    code: str,
    message: str,
) -> SQLiteProbeResult:
    return SQLiteProbeResult(
        condition=SourceCondition.DAMAGED,
        diagnostic=SafeDiagnostic(code, message),
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
        revision_facts=facts,
    )


def _invalid(
    details: os.stat_result,
    facts: tuple[tuple[str, int | str], ...],
    code: str,
    message: str,
) -> SQLiteProbeResult:
    return SQLiteProbeResult(
        condition=SourceCondition.INVALID,
        diagnostic=SafeDiagnostic(code, message),
        size_bytes=details.st_size,
        mtime_ns=details.st_mtime_ns,
        revision_facts=facts,
    )
