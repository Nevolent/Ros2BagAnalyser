from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import time

from .limits import is_postgres_bigint, is_postgres_integer, is_postgres_text
from .metadata import MetadataError, ParsedMetadata, parse_metadata_file
from .paths import (
    CatalogScanLimits,
    DirectEntry,
    SourceFileIdentity,
    UnsafeSourcePath,
    archive_relative_path,
    discover_recording_directories,
    resolve_declared_source,
    safe_filesystem_text,
    source_file_identity,
    inventory_direct_entries,
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
from rosbag_analyser.preparation_planner import RecordingPreparationFacts


logger = logging.getLogger(__name__)


class CatalogScanner:
    """Describe an archive without writing to sources or persistence."""

    REVISION_VERSION = 2

    def __init__(
        self,
        archive_root: Path,
        *,
        limits: CatalogScanLimits | None = None,
        settle_seconds: float = 0,
    ) -> None:
        self.archive_root = archive_root
        self.limits = limits or CatalogScanLimits()
        self.settle_seconds = settle_seconds
        self._copy_observations: dict[str, tuple[tuple, float]] = {}

    def _settled(self, path: str, entries: tuple[DirectEntry, ...]) -> bool:
        signature = tuple((entry.name, entry.identity, entry.is_symlink) for entry in entries)
        now = time.monotonic()
        previous = self._copy_observations.get(path)
        if previous is None or previous[0] != signature:
            self._copy_observations[path] = (signature, now)
            return self.settle_seconds <= 0
        # A nonempty SQLite journal/WAL indicates a live recording. Never open
        # such a database as immutable or treat it as a finished copied bag.
        if any(entry.name.endswith(('-wal', '-journal')) and entry.size_bytes for entry in entries):
            self._copy_observations[path] = (signature, now)
            return False
        return now - previous[1] >= self.settle_seconds

    def scan(
        self,
        *,
        known_recordings: frozenset[str] | None = None,
        timing_cache: dict[str, dict] | None = None,
        existing_paths: frozenset[str] = frozenset(),
    ) -> ScanSnapshot:
        started = time.monotonic_ns()
        recordings: list[RecordingScanResult] = []
        # Rename detection still traverses every path. Reuse timing for the same
        # physical database at a new path without an O(recordings²) cache search.
        timing_by_identity = {
            tuple(cache["key"]["file"]): cache
            for cache in (timing_cache or {}).values()
            if isinstance(cache, dict) and isinstance(cache.get("key"), dict)
            and isinstance(cache["key"].get("file"), list)
            and len(cache["key"]["file"]) == 6
            and all(type(value) is int for value in cache["key"]["file"])
        }
        candidates = discover_recording_directories(
            self.archive_root,
            self.limits,
            known_recordings=known_recordings or frozenset(),
        )
        # Observe every new inventory before inspecting any database. Otherwise
        # slow earlier bags postpone the quiet-period start for later folders.
        saved_paths = existing_paths if known_recordings is None else known_recordings
        unsettled = set()
        if self.settle_seconds > 0:
            for candidate in candidates:
                path = archive_relative_path(self.archive_root, candidate.path)
                if path not in saved_paths and (
                    candidate.entries is None or not self._settled(path, candidate.entries)
                ):
                    unsettled.add(path)
        for candidate in candidates:
            recording_root = candidate.path
            relative_path = archive_relative_path(self.archive_root, recording_root)
            if known_recordings is not None and relative_path in known_recordings:
                continue
            is_new = relative_path not in saved_paths
            if relative_path in unsettled:
                continue
            if candidate.entries is None:
                recordings.append(
                    self._uninspectable_recording(
                        recording_root,
                        SafeDiagnostic(
                            candidate.diagnostic_code or "recording_uninspectable",
                            candidate.diagnostic_message
                            or "This recording could not be inspected safely.",
                        ),
                    )
                )
                continue
            try:
                result = self._scan_recording(
                    recording_root, candidate.entries, timing_cache, timing_by_identity
                )
                # Recheck the whole inventory after inspection, including AVI
                # companions and newly arriving files. Copies can resume midscan.
                if self.settle_seconds > 0 and is_new:
                    after = inventory_direct_entries(recording_root, max_entries=self.limits.max_recording_entries)
                    if after != candidate.entries:
                        self._settled(relative_path, after)
                        continue
                recordings.append(result)
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
        if known_recordings is not None:
            # Incomplete copies remain undiscovered and can be retried on the
            # next page load. Full rescans still report all source diagnostics.
            recordings = [
                item for item in recordings if item.ros_health is RosHealth.READABLE
            ]
        elapsed_ms = (time.monotonic_ns() - started) // 1_000_000
        present = {archive_relative_path(self.archive_root, candidate.path) for candidate in candidates}
        self._copy_observations = {path: item for path, item in self._copy_observations.items()
                                   if path in present and path not in saved_paths}
        return ScanSnapshot(
            recordings=tuple(recordings),
            duration_ms=elapsed_ms,
            present_paths=(
                frozenset(
                    archive_relative_path(self.archive_root, candidate.path)
                    for candidate in candidates
                ) if known_recordings is not None else None
            ),
        )

    def _scan_recording(
        self,
        recording_root: Path,
        entries: tuple[DirectEntry, ...],
        timing_cache: dict[str, dict] | None = None,
        timing_by_identity: dict[tuple[int, ...], dict] | None = None,
    ) -> RecordingScanResult:
        relative_recording = archive_relative_path(self.archive_root, recording_root)

        metadata_component, metadata, metadata_identity = self._metadata_component(
            recording_root, entries
        )
        video_component, video_identity = self._companion_component(
            entries, SourceRole.TOPDOWN_VIDEO, ".avi"
        )
        timestamp_component, timestamps_identity = self._companion_component(
            entries, SourceRole.TOPDOWN_TIMESTAMPS, ".csv"
        )
        database_component, database_probe, database_identity = self._database_component(
            recording_root, metadata, timing_cache, timing_by_identity
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
        if metadata is not None and database_probe is not None and database_probe.timing:
            timing = database_probe.timing
            if timing["origin_ns"] is not None:
                offset = int(timing["origin_ns"]) - metadata.start_time_ns
                for gap in timing["gaps"]:
                    gap["start_ns"] = str(int(gap["start_ns"]) + offset)
                    gap["end_ns"] = str(int(gap["end_ns"]) + offset)
        if diagnostic is None and database_probe is not None and database_probe.timing:
            gaps = database_probe.timing["gaps"]
            if gaps:
                longest = gaps[0]
                seconds = int(longest["duration_ns"]) / 1_000_000_000
                origin = metadata.start_time_ns if metadata is not None else int(database_probe.timing["origin_ns"])
                timestamp = (origin + int(longest["start_ns"])) / 1_000_000_000
                diagnostic = SafeDiagnostic(
                    "recording_time_gap",
                    f"Possible missing data: a {seconds:.1f} s timestamp gap near Unix time "
                    f"{timestamp:.3f}. Review the timeline; timestamps alone do not prove data loss.",
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
            scan_details={
                "topics": [
                    {"name": topic.name, "message_type": topic.message_type,
                     "serialization_format": topic.serialization_format,
                     "message_count": str(topic.message_count)}
                    for topic in metadata.topics
                ] if metadata is not None else None,
                "timing": database_probe.timing if database_probe is not None else None,
                "timing_cache": database_probe.timing_cache if database_probe is not None else None,
            },
            preparation_facts=RecordingPreparationFacts(
                metadata=metadata,
                metadata_identity=metadata_identity,
                database_identity=database_identity,
                video_identity=video_identity,
                timestamps_identity=timestamps_identity,
            ),
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
    ) -> tuple[
        SourceComponentResult,
        ParsedMetadata | None,
        SourceFileIdentity | None,
    ]:
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
                entry.identity,
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
                entry.identity,
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
            entry.identity,
        )

    def _database_component(
        self,
        recording_root: Path,
        metadata: ParsedMetadata | None,
        timing_cache: dict[str, dict] | None = None,
        timing_by_identity: dict[tuple[int, ...], dict] | None = None,
    ) -> tuple[
        SourceComponentResult,
        SQLiteProbeResult | None,
        SourceFileIdentity | None,
    ]:
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
                None,
            )

        relative = archive_relative_path(self.archive_root, database_path)
        database_identity = source_file_identity(
            database_path.stat(follow_symlinks=False)
        )
        if support_diagnostic is not None:
            return (
                SourceComponentResult(
                    role=SourceRole.ROS_DATABASE,
                    condition=SourceCondition.UNSUPPORTED,
                    relative_path=relative,
                    size_bytes=database_identity.size_bytes,
                    mtime_ns=database_identity.mtime_ns,
                    diagnostic=support_diagnostic,
                ),
                None,
                database_identity,
            )

        cached = (timing_cache or {}).get(relative)
        if cached is None and timing_by_identity:
            cached = timing_by_identity.get((
                database_identity.device_id, database_identity.inode,
                database_identity.mode, database_identity.size_bytes,
                database_identity.mtime_ns, database_identity.ctime_ns,
            ))
        probe = (
            probe_sqlite_database(database_path) if cached is None else
            probe_sqlite_database(database_path, timing_cache=cached)
        )
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
            database_identity,
        )

    def _companion_component(
        self,
        entries: tuple[DirectEntry, ...],
        role: SourceRole,
        suffix: str,
    ) -> tuple[SourceComponentResult, SourceFileIdentity | None]:
        candidates = [
            entry for entry in entries if Path(entry.name).suffix.casefold() == suffix
        ]
        if not candidates:
            return (
                SourceComponentResult(
                    role=role,
                    condition=SourceCondition.MISSING,
                    diagnostic=SafeDiagnostic(
                        f"{role.value}_missing", "The expected companion source is missing."
                    ),
                ),
                None,
            )
        if len(candidates) > 1:
            return (
                SourceComponentResult(
                    role=role,
                    condition=SourceCondition.AMBIGUOUS,
                    diagnostic=SafeDiagnostic(
                        f"{role.value}_ambiguous",
                        "More than one possible companion source was found.",
                    ),
                    revision_facts=_candidate_revision_facts(
                        self.archive_root, candidates
                    ),
                ),
                None,
            )
        entry = candidates[0]
        relative = archive_relative_path(self.archive_root, entry.path)
        if entry.is_symlink or not entry.is_regular_file:
            return (
                SourceComponentResult(
                    role=role,
                    condition=SourceCondition.INVALID,
                    relative_path=relative,
                    size_bytes=entry.size_bytes,
                    mtime_ns=entry.mtime_ns,
                    diagnostic=SafeDiagnostic(
                        f"{role.value}_not_regular",
                        "The companion source is not a regular file.",
                    ),
                ),
                entry.identity,
            )
        return (
            SourceComponentResult(
                role=role,
                condition=SourceCondition.PRESENT,
                relative_path=relative,
                size_bytes=entry.size_bytes,
                mtime_ns=entry.mtime_ns,
            ),
            entry.identity,
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
    known_sizes = tuple(
        component.size_bytes
        for component in components
        if component.size_bytes is not None
    )
    return None if not known_sizes else sum(known_sizes)


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
