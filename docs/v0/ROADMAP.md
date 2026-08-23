# ROS 2 Bag Analyser — V0 Roadmap

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
accepted it on 2026-07-22. Building block 5 implementation was approved on
2026-07-22 for the exact V0 integration and mentor-readiness boundary below.
Implementation and automated verification were completed on 2026-07-22. The
user approved, and the explicit opt-in real-archive acceptance matrix was
completed, on 2026-07-22. The user reviewed and accepted Building block 5 that
day, completing the mentor-facing V0. Building block 6 implementation was
approved on 2026-07-29 for the exact frontend-only visual migration boundary
below. Its implementation and automated and synthetic-browser verification
were completed on 2026-07-29 and are awaiting user review.
Building block 7 was approved, implemented, and verified on 2026-07-30 and is
awaiting user review. Building block 8 was approved, implemented, and verified
on 2026-07-30 for the exact common IMU bundle, graph seeking, and cursor
rendering boundary below. It is awaiting user review and its separately
approved real-archive acceptance.

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

**Status:** Completed and user-accepted on 2026-07-22

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

### Implementation evidence — 2026-07-22

- A fresh virtual environment installed the locked requirements and editable
  package successfully; `pip check` reported no broken requirements, and all
  three application entry points were executable.
- The accumulated routine suite passed with 207 tests and 15 opt-in tests
  deselected. The PostgreSQL suite passed with 12 tests, and the ROS-message
  suite passed with 2 tests.
- The browser suite passed all 12 tests on Node.js 22.22.1, including explicit
  loading, empty, processing, unavailable, failed, ready, retry, provenance,
  coverage, shared-clock, and partial-consumer-failure behavior.
- A PostgreSQL/ASGI integration test ran the real serial worker against an
  event-controlled processor and proved catalog and detail reads complete while
  its job remains active.
- The 76,000-sample browser performance fixture parsed and transformed in about
  88 ms total on this development host; 10,000 timeline lookups took about
  5.5 ms. These are development observations, not deployment guarantees.
- `README.md` documents clean setup, worker operation, the all-six/short/reuse/
  damaged/long acceptance matrix, truthful UI checks, troubleshooting, and V0
  limitations.
- No real archive was accessed during implementation or automated verification.
  It was accessed only after the user's explicit opt-in for the separately
  recorded acceptance evidence below.

### Acceptance evidence — 2026-07-22

- The explicitly approved acceptance used `/mnt/d/Rosbags`, a new empty derived
  root, a new dedicated PostgreSQL 14 database, one API, and exactly one serial
  worker. The configured front and IMU topics remained
  `/kuupkulgur_v1/sensors/front_camera/image_raw` and
  `/kuupkulgur_v1/sensors/imu0/raw_data`; a second worker exited on the advisory
  lock as required.
- The opt-in catalog test and repeated live rescans found six stable recording
  IDs, five readable bags, and the expected damaged
  `2025_11_04_plain_figure8_spotlight_0.db3`. Scanning left 24 source-component
  rows, no jobs or artifacts, and exactly the accepted four PostgreSQL tables.
- On the short `2025_11_04_figure8` recording, front processing completed in
  330.647 seconds at 84,118,694 bytes, top-down in 6.948 seconds at 13,443,307
  bytes, and IMU in 16.441 seconds at 15,184 samples and 544,610 bytes. The
  videos validated as H.264 with 3,051 and 555 frames; start/middle/end range
  requests returned correct `206` responses.
- Immutable read-only SQLite inspection independently matched the short IMU
  artifact's first, middle, and last ROS record timestamps and
  `angular_velocity.z` values. The API and live UI reported measured coverage,
  correct ROS/CSV provenance, units, warnings, and `reduction: none`.
- Headless Edge exercised the shipped short page with the real artifacts.
  Global start, individual coverage entry, all-consumer coverage, slider seek,
  end coverage, sustained playback, seek while playing, and pause all passed.
  Both cameras mapped to the global clock, the IMU cursor/value followed it,
  out-of-coverage consumers hid or cleared independently, and observed mapped
  video drift stayed below 0.5 seconds.
- The damaged recording kept its AVI/CSV facts visible while front, synchronized
  top-down, and IMU requests returned distinct `unavailable` diagnostics. The
  repeated requests created no job or artifact.
- On the 758.739-second `2025_11_04_PE_1_4_plain_slow` scale case, front
  processing completed in 2,224.468 seconds at 482,413,143 bytes, top-down in
  33.707 seconds at 68,078,248 bytes, and IMU in 15.177 seconds at 75,729
  samples and 2,767,114 bytes. The profiled worker used 162,144 kB peak RSS and
  no swap over 34:42 wall time.
