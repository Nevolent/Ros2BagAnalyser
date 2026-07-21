from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from conftest import metadata_document
from rosbag_analyser.catalog.metadata import (
    MAX_METADATA_BYTES,
    MAX_YAML_DEPTH,
    MAX_YAML_NODES,
    MetadataError,
    POSTGRES_BIGINT_MAX,
    POSTGRES_INTEGER_MAX,
    parse_metadata_file,
)


def test_parses_known_humble_metadata_shape(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    path.write_text(
        yaml.safe_dump(metadata_document(), sort_keys=False), encoding="utf-8"
    )

    parsed = parse_metadata_file(path)

    assert parsed.version == 5
    assert parsed.storage_identifier == "sqlite3"
    assert parsed.duration_ns == 2_500_000_000
    assert parsed.start_time_ns == 1_700_000_000_000_000_000
    assert parsed.message_count == 42
    assert parsed.topic_count == 1
    assert parsed.relative_file_paths == ("recording_0.db3",)
    assert parsed.support_diagnostic() is None


def test_reports_unsupported_split_layout(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    document = metadata_document(relative_file_paths=["one.db3", "two.db3"])
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    parsed = parse_metadata_file(path)

    assert parsed.support_diagnostic().code == "split_bag_unsupported"


def test_rejects_oversized_metadata_before_yaml_parse(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    path.write_bytes(b"x" * (MAX_METADATA_BYTES + 1))

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_too_large"


def test_rejects_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    path.write_text("root: [unterminated", encoding="utf-8")

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_yaml_invalid"


def test_rejects_yaml_deeper_than_the_parser_limit(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    nested = "value"
    for _ in range(MAX_YAML_DEPTH + 2):
        nested = f"[{nested}]"
    path.write_text(f"root: {nested}\n", encoding="utf-8")

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_yaml_invalid"


def test_rejects_yaml_with_too_many_nodes(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    values = ",".join("0" for _ in range(MAX_YAML_NODES + 1))
    path.write_text(f"root: [{values}]\n", encoding="utf-8")

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_yaml_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", POSTGRES_INTEGER_MAX + 1),
        ("message_count", POSTGRES_BIGINT_MAX + 1),
    ],
)
def test_rejects_values_outside_catalog_storage_range(
    tmp_path: Path, field: str, value: int
) -> None:
    path = tmp_path / "metadata.yaml"
    document = metadata_document()
    document["rosbag2_bagfile_information"][field] = value
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_value_invalid"


def test_rejects_surrogate_text_values(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    text = yaml.safe_dump(metadata_document(), sort_keys=False)
    path.write_text(
        text.replace("storage_identifier: sqlite3", 'storage_identifier: "\\uDCFF"'),
        encoding="utf-8",
    )

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_value_invalid"


def test_rejects_nul_text_values(tmp_path: Path) -> None:
    path = tmp_path / "metadata.yaml"
    document = metadata_document(storage_identifier="sqlite3\x00")
    path.write_text(yaml.safe_dump(document), encoding="utf-8")

    with pytest.raises(MetadataError) as captured:
        parse_metadata_file(path)

    assert captured.value.diagnostic.code == "metadata_value_invalid"
