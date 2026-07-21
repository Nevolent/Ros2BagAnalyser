# ROS 2 Bag Analyser

ROS 2 Bag Analyser is a web application under development for reviewing rover
recording runs. It catalogs ROS 2 bags and will prepare reusable browser media
and present two cameras and one telemetry signal on a shared timeline.

## Current status

Building block 1 is complete and was accepted by the user on 2026-07-21. It
provides the read-only scanner, two-table PostgreSQL catalog,
rescan/list/detail API, archive table, recording detail view, and synthetic test
suite. Building blocks 2–5 have not started. The discarded local prototype is
not a dependency or compatibility target.

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

Building block 1 requires Python 3.10 and PostgreSQL. Create an isolated Python
environment and install the locked dependencies and editable package:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
```

Create a PostgreSQL database, create separate existing archive and derived
directories, and configure the process. Do not commit a `.env` file or use the
development paths below as application constants.

```bash
export ROS_BAG_ANALYSER_ARCHIVE_ROOT=/path/to/read-only/archive
export ROS_BAG_ANALYSER_DERIVED_ROOT=/path/to/separate/derived-data
export ROS_BAG_ANALYSER_DATABASE_URL=postgresql://user:password@localhost/database
```

Apply the two-table catalog migration and run the local application:

```bash
.venv/bin/rosbag-analyser-migrate
.venv/bin/rosbag-analyser
```

Open `http://127.0.0.1:8000`. The application does not scan automatically;
existing catalog rows load from PostgreSQL and the browser's **Rescan archive**
button starts a bounded read-only scan.

Run routine tests without PostgreSQL or the real archive:

```bash
.venv/bin/python -m pytest -m "not postgres and not real_archive"
```

PostgreSQL tests reset both catalog tables. Use only a dedicated disposable
database named `rosbag_analyser_test` or beginning with
`rosbag_analyser_test_`, and opt in to that reset explicitly:

```bash
export ROS_BAG_ANALYSER_TEST_DATABASE_URL=postgresql://user:password@localhost/rosbag_analyser_test
export ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET=1
.venv/bin/python -m pytest -m postgres --require-postgres
```

The required-suite flag makes missing PostgreSQL configuration fail rather than
silently skip. The fixture verifies the configured name against PostgreSQL's
`current_database()` before applying the migration or truncating tables.

## Building block 1 acceptance

Real-archive acceptance is separate from routine development and must not be
run without explicit approval. Once approved, identify the configured archive
and the expected damaged database explicitly:

```bash
export RUN_REAL_ARCHIVE_TESTS=1
export ROS_BAG_ANALYSER_ARCHIVE_ROOT=/path/to/read-only/archive
export ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE=2025_11_04_plain_figure8_spotlight_0.db3
.venv/bin/python -m pytest -m real_archive --require-real-archive
```

The required-suite flag makes a missing opt-in fail rather than silently skip.
The test records names, kinds, sizes, and modification times before the scan and
checks the same inventory afterward even if scanning raises. It also verifies
six recordings, five readable databases, and the specifically named damaged
database.

For the visible browser acceptance:

1. Start PostgreSQL and the application, then open `http://127.0.0.1:8000`.
2. Confirm startup loads the existing catalog without scanning automatically.
3. Select **Rescan archive** and verify six rows, five readable and one damaged.
4. Open one healthy row and verify metadata plus all four source components.
5. Open the damaged row and verify the database diagnostic while AVI/CSV
   companions remain present.
6. Record the six recording URLs, rescan again, and verify the row count and IDs
   are unchanged and no processing state appears.
7. Restart the application without rescanning and verify the same PostgreSQL
   catalog reloads.
8. Retain the real-test inventory result with the review notes as source
   immutability evidence.

The user accepted Building block 1 on 2026-07-21 based on the reviewed
implementation and synthetic test suite. The opt-in real-archive run and manual
browser checklist were not executed during this review; they remain available
as additional environment-specific evidence. Generic tests never access
`/mnt/d/Rosbags`.
