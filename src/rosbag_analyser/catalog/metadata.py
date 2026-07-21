from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
from typing import Any

import yaml
from yaml.events import AliasEvent

from .limits import POSTGRES_BIGINT_MAX, POSTGRES_INTEGER_MAX, is_postgres_text
from .paths import SourceFileIdentity, source_file_identity
from .types import SafeDiagnostic


MAX_METADATA_BYTES = 1_048_576
MAX_YAML_ALIASES = 100
MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 10_000


class MetadataError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.diagnostic = SafeDiagnostic(code=code, message=message)


class LimitedSafeLoader(yaml.SafeLoader):
    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._alias_count = 0
        self._depth = 0
        self._node_count = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        self._depth += 1
        self._node_count += 1
        try:
            if self._depth > MAX_YAML_DEPTH:
                raise yaml.YAMLError("YAML nesting limit exceeded")
            if self._node_count > MAX_YAML_NODES:
                raise yaml.YAMLError("YAML node limit exceeded")
            if self.check_event(AliasEvent):
                self._alias_count += 1
                if self._alias_count > MAX_YAML_ALIASES:
                    raise yaml.YAMLError("YAML alias limit exceeded")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


@dataclass(frozen=True)
class TopicFact:
    name: str
    message_type: str
    serialization_format: str
    message_count: int


@dataclass(frozen=True)
class ParsedMetadata:
    version: int
    storage_identifier: str
    duration_ns: int
    start_time_ns: int
    message_count: int
    topics: tuple[TopicFact, ...]
    relative_file_paths: tuple[str, ...]
    compression_format: str
    compression_mode: str

    @property
    def topic_count(self) -> int:
        return len(self.topics)

    def support_diagnostic(self) -> SafeDiagnostic | None:
        if self.version != 5:
            return SafeDiagnostic(
                "metadata_version_unsupported",
                "This recording uses an unsupported metadata version.",
            )
        if self.storage_identifier != "sqlite3":
            return SafeDiagnostic(
                "storage_format_unsupported",
                "This recording uses an unsupported ROS storage format.",
            )
        if self.compression_format or self.compression_mode:
            return SafeDiagnostic(
                "compressed_bag_unsupported",
                "Compressed ROS bags are not supported in V0.",
            )
        if len(self.relative_file_paths) != 1:
            return SafeDiagnostic(
                "split_bag_unsupported",
                "Split ROS bags are not supported in V0.",
            )
        return None


def parse_metadata_file(
    path: Path, *, expected_identity: SourceFileIdentity | None = None
) -> ParsedMetadata:
    raw = _read_bounded_regular_file(path, expected_identity=expected_identity)
    try:
        document = yaml.load(raw, Loader=LimitedSafeLoader)
    except (yaml.YAMLError, RecursionError) as error:
        raise MetadataError(
            "metadata_yaml_invalid", "The recording metadata is not valid YAML."
        ) from error

    root = _mapping(document, "metadata_root_invalid")
    information = _mapping(
        root.get("rosbag2_bagfile_information"), "metadata_information_missing"
    )

    version = _integer(
        information,
        "version",
        nonnegative=True,
        maximum=POSTGRES_INTEGER_MAX,
    )
    storage_identifier = _string(information, "storage_identifier")
    duration = _mapping(information.get("duration"), "metadata_duration_invalid")
    duration_ns = _integer(
        duration,
        "nanoseconds",
        nonnegative=True,
        maximum=POSTGRES_BIGINT_MAX,
    )
    starting_time = _mapping(
        information.get("starting_time"), "metadata_start_time_invalid"
    )
    start_time_ns = _integer(
        starting_time,
        "nanoseconds_since_epoch",
        nonnegative=True,
        maximum=POSTGRES_BIGINT_MAX,
    )
    message_count = _integer(
        information,
        "message_count",
        nonnegative=True,
        maximum=POSTGRES_BIGINT_MAX,
    )
    compression_format = _optional_string(information, "compression_format")
    compression_mode = _optional_string(information, "compression_mode")

    raw_paths = information.get("relative_file_paths")
    if not isinstance(raw_paths, list) or not all(
        isinstance(item, str) and item and is_postgres_text(item) for item in raw_paths
    ):
        raise MetadataError(
            "metadata_source_paths_invalid",
            "The metadata source-file list is invalid.",
        )

    raw_topics = information.get("topics_with_message_count")
    if not isinstance(raw_topics, list):
        raise MetadataError(
            "metadata_topics_invalid", "The metadata topic list is invalid."
        )
    topics = tuple(_parse_topic(item) for item in raw_topics)

    return ParsedMetadata(
        version=version,
        storage_identifier=storage_identifier,
        duration_ns=duration_ns,
        start_time_ns=start_time_ns,
        message_count=message_count,
        topics=topics,
        relative_file_paths=tuple(raw_paths),
        compression_format=compression_format,
        compression_mode=compression_mode,
    )


