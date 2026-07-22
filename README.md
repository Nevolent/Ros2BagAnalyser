# ROS 2 Bag Analyser

ROS 2 Bag Analyser is a web application under development for reviewing rover
recording runs. It catalogs ROS 2 bags and will prepare reusable browser media
and present two cameras and one telemetry signal on a shared timeline.

## Current status

Building blocks 1, 2, 3, and 4 are complete and user-accepted. Building block 5
implementation was approved on 2026-07-22 for the exact V0 integration and
mentor-readiness boundary in `ROADMAP.md`. Its implementation and automated
verification are complete, and its explicit opt-in real-archive acceptance
matrix passed on 2026-07-22. User review remains pending. The four-table
PostgreSQL model and one serial worker remain unchanged. The discarded local
prototype is not a dependency or compatibility target.

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

The current implementation requires Python 3.10, PostgreSQL, FFmpeg and
ffprobe, plus a ROS 2 Humble Python environment for the worker. Node.js 18 or
newer is a test-only prerequisite for the dependency-free browser suite; it is
not an application runtime dependency and no npm packages are required. Create
an isolated Python environment and install the locked dependencies and editable
package:

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
export ROS_BAG_ANALYSER_FRONT_TOPIC=/kuupkulgur_v1/sensors/front_camera/image_raw
export ROS_BAG_ANALYSER_IMU_TOPIC=/configured/standard/imu/topic
export ROS_BAG_ANALYSER_IMU_COMPONENT=angular_velocity.z
export ROS_BAG_ANALYSER_PREVIEW_PROFILE=h264-720p-v1
```

The front topic, IMU component, and profile shown have defaults; the IMU topic
is required because topic names are recording/environment configuration rather
than a product constant. `ROS_BAG_ANALYSER_FFMPEG` and
`ROS_BAG_ANALYSER_FFPROBE` may identify explicit executables; otherwise both
are resolved from `PATH` at startup.

Apply the migrations, then run the API and serial worker in separate sourced
shells:

```bash
.venv/bin/rosbag-analyser-migrate
.venv/bin/rosbag-analyser

# In a second shell with the same settings:
source /opt/ros/humble/setup.bash
.venv/bin/rosbag-analyser-worker
```

Open `http://127.0.0.1:8000`. The application does not scan automatically;
existing catalog rows load from PostgreSQL and the browser's **Rescan archive**
button starts a bounded read-only scan. Open a readable recording and select
**Generate front preview**. The request returns immediately; only the separate
worker reads image messages and creates media. Ready files are stored below
the configured derived root, never in the archive. The top-down pane has its
own **Generate top-down preview** action and uses the same serial worker and
fixed output profile. The IMU pane has a separate **Generate IMU series**
action, but still queues work through that one worker.

The supported Building block 2 input is one configured
`sensor_msgs/msg/Image` topic using `bgr8`. The fixed `h264-720p-v1` profile is
an MP4/H.264/yuv420p preview, bounded to 1280 × 720. ROS record timestamps drive
frame timing and measured coverage; equal record timestamps collapse to the
last frame at that time. Failed and interrupted attempts require an explicit
retry.

Irregular ROS record timestamps remain visible in the preview. A gap makes the
player hold the preceding image until the next recorded frame, so source
record-time jitter can look like a brief freeze even when camera header stamps
are regular. This preserves the accepted synchronization clock; smoothing the
preview with header timestamps or an assumed constant frame rate would change
that contract.

Top-down processing pairs the one catalogued AVI and CSV in the recording. The
CSV `unix_timestamp` column is parsed directly to integer nanoseconds and must
contain one strictly increasing value for every decoded AVI frame. The AVI's
nominal frame rate is ignored; output frame PTS follow CSV elapsed time. Both
camera panes use one browser-owned global timeline, report measured coverage,
and hide rather than freeze outside their coverage. A damaged ROS recording may
still show its AVI/CSV component facts, but synchronized top-down processing is
unavailable when the bag origin is not trustworthy.

