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
    """The configured schema is not the accepted application schema."""


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
    ("artifacts", "id", "bigint", "NO", "YES"),
    ("artifacts", "recording_id", "bigint", "NO", "NO"),
    ("artifacts", "kind", "text", "NO", "NO"),
    ("artifacts", "cache_identity", "text", "NO", "NO"),
    ("artifacts", "output_relative_path", "text", "NO", "NO"),
    ("artifacts", "mime_type", "text", "NO", "NO"),
    ("artifacts", "size_bytes", "bigint", "NO", "NO"),
    ("artifacts", "coverage_start_ns", "bigint", "NO", "NO"),
    ("artifacts", "coverage_end_ns", "bigint", "NO", "NO"),
    ("artifacts", "manifest", "jsonb", "NO", "NO"),
    (
        "artifacts",
        "created_at",
        "timestamp with time zone",
        "NO",
        "NO",
    ),
    ("jobs", "id", "bigint", "NO", "YES"),
    ("jobs", "recording_id", "bigint", "NO", "NO"),
    ("jobs", "kind", "text", "NO", "NO"),
    ("jobs", "cache_identity", "text", "NO", "NO"),
    ("jobs", "state", "text", "NO", "NO"),
    ("jobs", "queued_at", "timestamp with time zone", "NO", "NO"),
    ("jobs", "started_at", "timestamp with time zone", "YES", "NO"),
    ("jobs", "finished_at", "timestamp with time zone", "YES", "NO"),
    ("jobs", "error_code", "text", "YES", "NO"),
    ("jobs", "error_message", "text", "YES", "NO"),
}

