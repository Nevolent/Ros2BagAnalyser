#!/usr/bin/env python3
"""Read-only diagnostic for front-camera ROS Image headers and encodings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from rosbag_analyser.config import DEFAULT_FRONT_TOPIC
from rosbag_analyser.front_header_diagnostic import (
    DEFAULT_MAX_MESSAGES,
    FrontHeaderDiagnosticError,
    inspect_front_headers,
    resolve_front_source,
)
from rosbag_analyser.processors.front_preview import FrontPreviewProcessingError


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect selected front-camera headers and encodings through immutable SQLite access. "
            "The report is written only to standard output."
        )
    )
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument(
        "--recording",
        required=True,
        action="append",
        help="Safe archive-relative recording directory; repeat for each recording.",
    )
    parser.add_argument("--front-topic", default=DEFAULT_FRONT_TOPIC)
    parser.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    arguments = parser.parse_args()

    reports: list[dict[str, object]] = []
    failed = False
    for recording in arguments.recording:
        try:
            descriptor = resolve_front_source(
                arguments.archive_root, recording, arguments.front_topic
            )
            report = inspect_front_headers(
                descriptor, max_messages=arguments.max_messages
            )
            reports.append(
                {
                    "recording_path": recording,
                    "status": "complete",
                    "front_topic": arguments.front_topic,
                    "report": report.json_values(),
                }
            )
        except (FrontHeaderDiagnosticError, FrontPreviewProcessingError, ValueError) as error:
            failed = True
            reports.append(
                {
                    "recording_path": recording,
                    "status": "failed",
                    "diagnostic": {
                        "code": getattr(error, "code", "front_header_diagnostic_invalid"),
                        "message": getattr(error, "safe_message", str(error)),
                    },
                }
            )
    json.dump({"reports": reports}, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