IMU processing accepts the configured `sensor_msgs/msg/Imu` topic using CDR and
extracts only `angular_velocity.z`. ROS database record timestamps are converted
to integer nanoseconds relative to the bag start. The derived JSON preserves
source order, duplicate timestamps, every finite value, and explicit `null`
gaps for non-finite values. The browser labels the signal exactly as
`IMU angular_velocity.z (rad/s)`, maps it across the full recording timeline,
and clears the current value outside measured coverage. The V0 series uses no
reduction: a synthetic 76,000-sample profile measured a 2.76 MB payload, a
41 ms parse, and a 6 ms Canvas draw in headless Edge on the development host.

Run routine tests without PostgreSQL, ROS, or the real archive:

```bash
.venv/bin/python -m pytest -m "not postgres and not real_archive and not ros"
```

The generated ROS-message test requires the sourced Humble environment. Plugin
autoload is disabled here because the system ROS pytest bundle may include
unrelated optional launch-test plugins:

```bash
source /opt/ros/humble/setup.bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/ros
```

PostgreSQL tests reset all four application tables. Use only a dedicated
disposable database named `rosbag_analyser_test` or beginning with
`rosbag_analyser_test_`, and opt in to that reset explicitly:

```bash
export ROS_BAG_ANALYSER_TEST_DATABASE_URL=postgresql://user:password@localhost/rosbag_analyser_test
export ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET=1
.venv/bin/python -m pytest -m postgres --require-postgres
```

The required-suite flag makes missing PostgreSQL configuration fail rather than
silently skip. The fixture verifies the configured name against PostgreSQL's
`current_database()` before applying migrations or truncating tables.

Check the shipped browser code separately:

```bash
node --check src/rosbag_analyser/web/app.js
node --check src/rosbag_analyser/web/imu_graph.js
node --test tests/js/test_imu_graph.js tests/js/test_review_runtime.js
```

## V0 mentor demonstration

Building block 5 integrates the accepted catalog, front preview, top-down
preview, shared timeline, and IMU graph into one mentor-facing acceptance run.
It does not add another processing or storage subsystem. The run uses exactly
one API, one serial worker, the existing four PostgreSQL tables, and a derived
root that is separate from the read-only archive.

Real-archive access is never implied by an ordinary test or implementation
run. Before beginning this demonstration, obtain explicit opt-in approval for
the named archive and selected short, long, and damaged cases. Freeze the
reviewed worktree for the duration of the run; if code changes, start the
acceptance matrix again from a fresh before-inventory.

### Clean setup record

Create a new dedicated application database and a new empty derived directory.
Do not truncate an existing application database or delete an uncertain derived
directory. Record the following with the acceptance notes without committing
credentials or machine-specific absolute storage paths:

- Git revision and clean/dirty state;
- Python, PostgreSQL, ROS 2, PyAV, FFmpeg, ffprobe, browser, and Node versions;
- configured front topic, IMU topic/component, and preview profile;
- selected catalog IDs for the short healthy, long healthy, and damaged cases;
- confirmation that archive and derived roots are separate;
- the four PostgreSQL table names after migration.

Install from `requirements.lock`, apply the migrations, start the API, and then
start exactly one worker in a sourced ROS 2 Humble shell. A second worker must
exit rather than processing concurrently. Opening the application must load the
saved catalog without scanning or creating jobs automatically.

### Source inventory evidence

Before the first scan, capture one lightweight, recursively sorted inventory of
the complete archive containing only each entry's relative name, kind, byte
size, and nanosecond modification time. Store both inventory files and any
digest outside the archive, such as in the acceptance evidence directory or
derived root. A digest may cover this small inventory manifest; do not hash the
100+ GiB of source payloads.

