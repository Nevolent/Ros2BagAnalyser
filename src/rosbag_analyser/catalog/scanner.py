from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import time

from .limits import is_postgres_bigint, is_postgres_integer, is_postgres_text
from .metadata import MetadataError, ParsedMetadata, parse_metadata_file
from .paths import (
    DirectEntry,
    UnsafeSourcePath,
    archive_relative_path,
    discover_recording_directories,
    inventory_direct_entries,
    resolve_declared_source,
    safe_filesystem_text,
)
from .sqlite_health import SQLiteProbeResult, probe_sqlite_database
from .types import (
    RecordingScanResult,
    RootScanError,
    RosHealth,
    SafeDiagnostic,
    ScanSnapshot,
    SourceComponentResult,
    SourceCondition,
    SourceRole,
)


logger = logging.getLogger(__name__)


class CatalogScanner:
    """Describe an archive without writing to sources or persistence."""

    REVISION_VERSION = 2

    def __init__(self, archive_root: Path) -> None:
        self.archive_root = archive_root

    def scan(self) -> ScanSnapshot:
        started = time.monotonic_ns()
        recordings: list[RecordingScanResult] = []
        for recording_root in discover_recording_directories(self.archive_root):
            try:
                recordings.append(self._scan_recording(recording_root))
            except (OSError, UnsafeSourcePath) as error:
                diagnostic = _safe_path_diagnostic(error)
                recordings.append(
                    self._uninspectable_recording(recording_root, diagnostic)
                )
            except Exception:
                logger.exception(
                    "Unexpected failure while scanning recording %r.",
                    safe_filesystem_text(recording_root.name),
                )
                recordings.append(
                    self._uninspectable_recording(
                        recording_root,
                        SafeDiagnostic(
                            "recording_scan_failed",
                            "This recording could not be inspected safely.",
                        ),
                    )
                )
        elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
        return ScanSnapshot(recordings=tuple(recordings), duration_ms=elapsed_ms)

    def _scan_recording(self, recording_root: Path) -> RecordingScanResult:
        relative_recording = archive_relative_path(self.archive_root, recording_root)
        entries = inventory_direct_entries(recording_root)

        metadata_component, metadata = self._metadata_component(
            recording_root, entries
        )
        video_component = self._companion_component(
            entries, SourceRole.TOPDOWN_VIDEO, ".avi"
        )
        timestamp_component = self._companion_component(
            entries, SourceRole.TOPDOWN_TIMESTAMPS, ".csv"
        )
        database_component, database_probe = self._database_component(
            recording_root, metadata
        )
        components = (
            metadata_component,
            database_component,
            video_component,
            timestamp_component,
        )

        ros_health, diagnostic = _aggregate_ros_health(
            metadata_component, metadata, database_component
        )
        source_size = _complete_source_size(components)
        source_revision = _source_revision(
            relative_recording,
            metadata,
            components,
            database_probe,
            self.REVISION_VERSION,
        )
        result = RecordingScanResult(
            archive_relative_path=relative_recording,
            display_name=safe_filesystem_text(recording_root.name),
            start_time_ns=None if metadata is None else metadata.start_time_ns,
            duration_ns=None if metadata is None else metadata.duration_ns,
            total_source_size_bytes=source_size,
            storage_format=None if metadata is None else metadata.storage_identifier,
            metadata_version=None if metadata is None else metadata.version,
            message_count=None if metadata is None else metadata.message_count,
            topic_count=None if metadata is None else metadata.topic_count,
            ros_health=ros_health,
            diagnostic=diagnostic,
            source_revision=source_revision,
            components=components,
        )
        if not _is_catalog_persistable(result):
            return self._uninspectable_recording(
                recording_root,
                SafeDiagnostic(
                    "source_fact_out_of_range",
                    "This recording contains source facts outside the supported "
                    "catalog range.",
                ),
            )
        return result

    def _metadata_component(
        self, recording_root: Path, entries: tuple[DirectEntry, ...]
    ) -> tuple[SourceComponentResult, ParsedMetadata | None]:
        matches = [entry for entry in entries if entry.name == "metadata.yaml"]
        if not matches:
            return (
                SourceComponentResult(
                    role=SourceRole.METADATA,
                    condition=SourceCondition.MISSING,
                    diagnostic=SafeDiagnostic(
                        "metadata_missing", "The recording metadata is missing."
                    ),
                ),
                None,
            )
        entry = matches[0]
        relative = archive_relative_path(self.archive_root, entry.path)
        if entry.is_symlink or not entry.is_regular_file:
            return (
                SourceComponentResult(
                    role=SourceRole.METADATA,
                    condition=SourceCondition.INVALID,
                    relative_path=relative,
                    size_bytes=entry.size_bytes,
                    mtime_ns=entry.mtime_ns,
                    diagnostic=SafeDiagnostic(
                        "metadata_not_regular_file",
                        "The recording metadata is not a regular source file.",
                    ),
                ),
                None,
            )
        try:
            metadata = parse_metadata_file(
                entry.path,
                expected_identity=entry.identity,
            )
        except MetadataError as error:
            return (
                SourceComponentResult(
                    role=SourceRole.METADATA,
                    condition=SourceCondition.INVALID,
                    relative_path=relative,
                    size_bytes=entry.size_bytes,
                    mtime_ns=entry.mtime_ns,
                    diagnostic=error.diagnostic,
                ),
                None,
            )

        support_diagnostic = metadata.support_diagnostic()
        condition = (
            SourceCondition.READABLE
            if support_diagnostic is None
            else SourceCondition.UNSUPPORTED
        )
        return (
            SourceComponentResult(
                role=SourceRole.METADATA,
                condition=condition,
                relative_path=relative,
                size_bytes=entry.size_bytes,
                mtime_ns=entry.mtime_ns,
                diagnostic=support_diagnostic,
            ),
            metadata,
        )

    def _database_component(
        self, recording_root: Path, metadata: ParsedMetadata | None
    ) -> tuple[SourceComponentResult, SQLiteProbeResult | None]:
        if metadata is None:
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.UNINSPECTABLE,
                    diagnostic=SafeDiagnostic(
                        "database_not_resolved",
                        "The ROS database cannot be resolved without valid metadata.",
                    ),
                ),
                None,
            )
        support_diagnostic = metadata.support_diagnostic()
        if len(metadata.relative_file_paths) != 1:
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.UNSUPPORTED,
                    diagnostic=support_diagnostic,
                ),
                None,
            )

        declared_path = metadata.relative_file_paths[0]
        try:
            database_path = resolve_declared_source(
                self.archive_root, recording_root, declared_path
            )
        except FileNotFoundError:
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.MISSING,
                    diagnostic=SafeDiagnostic(
                        "database_missing", "The declared ROS database is missing."
                    ),
                ),
                None,
            )
        except UnsafeSourcePath as error:
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.INVALID,
                    diagnostic=SafeDiagnostic(error.code, error.safe_message),
                ),
                None,
            )

        relative = archive_relative_path(self.archive_root, database_path)
        if support_diagnostic is not None:
            details = database_path.stat(follow_symlinks=False)
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.UNSUPPORTED,
                    relative_path=relative,
                    size_bytes=details.st_size,
                    mtime_ns=details.st_mtime_ns,
                    diagnostic=support_diagnostic,
                ),
                None,
            )

        probe = probe_sqlite_database(database_path)
        return (
            SourceComponentResult(
                role=SourceRole.ROS_DATABASE,
                condition=probe.condition,
                relative_path=relative,
                size_bytes=probe.size_bytes,
                mtime_ns=probe.mtime_ns,
                diagnostic=probe.diagnostic,
                revision_facts=probe.revision_facts,
            ),
            probe,
        )

    def _companion_component(
        self,
        entries: tuple[DirectEntry, ...],
        role: SourceRole,
        suffix: str,
    ) -> SourceComponentResult:
        candidates = [
            entry for entry in entries if Path(entry.name).suffix.casefold() == suffix
        ]
        if not candidates:
            return SourceComponentResult(
                role=role,
                condition=SourceCondition.MISSING,
                diagnostic=SafeDiagnostic(
                    f"{role.value}_missing", "The expected companion source is missing."
                ),
            )
        if len(candidates) > 1:
            return SourceComponentResult(
                role=role,
                condition=SourceCondition.AMBIGUOUS,
                diagnostic=SafeDiagnostic(
                    f"{role.value}_ambiguous",
                    "More than one possible companion source was found.",
                ),
                revision_facts=_candidate_revision_facts(
                    self.archive_root, candidates
                ),
            )
        entry = candidates[0]
        relative = archive_relative_path(self.archive_root, entry.path)
        if entry.is_symlink or not entry.is_regular_file:
            return SourceComponentResult(
                role=role,
                condition=SourceCondition.INVALID,
                relative_path=relative,
                size_bytes=entry.size_bytes,
                mtime_ns=entry.mtime_ns,
                diagnostic=SafeDiagnostic(
                    f"{role.value}_not_regular",
                    "The companion source is not a regular file.",
                ),
            )
        return SourceComponentResult(
            role=role,
            condition=SourceCondition.PRESENT,
            relative_path=relative,
            size_bytes=entry.size_bytes,
            mtime_ns=entry.mtime_ns,
        )

    def _uninspectable_recording(
        self, recording_root: Path, diagnostic: SafeDiagnostic
    ) -> RecordingScanResult:
        relative = archive_relative_path(self.archive_root, recording_root)
        components = tuple(
            SourceComponentResult(
                role=role,
                condition=SourceCondition.UNINSPECTABLE,
                diagnostic=diagnostic,
            )
            for role in SourceRole
        )
        revision = _source_revision(
            relative, None, components, None, self.REVISION_VERSION
        )
        return RecordingScanResult(
            archive_relative_path=relative,
            display_name=safe_filesystem_text(recording_root.name),
            start_time_ns=None,
            duration_ns=None,
            total_source_size_bytes=None,
            storage_format=None,
            metadata_version=None,
            message_count=None,
            topic_count=None,
            ros_health=RosHealth.UNINSPECTABLE,
            diagnostic=diagnostic,
            source_revision=revision,
            components=components,
        )


