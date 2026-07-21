from __future__ import annotations

from importlib import resources
import re

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row


DATABASE_CONNECT_TIMEOUT_SECONDS = 5
DATABASE_STATEMENT_TIMEOUT_MS = 10_000
DATABASE_LOCK_TIMEOUT_MS = 5_000


class CatalogSchemaError(RuntimeError):
    """The configured schema is not the Building block 1 catalog schema."""


EXPECTED_CATALOG_COLUMNS = {
    ("recordings", "id", "bigint", "NO", "YES"),
    ("recordings", "archive_relative_path", "text", "NO", "NO"),
    ("recordings", "display_name", "text", "NO", "NO"),
    ("recordings", "start_time_ns", "bigint", "YES", "NO"),
    ("recordings", "duration_ns", "bigint", "YES", "NO"),
    ("recordings", "total_source_size_bytes", "bigint", "YES", "NO"),
    ("recordings", "storage_format", "text", "YES", "NO"),
    ("recordings", "metadata_version", "integer", "YES", "NO"),
    ("recordings", "message_count", "bigint", "YES", "NO"),
    ("recordings", "topic_count", "integer", "YES", "NO"),
    ("recordings", "ros_health", "text", "NO", "NO"),
    ("recordings", "diagnostic_code", "text", "YES", "NO"),
    ("recordings", "diagnostic_message", "text", "YES", "NO"),
    ("recordings", "source_revision", "text", "NO", "NO"),
    (
        "recordings",
        "created_at",
        "timestamp with time zone",
        "NO",
        "NO",
    ),
    (
        "recordings",
        "updated_at",
        "timestamp with time zone",
        "NO",
        "NO",
    ),
    ("source_components", "id", "bigint", "NO", "YES"),
    ("source_components", "recording_id", "bigint", "NO", "NO"),
    ("source_components", "role", "text", "NO", "NO"),
    ("source_components", "relative_path", "text", "YES", "NO"),
    ("source_components", "size_bytes", "bigint", "YES", "NO"),
    ("source_components", "mtime_ns", "bigint", "YES", "NO"),
    ("source_components", "condition", "text", "NO", "NO"),
    ("source_components", "diagnostic_code", "text", "YES", "NO"),
    ("source_components", "diagnostic_message", "text", "YES", "NO"),
    (
        "source_components",
        "created_at",
        "timestamp with time zone",
        "NO",
        "NO",
    ),
    (
        "source_components",
        "updated_at",
        "timestamp with time zone",
        "NO",
        "NO",
    ),
}

EXPECTED_CATALOG_DEFAULTS = {
    ("recordings", "created_at", "CURRENT_TIMESTAMP"),
    ("recordings", "updated_at", "CURRENT_TIMESTAMP"),
    ("source_components", "created_at", "CURRENT_TIMESTAMP"),
    ("source_components", "updated_at", "CURRENT_TIMESTAMP"),
}

EXPECTED_CATALOG_IDENTITIES = {
    (
        "recordings",
        "id",
        "BY DEFAULT",
        "1",
        "1",
        "1",
        "9223372036854775807",
        "NO",
    ),
    (
        "source_components",
        "id",
        "BY DEFAULT",
        "1",
        "1",
        "1",
        "9223372036854775807",
        "NO",
    ),
}

EXPECTED_CATALOG_CONSTRAINTS = {
    ("recordings", "p", "PRIMARY KEY (id)"),
    ("recordings", "u", "UNIQUE (archive_relative_path)"),
    (
        "recordings",
        "c",
        "CHECK (duration_ns IS NULL OR duration_ns >= 0)",
    ),
    (
        "recordings",
        "c",
        "CHECK (total_source_size_bytes IS NULL OR total_source_size_bytes >= 0)",
    ),
    (
        "recordings",
        "c",
        "CHECK (metadata_version IS NULL OR metadata_version >= 0)",
    ),
    (
        "recordings",
        "c",
        "CHECK (message_count IS NULL OR message_count >= 0)",
    ),
    (
        "recordings",
        "c",
        "CHECK (topic_count IS NULL OR topic_count >= 0)",
    ),
    (
        "recordings",
        "c",
        "CHECK (ros_health = ANY (ARRAY['readable', 'damaged', 'missing', "
        "'unsupported', 'uninspectable']))",
    ),
    (
        "recordings",
        "c",
        "CHECK (diagnostic_message IS NULL OR "
        "char_length(diagnostic_message) <= 500)",
    ),
    (
        "recordings",
        "c",
        "CHECK (char_length(source_revision) = 64)",
    ),
    ("recordings", "c", "CHECK (archive_relative_path <> '')"),
    ("recordings", "c", "CHECK (display_name <> '')"),
    ("source_components", "p", "PRIMARY KEY (id)"),
    (
        "source_components",
        "f",
        "FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE",
    ),
    (
        "source_components",
        "c",
        "CHECK (role = ANY (ARRAY['metadata', 'ros_database', 'topdown_video', "
        "'topdown_timestamps']))",
    ),
    (
        "source_components",
        "c",
        "CHECK (size_bytes IS NULL OR size_bytes >= 0)",
    ),
    (
        "source_components",
        "c",
        "CHECK (condition = ANY (ARRAY['present', 'readable', 'missing', "
        "'ambiguous', 'invalid', 'unsupported', 'damaged', 'uninspectable']))",
    ),
    (
        "source_components",
        "c",
        "CHECK (diagnostic_message IS NULL OR "
        "char_length(diagnostic_message) <= 500)",
    ),
    (
        "source_components",
        "u",
        "UNIQUE (recording_id, role)",
    ),
    (
        "source_components",
        "c",
        "CHECK (relative_path IS NULL OR relative_path <> '')",
    ),
}