- The long videos validated as H.264 with 15,171 and 2,868 frames. The IMU JSON
  parsed in 33 ms on the development host; live Edge loaded and drew all 75,729
  samples, and midpoint/end/playing seeks, coverage, playback, graph cursor, and
  pause checks passed. Catalog/detail responses remained near 12 ms during the
  long render, with state and completed-media checks between 38 and 52 ms.
- Repeated requests, rescans, API restarts, and a worker restart reused artifact
  IDs 1–6. PostgreSQL finished with exactly six succeeded jobs, six artifacts,
  no active job, and an empty temporary work directory.
- The complete archive retained 31 inventory entries and 24 files totalling
  114,464,854,725 bytes. Exact before/after relative names, kinds, sizes, and
  modification times matched at digest
  `edfaf0db862d846684cfa7a8133bcbba6c1142ba9c74092ca2d45e99cfe2c5bf`.
  No source was modified and every generated file remained outside the archive.

## 10. Final V0 gate

**Status:** Passed and user-approved on 2026-07-22

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

## 11. Building block 6 — Reference UI migration

**Status:** Implementation and verification completed on 2026-07-29; awaiting
user review

**Dependency:** Building blocks 1–5 and the V0 gate reviewed and accepted

### Goal

Apply the accepted visual design from the final served frontend of the simple
learning project to this PostgreSQL/worker application without changing its
backend, processing, storage, artifact, safety, or synchronization contracts.

The visual reference is the served `simple_bag_viewer/static` HTML, CSS, and
JavaScript in the separately inspected `Ros2BagAnalyser` repository. Its
unserved `new ui` mock is design provenance only and is not the functional
source.

### Included

- Port the dark top bar, brand, breadcrumb, navigation rail, database table,
  analyzer grid, media panes, telemetry pane, global timeline, metadata
  sidebar, inline SVG icons, status badges, and responsive layout.
- Keep `/` and `/recordings/{id}` as refreshable, bookmarkable routes using
  current numeric catalog IDs.
- Keep startup catalog loading separate from the explicit read-only rescan and
  retain the displayed catalog when a rescan fails.
- Map the current `not_requested`, `queued`, `processing`, `unavailable`,
  `failed`, and `ready` artifact states into the new presentation.
- Preserve independent front, top-down, and IMU request, polling, retry, and
  artifact-delivery behavior.
- Display current recording metadata and source-component facts in the
  reference-style metadata sidebar without inventing unavailable topic rows.
- Preserve the browser-owned full-recording timeline, 100-millisecond media
  correction, measured coverage, independent consumer failure, and current IMU
  timestamp, duplicate, null-gap, and current-value rules.
- Retain keyboard access, visible focus, skip navigation, live/busy semantics,
  safe DOM construction, sanitized diagnostics, and reduced-motion behavior.
- Update focused static/API and dependency-free browser tests for the new DOM.
- Document the intentional differences between visual parity and the discarded
  prototype's synchronous behavior.

### Excluded

- Database migrations, new tables, repository changes, new API endpoints or
  response fields, new processing kinds, or worker changes.
- Topic-detail persistence, route-time source reads, per-row detail requests,
  or browser access to source paths.
- Synchronous generation, front-first top-down gating, a front-video master
  clock, or direct generated-file URLs.
- A changed drift threshold, false boundary-frame coverage, graph-owned seeking,
  playback-rate controls, extra graphs, arbitrary telemetry, or later-roadmap
  features.
- A frontend framework, runtime package manager, icon/chart library, external
  asset CDN, or bundled font.
- Real-archive access during implementation or routine verification.

### Visible acceptance

- The archive and analyzer views visibly match the reference shell at desktop
  size while presenting only truthful current-system data and states.
- Initial load reads the saved catalog without scanning; explicit rescan,
  empty, loading, retained-table failure, and retry states remain clear.
- A recording URL can be opened, refreshed, left, and revisited with real
  browser navigation.
- Front, top-down, and IMU work can be requested independently and visibly move
  through the one-worker states without blocking ordinary catalog use.
- One global play/pause/seek control drives every ready consumer across the full
  bag duration; out-of-coverage and failed consumers do not stop the others.
- The current IMU label, units, gaps, cursor, value, provenance, and coverage
  remain accurate.
- The layout remains usable at the documented desktop, tablet, and narrow
  breakpoints with keyboard-visible state and focus.

