from __future__ import annotations

from typing import Any

import pytest

from rosbag_analyser.persistence import database


def test_open_connection_applies_catalog_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_connect(database_url: str, **kwargs: object) -> object:
        captured["database_url"] = database_url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(database.psycopg, "connect", fake_connect)

    connection = database.open_connection("postgresql:///catalog")

    assert connection is sentinel
    assert captured["connect_timeout"] == database.DATABASE_CONNECT_TIMEOUT_SECONDS
    assert "statement_timeout=10000" in str(captured["options"])
    assert "lock_timeout=5000" in str(captured["options"])


class _QueryResult:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = [] if rows is None else rows

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


def _valid_column_rows() -> list[dict[str, object]]:
    defaults = {
        (table_name, column_name): column_default
        for table_name, column_name, column_default in (
            database.EXPECTED_CATALOG_DEFAULTS
        )
    }
    identities = {
        (table_name, column_name): identity_values
        for (
            table_name,
            column_name,
            *identity_values,
        ) in database.EXPECTED_CATALOG_IDENTITIES
    }
    rows: list[dict[str, object]] = []
    for table_name, column_name, data_type, is_nullable, is_identity in (
        database.EXPECTED_CATALOG_COLUMNS
    ):
        identity = identities.get((table_name, column_name), [None] * 6)
        rows.append(
            {
                "table_name": table_name,
                "column_name": column_name,
                "data_type": data_type,
                "is_nullable": is_nullable,
                "is_identity": is_identity,
                "column_default": defaults.get((table_name, column_name)),
                "identity_generation": identity[0],
                "identity_start": identity[1],
                "identity_increment": identity[2],
                "identity_minimum": identity[3],
                "identity_maximum": identity[4],
                "identity_cycle": identity[5],
            }
        )
    return rows


def _valid_constraint_rows() -> list[dict[str, object]]:
    return [
        {
            "table_name": table_name,
            "constraint_type": constraint_type,
            "constraint_definition": definition,
        }
        for table_name, constraint_type, definition in (
            database.EXPECTED_CATALOG_CONSTRAINTS
        )
    ]


def _valid_index_rows() -> list[dict[str, object]]:
    return [
        {
            "index_name": index_name,
            "table_name": table_name,
            "indisunique": is_unique,
            "indisvalid": is_valid,
            "key_columns": list(key_columns),
            "predicate": predicate,
        }
        for (
            index_name,
            table_name,
            is_unique,
            is_valid,
            key_columns,
            predicate,
        ) in database.EXPECTED_PROCESSING_INDEXES
    ]


class _SchemaConnection:
    def __init__(
        self,
        column_rows: list[dict[str, object]],
        constraint_rows: list[dict[str, object]],
        index_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.column_rows = column_rows
        self.constraint_rows = constraint_rows
        self.index_rows = _valid_index_rows() if index_rows is None else index_rows

    def execute(self, statement: str, parameters: object = None) -> _QueryResult:
        if "information_schema.columns" in statement:
            return _QueryResult(self.column_rows)
        if "pg_catalog.pg_index" in statement:
            return _QueryResult(self.index_rows)
        return _QueryResult(self.constraint_rows)


class _IncompatibleSchemaConnection:
    def __enter__(self) -> "_IncompatibleSchemaConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> _QueryResult:
        return _QueryResult()


def test_migration_rejects_incompatible_existing_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _IncompatibleSchemaConnection()
    monkeypatch.setattr(database, "open_connection", lambda database_url: connection)

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database.apply_catalog_migration("postgresql:///catalog")


def test_schema_validation_accepts_exact_catalog_contract() -> None:
    connection = _SchemaConnection(_valid_column_rows(), _valid_constraint_rows())

    database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_rejects_missing_timestamp_default() -> None:
    rows = _valid_column_rows()
    created_at = next(
        row
        for row in rows
        if row["table_name"] == "recordings" and row["column_name"] == "created_at"
    )
    created_at["column_default"] = None
    connection = _SchemaConnection(rows, _valid_constraint_rows())

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_rejects_nonpositive_identity_options() -> None:
    rows = _valid_column_rows()
    recording_id = next(
        row
        for row in rows
        if row["table_name"] == "recordings" and row["column_name"] == "id"
    )
    recording_id["identity_start"] = "0"
    recording_id["identity_minimum"] = "0"
    connection = _SchemaConnection(rows, _valid_constraint_rows())

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_rejects_same_count_wrong_constraint() -> None:
    rows = _valid_constraint_rows()
    check = next(
        row
        for row in rows
        if row["table_name"] == "recordings" and row["constraint_type"] == "c"
    )
    check["constraint_definition"] = "CHECK (true)"
    connection = _SchemaConnection(_valid_column_rows(), rows)

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_rejects_missing_processing_index() -> None:
    connection = _SchemaConnection(
        _valid_column_rows(),
        _valid_constraint_rows(),
        index_rows=_valid_index_rows()[:-1],
    )

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_rejects_same_name_wrong_processing_index() -> None:
    rows = _valid_index_rows()
    rows[0]["key_columns"] = ["cache_identity", "kind"]
    connection = _SchemaConnection(
        _valid_column_rows(),
        _valid_constraint_rows(),
        index_rows=rows,
    )

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_constraint_normalization_accepts_inferred_literal_casts() -> None:
    reconstructed = (
        "CHECK (ros_health = ANY (ARRAY['readable'::text, 'damaged'::text, "
        "'missing'::text, 'unsupported'::text, "
        "'uninspectable'::text]::text[]))"
    )
    expected = (
        "CHECK (ros_health = ANY (ARRAY['readable', 'damaged', 'missing', "
        "'unsupported', 'uninspectable']))"
    )

    assert database._normalize_constraint_definition(reconstructed) == expected


def test_constraint_normalization_accepts_version_specific_predicate_wrapper() -> None:
    assert database._normalize_constraint_definition(
        "((state = 'queued'))"
    ) == "state = 'queued'"


def test_schema_validation_rejects_narrowing_column_cast() -> None:
    rows = _valid_constraint_rows()
    duration_check = next(
        row
        for row in rows
        if row["constraint_definition"]
        == "CHECK (duration_ns IS NULL OR duration_ns >= 0)"
    )
    duration_check["constraint_definition"] = (
        "CHECK (duration_ns IS NULL OR duration_ns::integer >= 0::integer)"
    )
    connection = _SchemaConnection(_valid_column_rows(), rows)

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]


def test_schema_validation_preserves_cast_text_inside_literal() -> None:
    rows = _valid_constraint_rows()
    health_check = next(
        row
        for row in rows
        if str(row["constraint_definition"]).startswith("CHECK (ros_health")
    )
    health_check["constraint_definition"] = str(
        health_check["constraint_definition"]
    ).replace("'readable'", "'readable::text'")
    connection = _SchemaConnection(_valid_column_rows(), rows)

    with pytest.raises(database.CatalogSchemaError, match="incompatible"):
        database._validate_catalog_schema(connection)  # type: ignore[arg-type]
