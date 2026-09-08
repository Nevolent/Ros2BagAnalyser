#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from rosbag_analyser.topic_audit import TopicAuditError, audit_recording_topics


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit topics in explicitly selected recordings without reading messages.")
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--recording", required=True, action="append")
    parser.add_argument("--front-topic", required=True)
    parser.add_argument("--imu-topic", required=True)
    arguments = parser.parse_args()
    reports: list[dict[str, object]] = []
    failed = False
    for recording in arguments.recording:
        try:
            reports.append(audit_recording_topics(arguments.archive_root, recording, front_topic=arguments.front_topic, imu_topic=arguments.imu_topic))
        except (TopicAuditError, ValueError) as error:
            failed = True
            reports.append({"recording_path": recording, "status": "failed", "diagnostic": {"code": getattr(error, "code", "topic_audit_invalid"), "message": getattr(error, "safe_message", str(error))}})
    json.dump({"reports": reports}, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
