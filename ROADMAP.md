# ROS 2 Bag Analyser — Roadmap

## 1. Status

Building block 1 is complete and was accepted by the user on 2026-07-21.
Building block 2 and its audit corrections are complete and were accepted by
the user on 2026-07-21. It adds the two remaining V0 PostgreSQL tables,
front-preview processor, serial worker, validated artifact publication,
request/poll/range API, and initial global timeline. Its synthetic,
ROS-message, PostgreSQL, browser, and approved real-archive acceptance evidence
is recorded below. Building block 3 implementation was approved on 2026-07-21,
completed with automated verification on 2026-07-22, and reviewed and accepted
by the user on 2026-07-22. Building block 4 implementation was approved on
2026-07-22 for the exact synchronized IMU graph boundary below. Its
implementation, confirmed audit corrections, automated verification, and
approved real-archive handoff were completed, and the user reviewed and
accepted it on 2026-07-22. Building block 5 has not started.

This roadmap defines V0 scope and order. Building block 1 implementation was
explicitly approved on 2026-07-20. That approval does not grant work on later
building blocks or access to the real archive outside a separately approved
acceptance run.

`ROADMAP.md` owns block scope, visible acceptance, and minimum testing. The
other governing documents must be aligned with it before implementation.

## 2. V0 objective

V0 proves that the application can:

1. Scan the six known recording folders.
2. Show metadata and identify the damaged ROS database.
3. Generate and reuse a front-camera preview.
4. Synchronize the timestamped top-down camera with the front camera.
5. Show one IMU graph on the same timeline.

V0 uses a small PostgreSQL catalog and one serial worker. It is a mentor
demonstration, not a production operations platform.

## 3. Mentor and acceptance matrix

Real-data cases are selected through configuration and recorded in acceptance
notes; application logic must not hard-code their labels or filenames.

| Case | Purpose | Required evidence |
|---|---|---|
| All six | Catalog | Six unique rows; five readable; one damaged; idempotent rescan |
| Short healthy | Main flow | Reusable front/top-down/IMU output on one transport |
| Long healthy | Final scale acceptance | Bounded work, sync, seeks, responsive graph |
| Damaged | Honest failure | Useful diagnosis; no crash; unavailable work creates no job |
| Original archive | Safety | Names, sizes, and modification times remain unchanged |

The short case is used routinely. The complete longer case is a final opt-in
acceptance run, never a routine development test, automated suite, or generic
CI requirement.

## 4. Rules for every block

- Originals are strictly read-only and are never repaired or reindexed.
- Scanning and artifact processing remain separate operations.
- Expensive processing runs outside normal HTTP requests in one serial worker.
- Reuse requires a matching source, processor, configuration, and output
  identity.
- All streams follow the shared bag-relative time model defined in
  `ARCHITECTURE.md`.
- `unavailable` means prerequisites prevent work and no job is created;
  `failed` means attempted processing ended with an error.
- Each block receives user review before the next begins.

## 5. Building block 1 — Archive catalog and bag table

**Status:** Completed and user-accepted on 2026-07-21

### Goal

Deliver an independently testable read-only scanner, small persistent catalog,
thin API, browser table, and recording detail view.

### Included

- Configure one archive root, one separate derived root, and PostgreSQL.
- Discover direct recording folders and treat each as one logical recording.
- Parse `metadata.yaml` and inventory expected source files by safe relative
  path, role, size, and modification time.
- Perform bounded read-only checks that distinguish the five readable ROS
  databases from the damaged database without full integrity scans.
- Persist only:
  - `recordings`, uniquely keyed by archive-relative folder, with table/detail
    metadata, ROS readability, safe diagnostic, and source signature;
  - `source_components`, keyed by recording and role, with bounded file
    facts and component condition.
- Keep topic count on the recording; processors later validate configured topics.
- Apply completed scan results transactionally and make unchanged rescans
  idempotent.
- Keep the scanner callable without FastAPI, ORM objects, or a worker.
- Provide minimal rescan, list, and detail API operations.
- Show metadata, ROS readability, diagnostics, and companion presence in the UI.
- Continue scanning when one folder is damaged.

### Excluded