def _aggregate_ros_health(
    metadata_component: SourceComponentResult,
    metadata: ParsedMetadata | None,
    database_component: SourceComponentResult,
) -> tuple[RosHealth, SafeDiagnostic | None]:
    if metadata is None:
        health = (
            RosHealth.MISSING
            if metadata_component.condition is SourceCondition.MISSING
            else RosHealth.UNINSPECTABLE
        )
        return health, metadata_component.diagnostic
    support_diagnostic = metadata.support_diagnostic()
    if support_diagnostic is not None:
        return RosHealth.UNSUPPORTED, support_diagnostic
    if database_component.condition is SourceCondition.READABLE:
        return RosHealth.READABLE, None
    if database_component.condition is SourceCondition.DAMAGED:
        return RosHealth.DAMAGED, database_component.diagnostic
    if database_component.condition is SourceCondition.MISSING:
        return RosHealth.MISSING, database_component.diagnostic
    if database_component.condition is SourceCondition.UNSUPPORTED:
        return RosHealth.UNSUPPORTED, database_component.diagnostic
    return RosHealth.UNINSPECTABLE, database_component.diagnostic


def _complete_source_size(
    components: tuple[SourceComponentResult, ...]
) -> int | None:
    if any(component.size_bytes is None for component in components):
        return None
    return sum(component.size_bytes or 0 for component in components)