### Minimum tests

- Static delivery tests cover the new shell, current asset routes, package
  data, CSP, and security headers.
- Browser tests cover catalog load/rescan/failure retention, numeric-ID
  navigation, truthful artifact states, independent request/poll flows, and
  status/media/data retries.
- Existing runtime tests continue to prove the monotonic global clock, play,
  pause, seek, end, measured coverage, drift correction, and isolated consumer
  failure.
- Existing IMU tests continue to prove decimal nanoseconds, duplicate-last
  lookup, null gaps, full-duration cursor mapping, and render failure recovery.
- The accumulated routine suite and disposable PostgreSQL suite pass without a
  migration or table-count change.
- Manual checks cover 1600×900, 1366×768, 1024×768, the 901/900-pixel layout
  boundary, 600×800, and 320×800 plus keyboard focus, 200% zoom, and reduced
  motion.
- Real-archive evidence is not required for this frontend-only block. Any later
  real-data revalidation remains separately opt-in.

### Implementation and verification evidence

- The fixed HTML shell, CSS visual system, and dependency-free browser runtime
  were migrated while retaining the existing API routes and response fields.
  No persistence, migration, repository, processor, worker, or artifact-store
  application file changed.
- Focused browser tests cover saved catalog loading and failed-rescan
  retention, numeric-ID links, all six artifact states, independent retries,
  shared play/pause/seek, measured coverage, drift correction, isolated media
  failure, narrow graph drawing, and graph-data failure recovery.
- On 2026-07-29, 207 routine tests, 2 ROS-message tests, 12 disposable
  PostgreSQL tests, 4 IMU JavaScript tests, and 8 browser-runtime JavaScript
  tests passed. The PostgreSQL migration test continued to prove exactly four
  domain tables.
- A synthetic localhost API fixture was rendered in Chrome at 1600×900,
  1366×768, 1024×768, 901×800, 900×800, 600×800, and an exact emulated
  320×800 CSS viewport. The 901/900 transition, single-column narrow layout,
  full catalog table, analyzer panes, and metadata scrolling were inspected.
- Browser-protocol checks at 320 pixels reported no horizontal document
  overflow and a visible keyboard-focused skip link. A 200-percent-equivalent
  viewport used the stacked layout. Reduced-motion emulation matched the media
  query, reduced animation duration, and disabled smooth scrolling.
- The original archive was not accessed. The browser fixture used only
  synthetic metadata, and no real-data acceptance was required for this block.

## 12. Building block 7 — One-command local operation

**Status:** Implemented and verified on 2026-07-30; awaiting user review

**Dependency:** Accepted V0 services and the Building block 6 frontend

### Goal

Make the complete local application consistently available against the real
read-only development archive without requiring a Codex prompt or reconstructing
its environment for each launch.

### Included

- Reuse the installed automatic Windows PostgreSQL 16 service, dedicated
  `rosbag_analyser` database and user, four accepted tables, and existing
  password-protected local configuration.
- Keep `/mnt/d/Rosbags` as the configured source and
  `/home/kardo/.local/share/rosbag-analyser/derived` as the separate generated
  artifact root.
- Add one version-controlled `./dev` command with `start`, `open`, `status`,
  `logs`, `restart`, `stop`, `migrate`, and explicit `rescan` operations.
- Add version-controlled API/worker launch wrappers and a locked local process
  supervisor, with validated PID files, private logs, exactly one serial worker,
  and clear restart/stop behavior.
- Install a Windows desktop shortcut that starts the application, waits for
  health, and opens the browser without depending on a WSL user-service bus.
- Make starts idempotent: an already healthy application returns immediately,
  while a stopped application migrates and starts without scanning.
- Validate that configuration files are private, roots exist and do not
  overlap, PostgreSQL is reachable, and the HTTP API becomes healthy.
- Keep scanning explicit. `./dev rescan` performs the accepted bounded,
  read-only scan; ordinary start and shortcut use the saved catalog.
- Document setup, commands, troubleshooting, local file ownership, and the
  difference between starting and rescanning.

### Excluded

- API, schema, repository, processor, job, artifact, synchronization, or
  frontend behavior changes.
- Automatic startup rescans, filesystem watchers, source repair, generated
  files in the archive, or direct browser source access.
- A second worker, distributed processing, containers, production deployment,
  remote/public exposure, authentication, or new runtime dependencies.
- Committing passwords, database URLs, `.env` files, machine-specific service
  state, derived artifacts, or rosbags.

