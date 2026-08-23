from __future__ import annotations

import logging
import re
import sys


DATABASE_URL = re.compile(r"postgresql(?:\+[A-Za-z0-9_.-]+)?://\S+", re.IGNORECASE)
SECRET_FIELD = re.compile(
    r"(?i)\b(authorization|cookie|password|secret|token|private[_ -]?key)"
    r"\s*[:=]\s*\S+"
)
ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_:.])/(?:[^\s:'\"<>]+/?)+")


def sanitize_log_text(value: str) -> str:
    sanitized = DATABASE_URL.sub("[database-url]", value)
    sanitized = SECRET_FIELD.sub(
        lambda match: f"{match.group(1)}=[redacted]", sanitized
    )
    return ABSOLUTE_PATH.sub("[path]", sanitized)


class SanitizingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return sanitize_log_text(super().format(record))


def configure_safe_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        SanitizingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


__all__ = ["SanitizingFormatter", "configure_safe_logging", "sanitize_log_text"]