- Preview, video, telemetry, artifacts, processing jobs, and artifact columns.
- Scan jobs/history, `scan_runs`, audit history, tombstones, missing-history
  retention, removal reconciliation, and rename reconciliation.
- Full database/message/video reads, top-down validation, and topic capability
  classification.
- Multiple roots, uploads, watchers, and additional bag formats.

### Visible acceptance

- **Rescan** shows exactly six rows: five readable and one specifically damaged.
- Healthy and damaged detail views show useful metadata and components.
- A second rescan still shows six rows and starts no processing.
- Restarting the application reloads the PostgreSQL catalog.

### Minimum tests

- Tiny valid and truncated/malformed fixtures cover metadata, bounded health,
  safe paths, and failure isolation.
- Configuration tests reject overlapping roots and path escapes.
- One PostgreSQL test applies the same result twice and proves stable row counts.
- Minimal API tests cover rescan result, list, and detail.
- One opt-in real scan proves six/five/one and an unchanged archive inventory.

## 6. Building block 2 — Front-camera preview and initial timeline

**Status:** Completed and user-accepted on 2026-07-21

**Dependency:** Building block 1 reviewed and accepted

### Goal

Generate and reuse one browser-playable front preview without blocking ordinary
API traffic, then control it with the first global timeline.

### Included

- Configure one preferred topic and preview output profile.
- Require `sensor_msgs/msg/Image`; initially support the observed `bgr8` format.
- Validate type, dimensions, step, and payload; decode with bounded memory.
- Build frame time from ROS record timestamps and generate seekable browser media.
- Add a minimal `artifacts` table containing only validated ready output, its
  cache identity, contained path, and required timing/manifest data.
- Add a minimal `jobs` table with artifact identity, timestamps, safe error, and
  `queued`, `running`, `succeeded`, or `failed` state.
- Use one serial worker and prevent duplicate active jobs per artifact identity.
- Reuse a matching ready artifact; a mismatch is a cache miss, not stale history.
- Validate temporary output before atomic publication where practical.
- Treat interrupted work as a visible failure and require an explicit new request.
- Provide request, polling, metadata, and byte-range media API operations.
- Show `not requested`, `queued/processing`, `ready`, `failed`, and `unavailable`.
- Add the front player and elapsed-time play, pause, and seek controls.

### Excluded

- Top-down media, telemetry, and scan jobs.
- Leases, heartbeats, automatic retry, durable phases, priorities, cancellation,
  multiple workers, and distributed coordination.
- Stale-artifact history, audit retention, and automated cleanup.
- Arbitrary topics/encodings, adaptive streaming, and production scheduling.

### Visible acceptance

- The short healthy case processes in the worker and remains playable/seekable.
- Reload, restart, and rescan reuse its completed preview.
- A repeated request creates no duplicate active job or ready artifact.
- The damaged case reports unavailable and creates no job.
- One opt-in longer-case run records duration, output size, and bounded memory.

### Minimum tests

- Tiny image sequences cover selection, validation, record-time mapping, and
  streaming rather than frame accumulation; one malformed case fails safely.
- Cache tests cover reuse and a relevant-input cache miss.
- PostgreSQL tests cover one active job and one ready artifact per identity.
- One interrupted-job test proves `failed`, no ready artifact, and an explicit
  new request can run safely.
- Publication tests prove partial output cannot become ready.
- Minimal API tests cover request, poll, unavailable, ready, and byte ranges.
- Short and opt-in longer real checks prove playback/reuse and source immutability.

### Acceptance evidence — 2026-07-21

- The routine suite passed with 144 tests and 12 environment-specific skips;
  the isolated generated ROS-message test passed; and all 10 PostgreSQL tests
  passed against a disposable PostgreSQL 14 database.
- PostgreSQL 14 exposed and verified corrections for a reserved catalog-query
  alias and version-specific predicate parentheses. Regression coverage was
  added, and the final PostgreSQL suite passed.
- The approved short figure-eight recording produced 3,051 frames and an
  84,118,694-byte preview in 305.742 seconds. The user confirmed playback;
  byte-range delivery, representative seeking, restart persistence, rescan and
  repeated-request reuse all passed.