After every acceptance check is finished, capture the same inventory again and
require an exact comparison. Also confirm that every generated file is under
the configured derived root. Any mismatch stops acceptance. Do not repair,
reindex, truncate, rename, or otherwise change a source to investigate it.

The opt-in catalog check remains available as an additional immediate
read-only guard:

```bash
export RUN_REAL_ARCHIVE_TESTS=1
export ROS_BAG_ANALYSER_ARCHIVE_ROOT=/path/to/read-only/archive
export ROS_BAG_ANALYSER_EXPECTED_DAMAGED_DATABASE=expected-damaged-name.db3
.venv/bin/python -m pytest -m real_archive --require-real-archive
```

### Acceptance matrix

**All recordings**

1. Confirm startup displays the saved catalog without scanning automatically.
2. Select **Rescan archive** and require six unique rows: five readable and one
   damaged.
3. Inspect healthy and damaged details and confirm all four source-component
   roles remain visible where present.
4. Record the six recording IDs, rescan again, and require the same IDs and row
   count.
5. Confirm scanning created no job or artifact and PostgreSQL still contains
   exactly `recordings`, `source_components`, `artifacts`, and `jobs`.

**Short healthy complete flow**

1. Request front, top-down, and IMU output. With one worker, expect one item to
   process while later items remain truthfully queued.
2. Repeat requests while work is active. Require one active job per matching
   `(kind, cache_identity)` and no partial ready artifact.
3. While processing continues, load the catalog and recording detail and record
   that both remain responsive.
4. Observe every output reach `ready`; record job/artifact IDs, cache identities,
   processing duration, output size, coverage, provenance, and warnings.
5. Play, pause, and seek near the global start, middle, and end plus times just
   inside and, where available, just outside each stream's measured coverage.
6. Confirm one global clock drives both cameras and the IMU cursor. An
   out-of-coverage camera must hide, the IMU value must clear outside IMU
   coverage, and the other consumers and clock must continue.
7. Sustain playback and perform repeated seeks without visible cumulative
   offset. Existing front-camera holds caused by ROS record-time gaps remain
   expected and must not be smoothed using header time.

**Reuse and duplicate prevention**

1. Record the ready artifact IDs, reload the page, rescan, and restart the API
   and worker with identical configuration.
2. Repeat all three requests and require the same compatible artifacts to be
   reused without new active jobs or ready artifacts.
3. Check counts grouped by `(kind, cache_identity)`; total table counts alone do
   not prove that the requested identity was reused.

**Damaged recording**

1. Confirm the ROS diagnostic is clear while AVI/CSV companion facts remain
   visible.
2. Confirm front and IMU processing are `unavailable`.
3. Confirm synchronized top-down processing is `unavailable` because a trusted
   bag-relative origin does not exist.
4. Repeat the requests and verify that no job or artifact is created.

**Final long scale smoke**

Run only the selected long healthy case and start the worker under
`/usr/bin/time -v`. Complete or reuse front, top-down, and IMU output, then
record per-artifact duration and size, worker peak resident memory and swap,
ordinary API responsiveness during work, sustained playback observations,
representative start/middle/end seeks, visible drift, and IMU payload/load/scrub
behavior. This is an observed practicality check, not a numeric service-level
agreement. Do not add parallel workers, progress percentages, telemetry
reduction, or other deferred infrastructure to change its result.

### Truthful UI states

- `not requested` offers an explicit generate action;
- `queued` waits for the one serial worker;
- `processing` means that processor is actively running;
- `unavailable` means prerequisites prevent an attempt and no job exists;
- `failed` means an attempt ended with an error and offers explicit retry;
- `ready` means a matching artifact and contained output were revalidated;
- `outside coverage` is a timeline condition, never a processing failure.

If loading a page, status response, media file, or IMU JSON fails, use its
visible retry action. Do not confuse a status-fetch failure with source
unavailability.

### Troubleshooting

- **Catalog database unavailable:** verify the PostgreSQL URL and server, then
  retry loading. A failed rescan retains the last complete catalog.
