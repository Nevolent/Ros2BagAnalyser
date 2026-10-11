import sqlite3
from conftest import inventory
from rosbag_analyser.catalog.sqlite_health import probe_sqlite_database
from rosbag_analyser.catalog import timing

def database(path, messages):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE topics(id INTEGER PRIMARY KEY, name TEXT, type TEXT, serialization_format TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id INTEGER, timestamp INTEGER, data BLOB);
            CREATE INDEX timestamp_idx ON messages(timestamp);
            INSERT INTO topics VALUES(1, '/image', 'sensor_msgs/msg/Image', 'cdr');
            INSERT INTO topics VALUES(2, '/imu', 'sensor_msgs/msg/Imu', 'cdr');
        """)
        connection.executemany("INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,X'00')", messages)

def test_recording_pause_is_saved_with_location_and_source_is_unchanged(tmp_path):
    path = tmp_path / "recording.db3"
    timestamps = [n * 100_000_000 for n in range(50)] + [
        20_000_000_000 + n * 100_000_000 for n in range(50)]
    database(path, [(1, stamp) for stamp in timestamps])
    before = inventory(tmp_path)
    result = probe_sqlite_database(path)
    assert result.condition.value == "readable"
    assert result.timing["status"] == "complete"
    assert result.timing["gaps"] == [{
        "topic": None, "start_ns": "4900000000", "end_ns": "20000000000",
        "duration_ns": "15100000000",
    }]
    assert inventory(tmp_path) == before

def test_sensor_pause_is_found_even_when_other_messages_continue(tmp_path):
    path = tmp_path / "sensor.db3"
    messages = [(2, n * 100_000_000) for n in range(250)]
    messages += [(1, n * 100_000_000) for n in list(range(50)) + list(range(200, 250))]
    database(path, messages)
    result = probe_sqlite_database(path)
    assert result.timing["gaps"][0]["topic"] == "/image"
    assert result.timing["gaps"][0]["duration_ns"] == "15100000000"

def test_regular_slow_streams_and_duplicate_timestamps_are_not_missing_data(tmp_path):
    path = tmp_path / "slow.db3"
    database(path, [(1, n * 10_000_000_000) for n in range(50) for _ in range(2)])
    result = probe_sqlite_database(path)
    assert result.timing["status"] == "complete"
    assert result.timing["gaps"] == []

def test_row_budget_reports_partial_without_claiming_a_complete_check(tmp_path, monkeypatch):
    path = tmp_path / "limited.db3"
    database(path, [(1, n * 100_000_000) for n in range(100)])
    monkeypatch.setattr(timing, "MAX_MESSAGES", 30)
    result = probe_sqlite_database(path)
    assert result.timing["status"] == "partial"
    assert result.timing["messages_checked"] == 30

def test_no_timestamp_index_is_still_bounded_by_query_deadline(tmp_path, monkeypatch):
    path = tmp_path / "deadline.db3"
    database(path, [(1, n * 100_000_000) for n in range(1000)])
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX timestamp_idx")
    monkeypatch.setattr(timing, "MAX_SECONDS", 0)
    result = probe_sqlite_database(path)
    assert result.condition.value == "readable"
    assert result.timing["status"] == "partial"


def test_scan_saves_topics_and_bag_relative_review_without_blocking_processing(tmp_path):
    from conftest import create_recording
    from rosbag_analyser.catalog.scanner import CatalogScanner
    from rosbag_analyser.catalog.metadata import parse_metadata_file
    from rosbag_analyser.config import V0_PREVIEW_PROFILE
    from rosbag_analyser.preparation_planner import PreparationPlanner
    archive = tmp_path / "archive"
    archive.mkdir()
    recording = create_recording(archive, "run",
                                 metadata_overrides={"duration": {"nanoseconds": 30_000_000_000}})
    metadata = parse_metadata_file(recording / "metadata.yaml")
    source = next(recording.glob("*.db3"))
    stamps = [n * 100_000_000 for n in range(50)] + [20_000_000_000 + n * 100_000_000 for n in range(50)]
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO topics VALUES(1, '/camera/image_raw', 'sensor_msgs/msg/Image', 'cdr', '')")
        connection.executemany("INSERT INTO messages(topic_id,timestamp,data) VALUES(1,?,X'00')",
                               [(metadata.start_time_ns + 100_000_000 + stamp,) for stamp in stamps])
    before = inventory(archive)
    result = CatalogScanner(archive).scan().recordings[0]
    assert result.ros_health.value == "readable"
    assert result.diagnostic.code == "recording_time_gap"
    assert "near Unix time " in result.diagnostic.message
    assert "timestamps alone do not prove data loss" in result.diagnostic.message.lower()
    assert result.scan_details["topics"][0]["name"] == "/camera/image_raw"
    assert result.scan_details["timing"]["gaps"][0]["start_ns"] == "5000000000"
    planner = PreparationPlanner(front_topic="", imu_topic="", imu_component="angular_velocity.z",
                                 profile=V0_PREVIEW_PROFILE, encoder_identity="synthetic")
    assert planner.plan_recording(1, result)[0].target_state == "available"
    assert inventory(archive) == before


def test_sensor_scan_finds_short_late_pause_in_unordered_rows_using_covering_index(tmp_path):
    path = tmp_path / "late-gap.db3"
    # IMU keeps the recording active while the camera pauses for 2.5 seconds.
    stamps = [n * 10_000_000 for n in range(4000)]
    messages = [(2, stamp) for stamp in stamps]
    messages += [(1, stamp) for stamp in stamps if not 30_000_000_000 <= stamp < 32_500_000_000]
    database(path, reversed(messages))
    before = inventory(tmp_path)
    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT timestamp FROM messages ORDER BY timestamp LIMIT 2000001"
        ).fetchall()
        assert any("COVERING INDEX timestamp_idx" in row[3] for row in plan)
        result = timing.inspect_timing(connection)
    assert result["status"] == "complete"
    assert result["gaps"] == [{"topic": "/image", "start_ns": "29990000000",
                              "end_ns": "32500000000", "duration_ns": "2510000000"}]
    assert inventory(tmp_path) == before


def test_partial_sensor_evidence_survives_query_interruption(tmp_path):
    path = tmp_path / "interrupted.db3"
    database(path, [(1, n * 10_000_000) for n in range(50)])

    class InterruptedSensorConnection:
        def set_progress_handler(self, callback, interval):
            pass

        def execute(self, query, parameters):
            if "NOT INDEXED" not in query:
                return connection.execute(query, parameters)

            def rows():
                for n in range(50):
                    yield 1, n * 10_000_000
                yield 1, 6_500_000_000
                raise sqlite3.OperationalError("interrupted")
            return rows()

    with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as connection:
        result = timing.inspect_timing(InterruptedSensorConnection())
    assert result["status"] == "partial"
    assert result["gaps"][0]["topic"] == "/image"
    assert result["gaps"][0]["duration_ns"] == "6010000000"