- The approved 758.739-second longer recording produced a 482,413,143-byte
  preview in 2,011.547 seconds. Peak worker RSS was 163,520 kB with no swap, and
  representative seeking passed.
- Reuse left exactly two succeeded jobs and two ready artifacts. The damaged
  recording remained `unavailable` and created no job or artifact.
- During long processing, ordinary catalog and completed-preview requests
  remained responsive, partial output stayed unpublished, and the temporary
  job workspace was empty after atomic publication.
- The archive still contained exactly six directories and 24 files. All 24
  source components retained their recorded sizes and nanosecond modification
  times, with no extra files or sidecars.
- Reported short-preview stutters were traced read-only to existing ROS record
  timestamp gaps of approximately 0.245–0.422 seconds. The source and MP4 each
  contained exactly 3,051 frames with the same timestamp-interval sequence;
  camera header stamps remained mostly near 0.05 seconds. Preserving these
  visible holds is the accepted record-clock synchronization behavior.

## 7. Building block 3 — Top-down camera and dual-video synchronization

**Status:** Completed and user-accepted on 2026-07-22

**Dependency:** Building block 2 reviewed and accepted

### Goal

Add the known AVI/CSV pair and make both cameras follow one honest bag-relative
timeline.

### Included

- Resolve AVI/CSV components catalogued in block 1.
- Validate timestamp column/parsing/order, AVI decoding/frame count, and one CSV
  timestamp per decoded frame.
- Convert CSV Unix timestamps to bag-relative integer nanoseconds.
- Generate browser media whose timing follows CSV elapsed time, not AVI rate.
- Reuse block 2's worker, cache, temporary output, and publication behavior.
- Store only required provenance, start/end, coverage, and warnings.
- Display both panes; one transport controls play, pause, and seek.
- Correct observable cumulative drift against the global clock.
- Show an explicit outside-coverage player state.
- Preserve healthy AVI/CSV facts for the damaged case while synchronized media
  remains unavailable when its bag origin is untrustworthy.

### Excluded

- Telemetry; manual/CV alignment; extra cameras; arbitrary pairing UI; live
  streaming; frame export; playback-rate controls; sync dashboards.
- New job states, retries, leases, or distributed coordination.

### Visible acceptance

- The short case plays, pauses, and seeks both cameras at matching bag time.
- Top-down playback visibly follows CSV timing and honest coverage.
- Reload reuses both artifacts.
- The longer case sustains playback and seeks near start, middle, and end without
  accumulating visible offset.
- The damaged case shows companions but synchronized media is unavailable.

### Minimum tests

- Pure tests cover CSV precision/order, duplicate time, frame-count mismatch,
  bag-relative conversion, coverage, and global-to-media mapping.
- One tiny AVI/CSV fixture covers successful conversion and one invalid case.
- Short real checks cover multiple seeks and sustained playback.
- One opt-in longer check covers drift/coverage; damaged returns unavailable.
- Before/after inventories prove AVI/CSV sources unchanged.

### Implementation evidence — automated verification complete

- On 2026-07-22, the routine non-PostgreSQL, non-ROS, non-real-archive suite
  passed with 177 tests and 13 environment-specific deselections.
- The isolated generated ROS-message regression test passed in the sourced ROS
  2 Humble environment.
- All 11 PostgreSQL tests passed against a disposable PostgreSQL 16 database,
  including the four-table migration and isolated front/top-down processing
  identities. The browser JavaScript passed a Node.js syntax check.
- Synthetic top-down coverage includes exact nanosecond CSV parsing, irregular
  CSV-driven MP4 PTS, full encoded-packet PTS comparison, pre-decode dimension
  limits, frame-count and ordering failures, source identity/inventory
  preservation, cache and unavailable behavior, worker dispatch, contained
  publication, range delivery, and the served two-pane/one-clock browser
  contract. The browser contract also covers invalidating interrupted media
  play attempts without stopping the shared clock.
- [README.md](README.md) contains the step-by-step opt-in Building block 3
  browser, longer-recording, performance, and before/after inventory procedure.
- Manual browser and real-archive checks were not required for the user's
  acceptance and remain optional future revalidation requiring separate opt-in
  approval. The real archive was not accessed during implementation or
  automated verification.