def open_connection(database_url: str) -> Connection[dict[str, object]]:
    options = (
        f"-c statement_timeout={DATABASE_STATEMENT_TIMEOUT_MS} "
        f"-c lock_timeout={DATABASE_LOCK_TIMEOUT_MS}"
    )
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        options=options,
    )


def apply_catalog_migration(database_url: str) -> None:
    migration = (
        resources.files("rosbag_analyser.persistence.migrations")
        .joinpath("0001_catalog.sql")
        .read_text(encoding="utf-8")
    )
    with open_connection(database_url) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("rosbag_analyser_catalog_migration",),
        )
        connection.execute(migration)
        _validate_catalog_schema(connection)


def _validate_catalog_schema(connection: Connection[dict[str, object]]) -> None:
    column_rows = connection.execute(
        """
        SELECT table_name, column_name, data_type, is_nullable, is_identity,
               identity_generation, identity_start, identity_increment,
               identity_minimum, identity_maximum, identity_cycle, column_default
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name IN ('recordings', 'source_components')
        """
    ).fetchall()
    actual_columns = {
        (
            str(row["table_name"]),
            str(row["column_name"]),
            str(row["data_type"]),
            str(row["is_nullable"]),
            str(row["is_identity"]),
        )
        for row in column_rows
    }
    actual_defaults = {
        (
            str(row["table_name"]),
            str(row["column_name"]),
            _optional_text(row["column_default"]),
        )
        for row in column_rows
        if row["column_default"] is not None
    }
    actual_identities = {
        (
            str(row["table_name"]),
            str(row["column_name"]),
            str(row["identity_generation"]),
            _optional_text(row["identity_start"]),
            _optional_text(row["identity_increment"]),
            _optional_text(row["identity_minimum"]),
            _optional_text(row["identity_maximum"]),
            _optional_text(row["identity_cycle"]),
        )
        for row in column_rows
        if row["identity_generation"] is not None
    }

    constraint_rows = connection.execute(
        """
        SELECT relation.relname AS table_name,
               constraint.contype AS constraint_type,
               pg_get_constraintdef(constraint.oid, true) AS constraint_definition
        FROM pg_catalog.pg_constraint AS constraint
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND relation.relname IN ('recordings', 'source_components')
          AND constraint.contype IN ('c', 'f', 'p', 'u')
        """
    ).fetchall()
    actual_constraints = {
        (
            str(row["table_name"]),
            str(row["constraint_type"]),
            _normalize_constraint_definition(str(row["constraint_definition"])),
        )
        for row in constraint_rows
    }

    if (
        actual_columns != EXPECTED_CATALOG_COLUMNS
        or actual_defaults != EXPECTED_CATALOG_DEFAULTS
        or actual_identities != EXPECTED_CATALOG_IDENTITIES
        or actual_constraints != EXPECTED_CATALOG_CONSTRAINTS
    ):
        raise CatalogSchemaError(
            "The catalog database schema is incompatible with this application version."
        )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _normalize_constraint_definition(definition: str) -> str:
    protected, literals = _protect_sql_string_literals(definition)
    literal_marker = r"\x00literal_\d+\x00"

    # PostgreSQL may spell the inferred types of constants explicitly. Remove
    # only casts attached to constants, never casts on columns or text inside a
    # quoted literal.
    protected = re.sub(
        rf"({literal_marker})::text\b",
        r"\1",
        protected,
    )
    protected = re.sub(
        r"(?<![\w.])(-?\d+)::(?:bigint|integer)\b",
        r"\1",
        protected,
    )
    protected = re.sub(
        rf"(ARRAY\[\s*{literal_marker}"
        rf"(?:\s*,\s*{literal_marker})*\s*\])::text\[\]",
        r"\1",
        protected,
    )
    normalized = " ".join(protected.split())
    for index, literal in enumerate(literals):
        normalized = normalized.replace(f"\x00literal_{index}\x00", literal)
    return normalized


def _protect_sql_string_literals(definition: str) -> tuple[str, tuple[str, ...]]:
    protected: list[str] = []
    literals: list[str] = []
    index = 0
    while index < len(definition):
        if definition[index] != "'":
            protected.append(definition[index])
            index += 1
            continue

        start = index
        index += 1
        while index < len(definition):
            if definition[index] != "'":
                index += 1
                continue
            index += 1
            if index < len(definition) and definition[index] == "'":
                index += 1
                continue
            break
        literal = definition[start:index]
        marker = f"\x00literal_{len(literals)}\x00"
        literals.append(literal)
        protected.append(marker)
    return "".join(protected), tuple(literals)