### Visible acceptance

- Double-clicking **ROS 2 Bag Analyser** on the Windows desktop opens the real
  app without a Codex prompt.
- `./dev start` is one command, is safe to repeat, and presents six saved real
  recordings without scanning.
- `./dev status`, `./dev logs`, `./dev restart`, and `./dev stop` give an
  understandable local lifecycle.
- `./dev rescan` explicitly returns six recordings, five readable and one
  damaged, while the archive inventory remains byte-for-byte identical at the
  names/kinds/sizes/modification-time manifest level.
- One validated API and one validated serial-worker process run under the local
  launcher and reuse existing ready artifacts.

### Minimum tests

- Shell syntax and focused static tests cover the command surface, private
  configuration validation, root separation, health waiting, explicit rescan,
  PID validation, lifecycle locking, and shortcut arguments.
- Installation and repeated starts are idempotent, and both managed processes
  and HTTP are healthy.
- Live API checks cover `/`, `/api/recordings`, one real detail route, and
  service restart.
- One explicit real rescan proves six/five/one with an unchanged 31-entry,
  24-file archive inventory digest.
- Existing routine, ROS, PostgreSQL, and browser suites remain green because
  this block does not change application behavior.

### Implementation and verification evidence

- `./dev` now validates the private configuration and non-overlapping roots,
  migrates the persistent database, and supervises one exact project API and
  one exact project worker through private PID/log state. A lifecycle lock
  prevents concurrent shortcut clicks from starting duplicates; child
  processes do not inherit that lock.
- WSL's user-service D-Bus proved unavailable across a fresh Windows launch, so
  the accepted implementation uses detached, command-validated local processes
  instead. This keeps the shortcut independent of both Codex and that
  machine-specific service-bus failure.
- The installed Windows shortcut launched the complete application from a
  stopped state. A repeated `./dev start` reused the same API and worker PIDs
  and returned in 89 milliseconds. Controlled restart and stop/start checks
  left exactly one API and one serial worker healthy.
- The persistent PostgreSQL database contains exactly `artifacts`, `jobs`,
  `recordings`, and `source_components`. Startup reused six saved real
  recording rows without scanning; `/`, `/api/recordings`, and a real detail
  route returned HTTP 200.
- The separately approved explicit rescan returned six recordings, five
  readable and one damaged with the expected `sqlite_size_mismatch`
  diagnostic. Its bounded scan completed in 292 milliseconds.
- Before and after the real-data checks, the read-only source manifest contained
  31 entries, 24 files, and six recording directories with the identical
  names/kinds/sizes/modification-time SHA-256 digest
  `edfaf0db862d846684cfa7a8133bcbba6c1142ba9c74092ca2d45e99cfe2c5bf`.
- On 2026-07-30, shell syntax and five launcher tests passed, followed by 212
  routine tests, two ROS-message tests, 12 disposable PostgreSQL tests, four
  IMU JavaScript tests, and eight browser-runtime JavaScript tests.

## 13. Building block 8 — Common IMU channels and interactive graph seeking

**Status:** Implemented and automatically verified on 2026-07-30; awaiting
user review and separately approved real-archive acceptance

**Dependency:** The current Building block 6 frontend and Building block 7 local
operation baseline

### Goal

Expose every audited, universally available raw IMU motion component through
one selectable graph, make that graph an additional seek surface for the
existing global clock, and remove visible cursor-line flicker without changing
the accepted processing or synchronization model.

### Included

- Keep the configured common CDR `sensor_msgs/msg/Imu` topic.
- Extract `angular_velocity.{x,y,z}` and
  `linear_acceleration.{x,y,z}` in one immutable sequential source pass.
- Publish one bounded schema-version-2 `imu_series` artifact containing shared
  record timestamps and six fixed value columns.
- Preserve decimal bag-relative nanoseconds, source order, duplicate-last
  lookup, per-component non-finite `null` gaps, measured coverage, and no
  reduction unless measured performance requires it.
- Reuse the existing `imu_series` kind, four PostgreSQL tables, one serial
  worker, request/state routes, and identity-specific range-delivered JSON URL.
- Add one accessible dropdown to the existing telemetry pane; switching changes
  the trace, exact label, units, scale, current value, and per-series facts
  without another request or job.
- Allow pointer, touch, and keyboard seeking from the graph while keeping the
  global range input, cameras, selected value, and monotonic playback aligned.
- Keep the trace static between selection/resize events and move a persistent
  cursor overlay with device-pixel-snapped composited translation.

### Excluded