## 8. Building block 4 — Synchronized IMU graph

**Status:** Completed and user-accepted on 2026-07-22

**Dependency:** Building block 3 reviewed and accepted

### Goal

Add one configured IMU angular-velocity series whose graph cursor follows the
same timeline as both cameras.

### Included

- Configure one `sensor_msgs/msg/Imu` topic and component, initially
  `angular_velocity.z`.
- Use `IMU angular_velocity.z (rad/s)` until rover coordinates justify yaw rate.
- Extract values using ROS record timestamps and bag-relative integer nanoseconds.
- Reject or clearly represent non-finite values.
- Measure the browser payload and rendering; if reduction is needed, use a
  bounded method preserving order, coverage bounds, and important extrema.
- Store the derived series outside PostgreSQL and reuse the existing worker/cache.
- Render one graph with label, units, provenance, coverage, and current value.
- Drive its cursor from global play, pause, and seek.
- Return unavailable without a job when topic/type/time prerequisites are absent.

### Excluded

- Arbitrary signals, expressions, multiple graphs, dashboards, custom messages,
  click-to-seek, graph-owned time, embedded PlotJuggler, LiDAR, GPS, and maps.
- New worker coordination or a general telemetry platform.

### Visible acceptance

- The short case shows a correctly labelled graph whose value/cursor follows
  play and seek; reload reuses the series.
- The longer case loads and scrubs responsively.
- The damaged case reports unavailable without creating a job.

### Minimum tests

- Generated IMU messages cover selection, field, units, record-time mapping,
  non-finite values, and missing prerequisites.
- If reduction is implemented, tests preserve ordered time, bounds, a known
  peak, and a trough.
- Timeline tests prove the graph uses the global clock.
- Short real values/timestamps are compared with independent ROS inspection.
- One opt-in longer rendering check and source inventory complete acceptance.

### Implementation evidence — 2026-07-22

- The routine non-PostgreSQL, non-ROS, non-real-archive suite passed with 207
  tests and 14 environment-specific deselections. Focused processor, artifact,
  service, worker, and API suites cover topic/type prerequisites, immutable
  source access, bounded row streaming, record-time mapping, non-finite gaps,
  duplicates, cache reuse/replacement, contained atomic publication, sanitized
  failures, one-worker dispatch, range delivery, and stale artifact URLs.
- Two generated-message ROS tests passed in the sourced ROS 2 Humble
  environment, including real `sensor_msgs/msg/Imu` CDR deserialization and
  proof that record time rather than header time drives `angular_velocity.z`.
- JavaScript syntax and seven dependency-free browser tests passed in Node.js:
  four pure timeline/series contracts and three runtime tests that execute the
  shipped browser script. The runtime coverage proves play, pause, animation
  ticks, and slider seeks drive both camera players and the IMU from one clock;
  narrow Canvas coordinates and isolated finite samples render correctly; and
  a render-time failure leaves an attached diagnostic and retry action. A
  reproducible 76,000-sample profile measured a 2.76 MB JSON payload, 50 ms
  parse/validation, 40 ms trace transformation, and 5.1 ms for 10,000
  binary-search cursor lookups. Headless Edge measured a 41 ms parse and 6 ms
  native Canvas draw, so V0 records `reduction: none` and preserves all samples.
- The PostgreSQL migration keeps exactly the accepted four tables and adds only
  the isolated `imu_series` artifact/job kind. All 18 repository integration
  tests passed against a disposable PostgreSQL 14 database, including the
  four-table migration and separated front/top-down/IMU processing identities.
- The shared artifact-store diagnostics now describe generic artifacts rather
  than calling IMU output a preview, with focused regression coverage.
- [README.md](README.md) documents configuration, exact signal identity and
  policies, plus the separately opt-in short/long/damaged browser, independent
  value comparison, performance, reuse, and source-inventory procedure. The
  real archive was not accessed during implementation.

### Acceptance evidence — 2026-07-22

- During the explicitly approved final handoff, the application used
  `/mnt/d/Rosbags`, a separate derived root, and the configured
  `/kuupkulgur_v1/sensors/imu0/raw_data` standard IMU topic with one API and
  exactly one serial worker.