def _is_catalog_persistable(recording: RecordingScanResult) -> bool:
    bigint_values = (
        recording.start_time_ns,
        recording.duration_ns,
        recording.total_source_size_bytes,
        recording.message_count,
        *(component.size_bytes for component in recording.components),
        *(component.mtime_ns for component in recording.components),
    )
    integer_values = (recording.metadata_version, recording.topic_count)
    text_values = (
        recording.archive_relative_path,
        recording.display_name,
        recording.storage_format,
        recording.source_revision,
        *(
            value
            for component in recording.components
            for value in (
                component.relative_path,
                None if component.diagnostic is None else component.diagnostic.code,
                None if component.diagnostic is None else component.diagnostic.message,
            )
        ),
        None if recording.diagnostic is None else recording.diagnostic.code,
        None if recording.diagnostic is None else recording.diagnostic.message,
    )
    return (
        all(value is None or is_postgres_bigint(value) for value in bigint_values)
        and all(value is None or is_postgres_integer(value) for value in integer_values)
        and all(value is None or is_postgres_text(value) for value in text_values)
    )


def _safe_path_diagnostic(error: Exception) -> SafeDiagnostic:
    if isinstance(error, UnsafeSourcePath):
        return SafeDiagnostic(error.code, error.safe_message)
    return SafeDiagnostic(
        "recording_uninspectable", "This recording could not be inspected safely."
    )


