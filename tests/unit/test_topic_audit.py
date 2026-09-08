from __future__ import annotations

from pathlib import Path
import sqlite3
import subprocess
import sys

from rosbag_analyser.topic_audit import audit_recording_topics


def _metadata(database_name: str) -> str:
    return f"""rosbag2_bagfile_information:
  version: 5
  storage_identifier: sqlite3
  duration: {{nanoseconds: 100}}
  starting_time: {{nanoseconds_since_epoch: 1000}}
  message_count: 7
  topics_with_message_count:
    - topic_metadata: {{name: /different/front, type: sensor_msgs/msg/Image, serialization_format: cdr}}
      message_count: 5
    - topic_metadata: {{name: /configured/imu, type: sensor_msgs/msg/Imu, serialization_format: cdr}}
      message_count: 2
  relative_file_paths: [{database_name}]
  compression_format: ''
  compression_mode: ''
"""


def _recording(tmp_path: Path, topics: list[tuple[int, str, str, str]]) -> tuple[Path, Path]:
    archive = tmp_path / "archive"
    recording = archive / "folder" / "bag-one"
    recording.mkdir(parents=True)
    database = recording / "bag.db3"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE topics (id INTEGER PRIMARY KEY, name TEXT, type TEXT, serialization_format TEXT)")
        connection.executemany("INSERT INTO topics VALUES (?, ?, ?, ?)", topics)
        connection.commit()
    finally:
        connection.close()
    (recording / "metadata.yaml").write_text(_metadata(database.name), encoding="utf-8")
    return archive, recording


def test_audit_reports_matches_candidates_and_preserves_source(tmp_path: Path) -> None:
    archive, recording = _recording(tmp_path, [
        (1, "/different/front", "sensor_msgs/msg/Image", "cdr"),
        (2, "/configured/imu", "sensor_msgs/msg/Imu", "cdr"),
    ])
    before = {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in recording.iterdir()}

    report = audit_recording_topics(archive, "folder/bag-one", front_topic="/configured/front", imu_topic="/configured/imu")

    configured = report["configured"]
    assert configured["front"]["usable"] is False
    assert configured["imu"]["usable"] is True
    assert [item["name"] for item in report["candidate_front_topics"]] == ["/different/front"]
    assert {path.name: (path.stat().st_size, path.stat().st_mtime_ns) for path in recording.iterdir()} == before
    assert not (recording / "bag.db3-journal").exists()
    assert not (recording / "bag.db3-wal").exists()
    assert not (recording / "bag.db3-shm").exists()


def test_audit_exposes_metadata_database_disagreement(tmp_path: Path) -> None:
    archive, _ = _recording(tmp_path, [
        (1, "/configured/front", "sensor_msgs/msg/Image", "cdr"),
        (2, "/configured/imu", "example/Other", "cdr"),
    ])

    report = audit_recording_topics(archive, "folder/bag-one", front_topic="/configured/front", imu_topic="/configured/imu")

    configured = report["configured"]
    assert configured["front"]["metadata_match"] is None
    assert configured["front"]["database_match"]["type"] == "sensor_msgs/msg/Image"
    assert configured["imu"]["usable"] is False


def test_all_mode_writes_one_json_line_per_recording_and_summary(tmp_path: Path) -> None:
    archive, _ = _recording(tmp_path, [
        (1, "/different/front", "sensor_msgs/msg/Image", "cdr"),
        (2, "/configured/imu", "sensor_msgs/msg/Imu", "cdr"),
    ])
    repository = Path(__file__).parents[2]

    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "deploy/scripts/topic_audit.py"),
            "--archive-root",
            str(archive),
            "--all",
            "--front-topic",
            "/configured/front",
            "--imu-topic",
            "/configured/imu",
        ],
        cwd=repository,
        env={"PYTHONPATH": str(repository / "src")},
        check=True,
        capture_output=True,
        text=True,
    )

    lines = completed.stdout.splitlines()
    assert len(lines) == 2
    assert '"recording_path": "folder/bag-one"' in lines[0]
    assert '"record_type": "summary"' in lines[1]
    assert '"recording_count": 1' in lines[1]
