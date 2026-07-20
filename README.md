# ROS 2 Bag Analyser

ROS 2 Bag Analyser is a planned web application for reviewing rover recording
runs. It will catalog ROS 2 bags, prepare reusable browser media, and present
two cameras and one telemetry signal on a shared timeline.

## Current status

This repository is a fresh, documentation-only baseline. There is no runnable
application, backend, frontend, database schema, worker, or build configuration.
The discarded local prototype is not a dependency or compatibility target.

Implementation has not started. Work begins only after the user approves the
exact boundary of a building block in [ROADMAP.md](ROADMAP.md).

## V0 proof

V0 has five outcomes:

1. Scan the six known recording folders and show one row per run.
2. Show useful metadata and identify the damaged ROS database without crashing.
3. Generate and reuse a browser-playable front-camera preview.
4. Add the timestamped top-down camera and control both cameras from one
   synchronized timeline.
5. Show one synchronized IMU angular-velocity graph.

Acceptance covers the catalog across all six runs, the complete review workflow
on one short healthy run, a final opt-in scale acceptance on one long healthy
run, and clear diagnostics for the damaged run. This is a mentor-facing proof,
not a production robotics platform.

## Development data and safety

The current development archive is external to this repository:

```text
Windows: D:\Rosbags
WSL:     /mnt/d/Rosbags
```

It contains six recording directories: five readable ROS 2 SQLite bags and one
truncated, malformed database. The detailed inspected facts and current topic
assumptions are recorded in [PROJECT.md](PROJECT.md).

Original recordings are always read-only. The application must never modify,
repair, reindex, rename, move, delete, or write generated files beside a source.
Previews and extracted telemetry go to a separate configurable derived-data
location.

## V0 shape

V0 remains a modular monolith: a browser interface, a thin HTTP API, persistent
application metadata, one background processing path for expensive work, and a
separate filesystem location for derived artifacts. Exact storage, processing,
artifact, and synchronization decisions belong to
[ARCHITECTURE.md](ARCHITECTURE.md).

Redis, distributed workers, authentication, LiDAR, annotations, collaboration,
and production deployment are outside V0.

## Project documents

- [PROJECT.md](PROJECT.md) owns product direction, inspected data facts, V0
  scope, and requirements.
- [ARCHITECTURE.md](ARCHITECTURE.md) owns technical boundaries, data flow,
  storage, processing, artifacts, and timing.
- [ROADMAP.md](ROADMAP.md) owns build order, block status, verification, and
  acceptance gates.
- [AGENTS.md](AGENTS.md) owns standing contribution and source-safety rules.

## Development

There are no setup or run commands yet. Do not scaffold application code,
install dependencies, or process recordings until the relevant roadmap block is
explicitly approved.