- `cmd_vel`, commanded-motion graphs, arbitrary topics or fields, custom
  encoder/EPS decoding, custom-message dependencies, and topic-detail
  persistence.
- Orientation, Euler angles, derived magnitudes, covariance graphs, Ouster,
  LiDAR, point clouds, GPS, maps, and additional graph panes.
- Graph-local time, pan, zoom, playback-rate controls, a changed camera drift
  threshold, or false boundary-frame coverage.
- A new table, processing kind, worker, frontend framework, chart library, or
  runtime dependency.
- Automatic generation during startup or scan and real-archive processing
  without a separately approved acceptance run.

### Visible acceptance

- Every readable recording offers the same six exact IMU choices after one
  generation; the damaged recording remains unavailable and creates no job.
- `angular_velocity.z` remains the default. Switching all choices is immediate
  and creates no request, job, or additional artifact.
- Labels, units, extrema, null gaps, coverage, and current values match the
  selected raw component.
- Dragging or keyboard-seeking the graph updates the global clock, range input,
  both available cameras, graph cursor, and current value while paused or
  playing, with clamping at both recording boundaries.
- The cursor line and dot remain continuously visible during sustained
  playback, seeking, resize, and selection changes; ordinary clock ticks do not
  redraw the static trace.
- Reload, restart, and rescan reuse the compatible bundle; the accepted
  four-table, one-worker model and existing camera behavior remain intact.
- One separately approved short/long/damaged real acceptance compares values,
  records bundle and browser performance, and proves an unchanged source
  inventory.

### Minimum tests

- Processor tests cover one-pass six-column extraction, exact registry order,
  record time, duplicates, per-column nulls and extrema, all-null isolation,
  malformed CDR, oversized payload/output, source identity, and no source
  sidecars.
- Generated ROS tests serialize all six standard fields while header time
  differs from record time.
- Artifact, worker, repository, and API tests cover schema-version-2 row width,
  per-series facts, cache replacement, atomic publication, identity-bound
  delivery, truthful states, sanitized failures, and exactly four tables.
- Browser tests cover schema parsing, dropdown ordering and switching, current
  lookup, gaps, plot mapping, pointer capture, touch/pointer cancellation,
  keyboard seeking, playback reanchoring, clamping, and synchronized consumers.
- Cursor regression tests prove one persistent overlay, at most one queued
  pointer paint, no trace redraw during clock ticks, and pixel-snapped
  translation at different device-pixel ratios.
- The accumulated routine, ROS-message, disposable PostgreSQL, and JavaScript
  suites pass. Real archive checks remain explicit and opt-in.

### Implementation and verification evidence

- The existing `imu_series` processor now deserializes each standard IMU
  message once and writes the six fixed raw axes beside one decimal
  bag-relative record timestamp in a bounded schema-version-2 JSON bundle.
- Worker validation and the artifact manifest record ordered registry identity,
  per-series finite/null counts and extrema, configured default, duplicate
  policy, measured coverage, and exact source/artifact identity. No table,
  processing kind, worker, route-time source read, or dependency was added.
- The ready API exposes the six literal choices and chooses the first finite
  axis only when the configured default is entirely null. The browser parses
  the bundle once, switches signals locally, and keeps exact labels, units,
  gaps, scale, coverage, and current values aligned.
- The graph now seeks the one full-recording clock through captured
  pointer/touch input or keyboard steps. Seeks clamp, reanchor playback, and
  update the global range input, available cameras, selected value, and
  accessibility state.
- The Canvas trace is static during ordinary clock ticks. One persistent
  cursor overlay moves by device-pixel-snapped `translate3d`; pointer moves are
  coalesced to one animation frame and cancellation releases capture.
- On 2026-07-30, 215 routine tests, two generated ROS-message tests, and 14
  JavaScript graph/runtime tests passed. Both shipped browser scripts passed
  syntax checks. PostgreSQL tests were not rerun because no dedicated
  disposable test database was configured; this block does not change the
  accepted four-table schema or repository operations.
- The synthetic 76,000-row, six-channel browser profile produced a 10.14 MB
  payload, parsed in about 110 milliseconds, transformed the selected trace in
  about 34 milliseconds, and completed 10,000 current-value lookups in about
  6 milliseconds on the development host, so no reduction or new dependency
  was introduced.
- This implementation did not access the original archive. Short, long, and
  damaged real generation, browser review, source-inventory comparison, and
  immutability evidence remain a separate explicit opt-in acceptance run.

## 14. Deferred backlog

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
