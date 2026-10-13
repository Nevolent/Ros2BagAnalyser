"""Sort message headers before reading bounded payloads from immutable bags."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager


@contextmanager
def ordered_topic_messages(connection, topic_id, max_payload_bytes, *, control=None):
    # The usual timestamp-only index makes SQLite visit every topic's table
    # pages in timestamp order. +timestamp permits a topic index, but prevents
    # that expensive ordering-index scan. The non-flattenable subquery sorts
    # only IDs, timestamps and lengths; blobs never enter SQLite's sort buffer.
    # Its single outer projection preserves that order and fetches selected
    # payloads by primary key only when the consumer advances the cursor.
    control_error = None

    def checkpoint():
        nonlocal control_error
        try:
            control.checkpoint("processing")
        except BaseException as error:
            # sqlite3 turns callback exceptions into SQLITE_INTERRUPT. Restore
            # cancellation/control errors outside the callback instead.
            control_error = error
            return 1
        return 0

    if control is not None:
        connection.set_progress_handler(checkpoint, 10000)
    try:
        cursor = connection.execute(
            """
            SELECT selected.timestamp, selected.size,
                   (SELECT CASE WHEN selected.size BETWEEN 1 AND ?
                                THEN data ELSE NULL END
                    FROM messages WHERE id = selected.id)
            FROM (
                SELECT id, timestamp, length(data) AS size
                FROM messages WHERE topic_id = ?
                ORDER BY +timestamp, id LIMIT -1 OFFSET 0
            ) AS selected
            """,
            (max_payload_bytes, topic_id),
        )
        try:
            yield cursor
        finally:
            cursor.close()
    except sqlite3.Error:
        if control_error is not None:
            raise control_error
        raise
    finally:
        if control is not None:
            connection.set_progress_handler(None, 0)