- **Queued indefinitely:** verify the worker uses the same database and
  configuration and that its ROS 2 Humble environment is sourced.
- **Second worker rejected:** stop the duplicate process; V0 deliberately permits
  only one serial worker.
- **FFmpeg or ffprobe rejected at startup:** configure the intended executable
  explicitly or correct `PATH`; the application verifies executable identity.
- **Front or IMU unavailable:** verify the exact configured topic, standard
  message type, CDR serialization, and supported component/encoding, then rescan
  if the source facts changed.
- **Interrupted or failed job:** inspect the safe diagnostic and request an
  explicit retry. V0 has no automatic retry or active-job recovery lease.
- **Ready output no longer loads:** reload its state. Missing, changed, or invalid
  artifacts are not silently served under a stale URL.
- **Root-overlap error:** choose separate existing archive and derived
  directories; never weaken this validation.

### V0 limitations

V0 intentionally has no authentication, public deployment, upload/watch flow,
repair tools, general split-bag or alternate-format support, arbitrary topics or
encodings, extra cameras or graphs, custom-message processing, LiDAR/GPS/maps,
click-to-seek graphs, playback-rate controls, cancellation, automatic retry,
leases, priorities, multiple workers, retention, cleanup, monitoring, or job
console. Record a limitation rather than expanding Building block 5 to solve
deferred product or operations work.

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

## Building block 2 acceptance

The safe synthetic suite covers source selection, malformed and oversized
images, bounded frame streaming, variable record-time mapping, keyframes, cache
invalidation, invalid-artifact recovery, confined atomic publication, worker
success/failure/interruption, consistent API states, and conditional byte
ranges. The generated ROS test covers real Humble serialization without using a
recording archive.

The environment-specific review remains opt-in. It was explicitly approved and
completed for Building block 2 on 2026-07-21. For any future revalidation,
capture a before-and-after inventory of names, sizes, and modification times and
compare it exactly as source-immutability evidence.

1. On one short readable recording, request the preview and observe
   `not requested` → `queued`/`processing` → `ready`.
2. Play, pause, and seek near the beginning, middle, and end; confirm the global
   elapsed time and explicit outside-coverage state remain honest. Let playback
   reach the global end and confirm both the clock and video stop.
3. Reload, rescan, and restart the API and worker; confirm the same ready output
   is reused and repeated requests create no duplicate active job or artifact.
4. Open the damaged recording; confirm it is unavailable and creates no job.
5. For one approved longer recording, start the worker with
   `/usr/bin/time -v .venv/bin/rosbag-analyser-worker`, request exactly one
   preview, and stop after it reaches `ready`. Record the worker's logged
   processing duration and output size plus `Maximum resident set size` from
   `time`; then repeat the play/seek/reload/reuse checks above.
6. Compare the after-inventory with the before-inventory for both recordings.

The accepted run covered a short playable and seekable preview, restart and
request reuse, one longer bounded-memory render, the damaged recording, a
disposable PostgreSQL 14 database, and unchanged source metadata. It also
confirmed that reported short-preview freezes reproduce gaps already present in
ROS record timestamps rather than dropped preview frames. Exact evidence is
recorded in [ROADMAP.md](ROADMAP.md).

Future access to or processing of the real archive requires separate explicit
approval. Building block 3 was reviewed and accepted on 2026-07-22; its manual
browser and real-archive procedure remains available as optional future
revalidation.

## Building block 3 acceptance

Routine synthetic tests do not access the real archive. The following manual
procedure is opt-in and must not begin until access to the named recordings is
approved. Keep the archive and derived-data roots separate throughout.

1. Identify one short readable recording, one longer readable recording, and
   the expected damaged recording. Before processing, inventory every source
   item in those recording directories by relative name, kind, byte size, and
   modification time. Do not create hashes, locks, indexes, or sidecars there.