def _candidate_revision_facts(
    archive_root: Path, candidates: list[DirectEntry]
) -> tuple[tuple[str, int | str], ...]:
    facts: list[tuple[str, int | str]] = []
    for index, candidate in enumerate(candidates):
        prefix = f"candidate_{index}"
        file_kind = (
            "symlink"
            if candidate.is_symlink
            else "regular"
            if candidate.is_regular_file
            else "other"
        )
        facts.extend(
            (
                (
                    f"{prefix}_relative_path",
                    archive_relative_path(archive_root, candidate.path),
                ),
                (f"{prefix}_file_kind", file_kind),
                (
                    f"{prefix}_size_bytes",
                    "unknown" if candidate.size_bytes is None else candidate.size_bytes,
                ),
                (
                    f"{prefix}_mtime_ns",
                    "unknown" if candidate.mtime_ns is None else candidate.mtime_ns,
                ),
            )
        )
    return tuple(facts)


def _source_revision(
    relative_recording: str,
    metadata: ParsedMetadata | None,
    components: tuple[SourceComponentResult, ...],
    database_probe: SQLiteProbeResult | None,
    revision_version: int,
) -> str:
    metadata_facts: dict[str, object] | None = None
    if metadata is not None:
        metadata_facts = {
            "version": metadata.version,
            "storage_identifier": metadata.storage_identifier,
            "duration_ns": metadata.duration_ns,
            "start_time_ns": metadata.start_time_ns,
            "message_count": metadata.message_count,
            "compression_format": metadata.compression_format,
            "compression_mode": metadata.compression_mode,
            "relative_file_paths": metadata.relative_file_paths,
            "topics": [
                {
                    "name": topic.name,
                    "type": topic.message_type,
                    "serialization_format": topic.serialization_format,
                    "message_count": topic.message_count,
                }
                for topic in metadata.topics
            ],
        }
    document = {
        "revision_version": revision_version,
        "recording": relative_recording,
        "metadata": metadata_facts,
        "components": [
            {
                "role": component.role.value,
                "condition": component.condition.value,
                "relative_path": component.relative_path,
                "size_bytes": component.size_bytes,
                "mtime_ns": component.mtime_ns,
                "diagnostic_code": (
                    None if component.diagnostic is None else component.diagnostic.code
                ),
                "revision_facts": component.revision_facts,
            }
            for component in components
        ],
        "sqlite": (
            None if database_probe is None else database_probe.revision_facts
        ),
    }
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["CatalogScanner", "RootScanError"]
