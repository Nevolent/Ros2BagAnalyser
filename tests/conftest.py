from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pytest
import yaml

from rosbag_analyser.storage_layout import is_reserved_cache_root_entry


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("optional acceptance")
    group.addoption(
        "--require-postgres",
        action="store_true",
        dest="require_postgres",
        help="Fail instead of skip when PostgreSQL acceptance prerequisites are absent.",
    )
    group.addoption(
        "--require-real-archive",
        action="store_true",
        dest="require_real_archive",
        help="Fail instead of skip when real-archive acceptance is not enabled.",
    )


def require_optional_prerequisite(
    config: pytest.Config,
    *,
    option_name: str,
    ready: bool,
    message: str,
) -> None:
    if ready:
        return
    if config.getoption(option_name):
        pytest.fail(message)
    pytest.skip(message)


def create_rosbag_database(path: Path, *, include_ros_tables: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        if include_ros_tables:
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
                "CREATE INDEX timestamp_idx ON messages (timestamp ASC)"
            )
        else:
            connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()


def metadata_document(
    database_name: str = "recording_0.db3",
    *,
    storage_identifier: str = "sqlite3",
    version: int = 5,
    compression_format: str = "",
    compression_mode: str = "",
    relative_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "rosbag2_bagfile_information": {
            "version": version,
            "storage_identifier": storage_identifier,
            "duration": {"nanoseconds": 2_500_000_000},
            "starting_time": {"nanoseconds_since_epoch": 1_700_000_000_000_000_000},
            "message_count": 42,
            "topics_with_message_count": [
                {
                    "topic_metadata": {
                        "name": "/camera/image_raw",
                        "type": "sensor_msgs/msg/Image",
                        "serialization_format": "cdr",
                        "offered_qos_profiles": "",
                    },
                    "message_count": 42,
                }
            ],
            "compression_format": compression_format,
            "compression_mode": compression_mode,
            "relative_file_paths": (
                [database_name]
                if relative_file_paths is None
                else relative_file_paths
            ),
            "files": [],
        }
    }


def create_recording(
    archive_root: Path,
    name: str,
    *,
    damaged: bool = False,
    include_video: bool = True,
    include_csv: bool = True,
    metadata_overrides: dict[str, Any] | None = None,
) -> Path:
    recording = archive_root / name
    recording.mkdir()
    database_name = f"{name}_0.db3"
    database_path = recording / database_name
    create_rosbag_database(database_path)
    if damaged:
        data = database_path.read_bytes()
        database_path.write_bytes(data[:-4_096])
    document = metadata_document(database_name)
    if metadata_overrides:
        document["rosbag2_bagfile_information"].update(metadata_overrides)
    (recording / "metadata.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    if include_video:
        (recording / f"{name}.avi").write_bytes(b"synthetic video placeholder")
    if include_csv:
        (recording / f"{name}.csv").write_text(
            "unix_timestamp,human_timestamp\n", encoding="utf-8"
        )
    return recording


def inventory(root: Path) -> tuple[tuple[str, str, int, int], ...]:
    entries: list[tuple[str, str, int, int]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and is_reserved_cache_root_entry(relative.parts[0]):
            continue
        details = path.lstat()
        kind = "symlink" if path.is_symlink() else "dir" if path.is_dir() else "file"
        entries.append(
            (path.relative_to(root).as_posix(), kind, details.st_size, details.st_mtime_ns)
        )
    return tuple(entries)
