#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rosbag_analyser.catalog.paths import (
    CatalogScanLimits,
    archive_relative_path,
    discover_recording_directories,
)
from rosbag_analyser.catalog.types import RootScanError
from rosbag_analyser.topic_audit import TopicAuditError, audit_recording_topics


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit recording topics without reading messages.")
    parser.add_argument("--archive-root", required=True, type=Path)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--recording", action="append")
    selection.add_argument(
        "--all",
        action="store_true",
        help="Audit every recording found by the bounded, non-symlink catalog walk.",
    )
    parser.add_argument("--front-topic", required=True)
    parser.add_argument("--imu-topic", required=True)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--max-entries", type=int, default=100_000)
    parser.add_argument("--max-directories", type=int, default=10_000)
    parser.add_argument("--max-recordings", type=int, default=5_000)
    parser.add_argument("--max-directory-entries", type=int, default=2_000)
    parser.add_argument("--max-recording-entries", type=int, default=256)
    arguments = parser.parse_args()

    recordings = arguments.recording or []
    if arguments.all:
        try:
            limits = CatalogScanLimits(
                max_depth=arguments.max_depth,
                max_entries=arguments.max_entries,
                max_directories=arguments.max_directories,
                max_recordings=arguments.max_recordings,
                max_directory_entries=arguments.max_directory_entries,
                max_recording_entries=arguments.max_recording_entries,
            )
            recordings = [
                archive_relative_path(arguments.archive_root, item.path)
                for item in discover_recording_directories(arguments.archive_root, limits)
            ]
        except (RootScanError, ValueError) as error:
            print(json.dumps({
                "status": "failed",
                "diagnostic": {
                    "code": getattr(getattr(error, "diagnostic", None), "code", "archive_discovery_failed"),
                    "message": getattr(getattr(error, "diagnostic", None), "message", str(error)),
                },
            }, sort_keys=True))
            return 1

    failed = False
    completed = 0
    for recording in recordings:
        try:
            report = audit_recording_topics(arguments.archive_root, recording, front_topic=arguments.front_topic, imu_topic=arguments.imu_topic)
            completed += 1
        except (TopicAuditError, ValueError) as error:
            failed = True
            report = {"recording_path": recording, "status": "failed", "diagnostic": {"code": getattr(error, "code", "topic_audit_invalid"), "message": getattr(error, "safe_message", str(error))}}
        print(json.dumps(report, sort_keys=True))
    print(json.dumps({
        "record_type": "summary",
        "status": "complete_with_failures" if failed else "complete",
        "recording_count": len(recordings),
        "completed_count": completed,
        "failed_count": len(recordings) - completed,
    }, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