2. Apply migrations to a dedicated PostgreSQL database, then start the API and
   exactly one serial worker with the same archive, derived-root, and profile
   configuration.
3. On the short recording, request the front and top-down previews. Observe
   each transition from `not requested` through `queued`/`processing` to
   `ready`, then confirm another request reuses the ready artifact.
4. Play, pause, and scrub to times before, inside, and after each camera's
   measured coverage. Confirm both visible cameras show matching global time,
   an out-of-coverage camera is hidden with an explicit message, and the other
   camera and global clock continue. Repeat several seeks while playing and
   confirm no visible cumulative offset develops.
5. Reload the page, rescan, and restart the API and worker. Confirm both ready
   artifacts remain reusable and repeated requests create neither duplicate
   active jobs nor duplicate artifacts.
6. Open the damaged recording. Confirm its AVI/CSV component facts remain
   visible, synchronized top-down media is unavailable, and requesting it does
   not create a processing job.
7. For the longer recording, run the worker under
   `/usr/bin/time -v .venv/bin/rosbag-analyser-worker`, generate both previews,
   and record logged duration, output size, and maximum resident set size.
   Sustain playback, then seek near the start, middle, and end; confirm honest
   coverage and no accumulating visible offset.
8. Stop processing and capture the same source inventory again. Require an
   exact before/after match and retain it with the review evidence. Confirm all
   generated files are confined to the configured derived-data root.

PostgreSQL verification and JavaScript runtime syntax checking passed on
2026-07-22. This browser procedure and real-archive checks are separate pieces
of evidence and must not be reported as complete unless they are actually run.

## Building block 4 acceptance

Routine tests use tiny synthetic SQLite databases and generated ROS messages;
they never access the development archive. The following end-to-end procedure
requires separate explicit approval for the named recordings.

1. Configure the exact standard IMU topic and identify one short readable
   recording, one longer readable recording, and the damaged recording. Capture
   a before-inventory of source-relative names, kinds, byte sizes, and
   modification times for each selected directory.
2. Apply migrations to a dedicated PostgreSQL database and start the API plus
   exactly one serial worker with the same archive, derived root, front topic,
   IMU topic, component, and preview profile.
3. Independently inspect several short-recording IMU rows read-only and record
   their ROS database timestamps and `angular_velocity.z` values. Do not create
   indexes, journals, WAL files, locks, caches, or sidecars in the source.
4. In the short recording, request the IMU series and observe `not requested`
   through `queued`/`processing` to `ready`. Compare the graph label, units,
   coverage, representative timestamps, values, and any non-finite gaps with
   the independent inspection.
5. Play, pause, and seek before, inside, and after IMU coverage while both
   cameras are present. Confirm the graph cursor follows the one global clock,
   the current value is the last sample at or before that clock time, duplicate
   timestamps resolve to the last database-order sample, and no value is shown
   outside coverage.
6. Reload, rescan, and restart the API and worker. Confirm the ready series is
   reused and repeated requests create no duplicate active job or artifact.
7. Open the damaged recording and any readable recording lacking the configured
   topic. Confirm IMU is `unavailable` and no IMU processing job is created.
8. On the longer recording, record extraction duration, output byte size, and
   worker maximum resident set size. Load the graph and scrub repeatedly near
   the start, middle, and end, recording browser payload/parse/draw observations
   and confirming responsive cursor/value updates.
9. Capture the same source inventory after the checks and require an exact
   before/after match. Confirm every generated file is confined to the derived
   root.

The real archive was not accessed during Building block 4 implementation. In
the final approved acceptance handoff, the application was connected to
`/mnt/d/Rosbags` with a separate derived root and the configured standard IMU
topic. The opt-in catalog check found six recordings, five readable bags, and
the expected damaged bag; its before/after source inventory was identical. The
user reviewed and accepted Building block 4 on 2026-07-22. The independent IMU
row comparison and longer-case resource profile remain available as optional
future revalidation rather than recorded acceptance evidence.