def _read_bounded_regular_file(
    path: Path, *, expected_identity: SourceFileIdentity | None
) -> bytes:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise MetadataError(
            "metadata_unreadable", "The recording metadata could not be read."
        ) from error

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise MetadataError(
                "metadata_not_regular_file",
                "The recording metadata is not a regular file.",
            )
        before_identity = source_file_identity(before)
        if expected_identity is not None and before_identity != expected_identity:
            raise MetadataError(
                "metadata_changed_during_scan",
                "The recording metadata changed during the scan.",
            )
        if before.st_size > MAX_METADATA_BYTES:
            raise MetadataError(
                "metadata_too_large",
                "The recording metadata exceeds the V0 size limit.",
            )
        chunks: list[bytes] = []
        remaining = MAX_METADATA_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    if len(raw) > MAX_METADATA_BYTES:
        raise MetadataError(
            "metadata_too_large", "The recording metadata exceeds the V0 size limit."
        )
    if before_identity != source_file_identity(after):
        raise MetadataError(
            "metadata_changed_during_scan",
            "The recording metadata changed during the scan.",
        )
    return raw


def _parse_topic(value: object) -> TopicFact:
    item = _mapping(value, "metadata_topic_invalid")
    topic_metadata = _mapping(
        item.get("topic_metadata"), "metadata_topic_definition_invalid"
    )
    return TopicFact(
        name=_string(topic_metadata, "name"),
        message_type=_string(topic_metadata, "type"),
        serialization_format=_string(topic_metadata, "serialization_format"),
        message_count=_integer(
            item,
            "message_count",
            nonnegative=True,
            maximum=POSTGRES_BIGINT_MAX,
        ),
    )


def _mapping(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MetadataError(code, "The recording metadata structure is invalid.")
    return value


def _integer(
    mapping: dict[str, Any],
    name: str,
    *,
    nonnegative: bool,
    maximum: int | None = None,
) -> int:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetadataError(
            "metadata_value_invalid", f"Metadata field {name} must be an integer."
        )
    if nonnegative and value < 0:
        raise MetadataError(
            "metadata_value_invalid", f"Metadata field {name} must not be negative."
        )
    if maximum is not None and value > maximum:
        raise MetadataError(
            "metadata_value_invalid",
            f"Metadata field {name} exceeds the supported range.",
        )
    return value


def _string(mapping: dict[str, Any], name: str) -> str:
    value = mapping.get(name)
    if not isinstance(value, str) or not value or not is_postgres_text(value):
        raise MetadataError(
            "metadata_value_invalid", f"Metadata field {name} must be text."
        )
    return value


def _optional_string(mapping: dict[str, Any], name: str) -> str:
    value = mapping.get(name, "")
    if value is None:
        return ""
    if not isinstance(value, str) or not is_postgres_text(value):
        raise MetadataError(
            "metadata_value_invalid", f"Metadata field {name} must be text."
        )
    return value