- The opt-in catalog acceptance test and live rescan both found six recordings,
  five readable bags, and the expected damaged bag. Scanning created no jobs or
  artifacts, and PostgreSQL retained exactly the accepted four tables.
- The complete archive contained 24 files totalling 114,464,854,725 bytes. Its
  before/after names, kinds, sizes, and modification-time inventory digest was
  unchanged at
  `edfaf0db862d846684cfa7a8133bcbba6c1142ba9c74092ca2d45e99cfe2c5bf`.
- The user reviewed and accepted Building block 4. The independent IMU-row
  comparison and longer-case resource profile were not separately recorded and
  remain optional future revalidation rather than completed evidence.

## 9. Building block 5 — V0 integration and mentor readiness

**Status:** Planned

**Dependency:** Building blocks 1–4 reviewed and accepted

### Goal

Prove the accepted slices work together in a clean mentor demonstration without
adding another infrastructure subsystem.

### Included

- Catalog and inspect all six recordings.
- Run the complete synchronized flow on the selected short healthy case.
- Run the opt-in longer scale smoke across preview completion, sustained sync,
  representative seeks, and graph responsiveness.
- Verify damaged diagnostics and unavailable ROS-dependent actions.
- Verify completed-artifact reuse after reload, restart, and rescan.
- Verify repeated actions do not duplicate active jobs or ready artifacts.
- Verify ordinary catalog/detail traffic remains responsive during processing.
- Polish only V0's loading, empty, processing, unavailable, ready, and failed UI.
- Complete setup, configuration, worker, acceptance, limitations, performance,
  and troubleshooting notes.
- Perform one final lightweight inventory of the complete archive.

### Excluded

- Processing every artifact for all five readable recordings.
- Leases, heartbeats, auto retry, priorities, cancellation, multiple workers,
  stale/scan audit history, retention, cleanup, chaos/load tests, and deployment.
- Active-job crash survival beyond clear interrupted failure and explicit retry.
- Any deferred product feature.

### Visible acceptance

- A documented clean setup runs the acceptance matrix without code changes.
- All six catalog rows, the short full flow, the longer smoke, and damaged
  behavior pass.
- The UI remains responsive and statuses remain truthful during processing.
- The final archive inventory matches the initial inventory.

### Minimum tests

- Run the accumulated focused unit and PostgreSQL/API suite from clean setup.
- One integration check proves ordinary API reads work during a worker job.
- Execute the acceptance matrix once and record browser checks for play, seek,
  coverage, reuse, drift, graph cursor, and damaged behavior.
- Record limitations instead of expanding V0 to solve deferred operations work.

## 10. Final V0 gate

V0 is complete only when:

- The acceptance matrix passes for all six, the short, the final opt-in long,
  and the damaged cases.
- The scanner remains bounded, read-only, independent, and separate from
  artifact processing.
- PostgreSQL contains only small V0 catalog, artifact, and job metadata.
- Matching completed artifacts are reusable and partial work is never ready.
- Unavailable prerequisites and failed processing remain distinct.
- ROS record time aligns the front camera and IMU; CSV time aligns top-down
  frames; every stream maps to the same bag-relative timeline.
- Focused tests pass, real checks remain opt-in, and originals are unchanged.
- Setup, evidence, limitations, and governing documents are truthful.
- The user reviews and approves the complete result.

## 11. Deferred backlog

### Catalog and formats

- Multiple roots, NAS/watchers, uploads, scan/audit history, tombstones, rename
  reconciliation, ROS 1, MCAP, compression, split bags, and repair tools.

### Jobs and artifacts

- Leases, heartbeats, auto retry, priorities, quotas, cancellation, multiple
  workers, Redis, brokers, active-job recovery, retention, cleanup, object
  storage, and production migration.

### Processing and visualization

- Additional cameras/topics/encodings, quality controls, adaptive streaming,
  clips, thumbnails, exports, adjustable synchronization, multiple/custom
  telemetry, dashboards, LiDAR, GPS, and maps.

### Product and operations

- Authentication, users, annotations, comments, saved/shared views, deployment,
  monitoring, alerts, backups, disaster recovery, and public exposure.
