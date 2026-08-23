from __future__ import annotations

import logging
import sys

from rosbag_analyser.safe_logging import SanitizingFormatter, sanitize_log_text


def test_log_sanitizer_removes_paths_database_urls_and_secret_fields() -> None:
    source = (
        "failed /srv/private/archive/run/metadata.yaml "
        "postgresql://user:password@private/db password=hunter2"
    )

    sanitized = sanitize_log_text(source)

    assert "/srv/private" not in sanitized
    assert "postgresql://" not in sanitized
    assert "hunter2" not in sanitized
    assert "[path]" in sanitized
    assert "[database-url]" in sanitized


def test_formatter_sanitizes_exception_traceback() -> None:
    try:
        raise RuntimeError("source unavailable at /private/source/recording.db3")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "operation failed",
            (),
            sys.exc_info(),
        )

    rendered = SanitizingFormatter("%(message)s").format(record)

    assert "/private/source" not in rendered
    assert "RuntimeError" in rendered
