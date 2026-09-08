from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3
import stat

from rosbag_analyser.catalog.metadata import MetadataError, TopicFact, parse_metadata_file
from rosbag_analyser.catalog.paths import UnsafeSourcePath, resolve_declared_source, source_file_identity
from rosbag_analyser.front_preview import CDR_SERIALIZATION, IMAGE_MESSAGE_TYPE
from rosbag_analyser.imu_series import IMU_MESSAGE_TYPE


MAX_DATABASE_TOPICS = 10_000


class TopicAuditError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class DatabaseTopic:
    name: str
    message_type: str
    serialization_format: str

    def json_values(self) -> dict[str, str]:
        return {"name": self.name, "type": self.message_type, "serialization_format": self.serialization_format}


def audit_recording_topics(
    archive_root: Path,
    recording_relative_path: str,
    *,
    front_topic: str,
    imu_topic: str,
) -> dict[str, object]:
    """Compare metadata topics with the immutable SQLite topic table."""
    root = _validated_archive_root(archive_root)
    recording_root = _resolve_selected_recording(root, recording_relative_path)
    metadata_path = recording_root / "metadata.yaml"
    try:
        metadata_details = metadata_path.lstat()
    except OSError as error:
        raise TopicAuditError("metadata_unavailable", "The recording metadata is unavailable.") from error
    if stat.S_ISLNK(metadata_details.st_mode) or not stat.S_ISREG(metadata_details.st_mode):
        raise TopicAuditError("metadata_unavailable", "The recording metadata is not a regular source file.")
    try:
        metadata = parse_metadata_file(metadata_path, expected_identity=source_file_identity(metadata_details))
    except MetadataError as error:
        raise TopicAuditError(error.diagnostic.code, error.diagnostic.message) from error
    if len(metadata.relative_file_paths) != 1:
        raise TopicAuditError("split_bag_unsupported", "The selected-recording topic audit supports one SQLite file per recording.")
    try:
        database_path = resolve_declared_source(root, recording_root, metadata.relative_file_paths[0])
        database_details = database_path.lstat()
    except (OSError, UnsafeSourcePath) as error:
        raise TopicAuditError("database_unavailable", "The recording database could not be resolved safely.") from error
    if stat.S_ISLNK(database_details.st_mode) or not stat.S_ISREG(database_details.st_mode):
        raise TopicAuditError("database_unavailable", "The recording database is not a regular source file.")
    database_topics = _read_database_topics(database_path, source_file_identity(database_details))
    return {
        "recording_path": recording_relative_path,
        "status": "complete",
        "configured": {
            "front": _configured_topic_result(front_topic, IMAGE_MESSAGE_TYPE, metadata.topics, database_topics),
            "imu": _configured_topic_result(imu_topic, IMU_MESSAGE_TYPE, metadata.topics, database_topics),
        },
        "candidate_front_topics": _candidates(IMAGE_MESSAGE_TYPE, metadata.topics, database_topics),
        "candidate_imu_topics": _candidates(IMU_MESSAGE_TYPE, metadata.topics, database_topics),
        "metadata_topics": [_metadata_topic_values(topic) for topic in metadata.topics],
        "database_topics": [topic.json_values() for topic in database_topics],
    }


def _read_database_topics(database_path: Path, expected_identity: object) -> tuple[DatabaseTopic, ...]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(database_path, flags)
    except OSError as error:
        raise TopicAuditError("database_open_failed", "The recording database could not be opened safely.") from error
    connection: sqlite3.Connection | None = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or source_file_identity(before) != expected_identity:
            raise TopicAuditError("database_changed", "The recording database changed before topic inspection.")
        connection = sqlite3.connect(f"file:/proc/self/fd/{descriptor}?mode=ro&immutable=1", uri=True)
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT name, type, serialization_format FROM topics ORDER BY id LIMIT ?",
            (MAX_DATABASE_TOPICS + 1,),
        ).fetchall()
        if len(rows) > MAX_DATABASE_TOPICS:
            raise TopicAuditError("topic_limit_exceeded", "The recording contains more topics than the audit limit.")
        topics = tuple(DatabaseTopic(str(name), str(message_type), str(serialization)) for name, message_type, serialization in rows)
        if source_file_identity(os.fstat(descriptor)) != source_file_identity(before):
            raise TopicAuditError("database_changed", "The recording database changed during topic inspection.")
        return topics
    except TopicAuditError:
        raise
    except sqlite3.Error as error:
        raise TopicAuditError("database_read_failed", "The recording topic table could not be read.") from error
    finally:
        if connection is not None:
            connection.close()
        os.close(descriptor)


def _configured_topic_result(configured_name: str, expected_type: str, metadata_topics: tuple[TopicFact, ...], database_topics: tuple[DatabaseTopic, ...]) -> dict[str, object]:
    metadata_matches = [topic for topic in metadata_topics if topic.name == configured_name]
    database_matches = [topic for topic in database_topics if topic.name == configured_name]
    return {
        "name": configured_name,
        "expected_type": expected_type,
        "expected_serialization_format": CDR_SERIALIZATION,
        "metadata_match": _metadata_topic_values(metadata_matches[0]) if len(metadata_matches) == 1 else None,
        "database_match": database_matches[0].json_values() if len(database_matches) == 1 else None,
        "metadata_match_count": len(metadata_matches),
        "database_match_count": len(database_matches),
        "usable": len(metadata_matches) == 1 and len(database_matches) == 1 and metadata_matches[0].message_type == expected_type and metadata_matches[0].serialization_format == CDR_SERIALIZATION and metadata_matches[0].message_count > 0 and database_matches[0].message_type == expected_type and database_matches[0].serialization_format == CDR_SERIALIZATION,
    }


def _candidates(expected_type: str, metadata_topics: tuple[TopicFact, ...], database_topics: tuple[DatabaseTopic, ...]) -> list[dict[str, object]]:
    names = sorted({topic.name for topic in metadata_topics if topic.message_type == expected_type} | {topic.name for topic in database_topics if topic.message_type == expected_type})
    return [{
        "name": name,
        "metadata": next((_metadata_topic_values(topic) for topic in metadata_topics if topic.name == name), None),
        "database": next((topic.json_values() for topic in database_topics if topic.name == name), None),
    } for name in names]


def _metadata_topic_values(topic: TopicFact) -> dict[str, object]:
    return {"name": topic.name, "type": topic.message_type, "serialization_format": topic.serialization_format, "message_count": topic.message_count}


def _validated_archive_root(path: Path) -> Path:
    if not path.is_absolute():
        raise TopicAuditError("archive_root_invalid", "The archive root must be absolute.")
    try:
        details = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise TopicAuditError("archive_root_unavailable", "The archive root could not be checked safely.") from error
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        raise TopicAuditError("archive_root_invalid", "The archive root must be a non-symbolic-link directory.")
    return resolved


def _resolve_selected_recording(root: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.startswith("/") or "\\" in relative_path:
        raise TopicAuditError("recording_path_invalid", "A recording path must be archive-relative.")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TopicAuditError("recording_path_invalid", "A recording path must be archive-relative.")
    current = root
    try:
        for part in parts:
            current = current / part
            details = current.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise TopicAuditError("source_symlink_rejected", "Source symlinks are not supported.")
        resolved = current.resolve(strict=True)
    except TopicAuditError:
        raise
    except OSError as error:
        raise TopicAuditError("recording_path_unavailable", "The selected recording is unavailable.") from error
    if root not in resolved.parents or not resolved.is_dir():
        raise TopicAuditError("recording_path_invalid", "The selected recording is outside the archive root.")
    return resolved
