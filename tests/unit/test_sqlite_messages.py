import sqlite3
from types import SimpleNamespace

import pytest

from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.processors.sqlite_messages import ordered_topic_messages


@pytest.mark.parametrize("index", (None, "timestamp", "topic_id, timestamp"))
def test_selected_payloads_keep_timestamp_and_duplicate_order_and_size_limit(index):
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id, timestamp, data BLOB)")
        if index:
            connection.execute(f"CREATE INDEX source_idx ON messages({index})")
        connection.executemany("INSERT INTO messages VALUES (?, ?, ?, ?)", (
            (1, 1, 30, b"third"), (2, 1, 10, b"first"), (3, 2, 0, b"unselected"),
            (4, 1, 10, b"later"), (5, 1, 20, b"oversized"), (6, 1, 40, b""),
        ))
        with ordered_topic_messages(connection, 1, 5) as rows:
            assert list(rows) == [(10, 5, b"first"), (10, 5, b"later"),
                                  (20, 9, None), (30, 5, b"third"), (40, 0, None)]


def test_cancellation_interrupts_initial_header_sort_and_leaves_connection_usable():
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, topic_id, timestamp, data BLOB)")
        connection.executemany("INSERT INTO messages VALUES (?, 1, ?, X'01')",
                               ((index, 20000 - index) for index in range(20000)))
        def cancel(phase):
            assert phase == "processing"
            raise JobCanceled()
        with pytest.raises(JobCanceled):
            with ordered_topic_messages(connection, 1, 10, control=SimpleNamespace(checkpoint=cancel)):
                pytest.fail("Cancellation should happen before the first payload is returned.")
        assert connection.execute("SELECT count(*) FROM messages").fetchone() == (20000,)