EXPECTED_CATALOG_DEFAULTS = {
    ("recordings", "created_at", "CURRENT_TIMESTAMP"),
    ("recordings", "updated_at", "CURRENT_TIMESTAMP"),
    ("source_components", "created_at", "CURRENT_TIMESTAMP"),
    ("source_components", "updated_at", "CURRENT_TIMESTAMP"),
    ("artifacts", "created_at", "CURRENT_TIMESTAMP"),
    ("jobs", "queued_at", "CURRENT_TIMESTAMP"),
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
    (
        "artifacts",
        "id",
        "BY DEFAULT",
        "1",
        "1",
        "1",
        "9223372036854775807",
        "NO",
    ),
    (
        "jobs",
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
    ("artifacts", "p", "PRIMARY KEY (id)"),
    (
        "artifacts",
        "f",
        "FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE",
    ),
    ("artifacts", "c", "CHECK (kind = 'front_preview')"),
    ("artifacts", "c", "CHECK (char_length(cache_identity) = 64)"),
    ("artifacts", "c", "CHECK (output_relative_path <> '')"),
    ("artifacts", "c", "CHECK (mime_type <> '')"),
    ("artifacts", "c", "CHECK (size_bytes > 0)"),
    (
        "artifacts",
        "c",
        "CHECK (jsonb_typeof(manifest) = 'object')",
    ),
    (
        "artifacts",
        "u",
        "UNIQUE (kind, cache_identity)",
    ),
    (
        "artifacts",
        "c",
        "CHECK (coverage_end_ns >= coverage_start_ns)",
    ),
    ("jobs", "p", "PRIMARY KEY (id)"),
    (
        "jobs",
        "f",
        "FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE",
    ),
    ("jobs", "c", "CHECK (kind = 'front_preview')"),
    ("jobs", "c", "CHECK (char_length(cache_identity) = 64)"),
    (
        "jobs",
        "c",
        "CHECK (state = ANY (ARRAY['queued', 'running', 'succeeded', 'failed']))",
    ),
    (
        "jobs",
        "c",
        "CHECK (error_message IS NULL OR char_length(error_message) <= 500)",
    ),
    (
        "jobs",
        "c",
        "CHECK (state = 'queued' AND started_at IS NULL AND finished_at IS NULL "
        "OR state = 'running' AND started_at IS NOT NULL AND finished_at IS NULL "
        "OR (state = ANY (ARRAY['succeeded', 'failed'])) AND started_at IS NOT NULL "
        "AND finished_at IS NOT NULL)",
    ),
    (
        "jobs",
        "c",
        "CHECK (state = 'failed' AND error_code IS NOT NULL AND error_message IS NOT "
        "NULL OR state <> 'failed' AND error_code IS NULL AND error_message IS NULL)",
    ),
}

EXPECTED_PROCESSING_INDEXES = {
    (
        "jobs_one_active_identity",
        "jobs",
        True,
        True,
        ("kind", "cache_identity"),
        "state = ANY (ARRAY['queued', 'running'])",
    ),
    (
        "jobs_queue_order",
        "jobs",
        False,
        True,
        ("queued_at", "id"),
        "state = 'queued'",
    ),
}
EXPECTED_TABLES = ("recordings", "source_components", "artifacts", "jobs")


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
    migration_root = resources.files("rosbag_analyser.persistence.migrations")
    migrations = tuple(
        item.read_text(encoding="utf-8")
        for item in sorted(migration_root.iterdir(), key=lambda entry: entry.name)
        if item.name.endswith(".sql")
    )
    with open_connection(database_url) as connection:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            ("rosbag_analyser_catalog_migration",),
        )
        for migration in migrations:
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
          AND table_name = ANY (%s)
        """,
        (list(EXPECTED_TABLES),),
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
               constraint_info.contype AS constraint_type,
               pg_get_constraintdef(constraint_info.oid, true) AS constraint_definition
        FROM pg_catalog.pg_constraint AS constraint_info
        JOIN pg_catalog.pg_class AS relation
          ON relation.oid = constraint_info.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND relation.relname = ANY (%s)
          AND constraint_info.contype IN ('c', 'f', 'p', 'u')
        """,
        (list(EXPECTED_TABLES),),
    ).fetchall()
    actual_constraints = {
        (
            str(row["table_name"]),
            str(row["constraint_type"]),
            _normalize_constraint_definition(str(row["constraint_definition"])),
        )
        for row in constraint_rows
    }

    index_rows = connection.execute(
        """
        SELECT index_relation.relname AS index_name,
               table_relation.relname AS table_name,
               index_info.indisunique, index_info.indisvalid,
               ARRAY(
                   SELECT pg_get_indexdef(index_info.indexrelid, position, true)
                   FROM generate_series(1, index_info.indnkeyatts) AS position
                   ORDER BY position
               ) AS key_columns,
               pg_get_expr(index_info.indpred, index_info.indrelid, true) AS predicate
        FROM pg_catalog.pg_index AS index_info
        JOIN pg_catalog.pg_class AS index_relation
          ON index_relation.oid = index_info.indexrelid
        JOIN pg_catalog.pg_class AS table_relation
          ON table_relation.oid = index_info.indrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = table_relation.relnamespace
        WHERE namespace.nspname = current_schema()
          AND index_relation.relname = ANY (%s)
        """,
        ([index[0] for index in EXPECTED_PROCESSING_INDEXES],),
    ).fetchall()
    actual_processing_indexes = {
        (
            str(row["index_name"]),
            str(row["table_name"]),
            bool(row["indisunique"]),
            bool(row["indisvalid"]),
            tuple(str(column) for column in row["key_columns"]),
            _normalize_constraint_definition(str(row["predicate"])),
        )
        for row in index_rows
    }

    if (
        actual_columns != EXPECTED_CATALOG_COLUMNS
        or actual_defaults != EXPECTED_CATALOG_DEFAULTS
        or actual_identities != EXPECTED_CATALOG_IDENTITIES
        or actual_constraints != EXPECTED_CATALOG_CONSTRAINTS
        or actual_processing_indexes != EXPECTED_PROCESSING_INDEXES
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
    normalized = _strip_redundant_outer_parentheses(" ".join(protected.split()))
    for index, literal in enumerate(literals):
        normalized = normalized.replace(f"\x00literal_{index}\x00", literal)
    return normalized


def _strip_redundant_outer_parentheses(definition: str) -> str:
    normalized = definition
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        wraps_entire_definition = True
        for index, character in enumerate(normalized):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(normalized) - 1:
                    wraps_entire_definition = False
                    break
                if depth < 0:
                    wraps_entire_definition = False
                    break
        if not wraps_entire_definition or depth != 0:
            break
        normalized = normalized[1:-1].strip()
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
