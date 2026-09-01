# ROS 2 Bag Analyser — V1 Roadmap

## 1. Status

V1 product and architecture planning was approved on 2026-08-04. The V0 proof
and post-V0 work are preserved in [docs/v0](docs/v0/INDEX.md).

Building block 1 was explicitly accepted on 2026-08-04. Building block 2 was
then explicitly invoked, implemented, verified, and accepted on the same date.
An explicitly approved smooth front-camera corrective slice was implemented
after that acceptance without entering Building block 3. An approved moved-path
catalog corrective slice was then implemented after nested archive moves
exposed retained missing history as duplicate damaged recordings. A separately
approved move-aware artifact-reuse correction now preserves compatible work
across unambiguous folder moves and repairs the already-split development
catalog without rewriting derived files. Building block 3 was explicitly
invoked on 2026-08-16. Its
repository-readiness phase is implemented and locally verified. On 2026-08-23
the user accepted all preceding application and repository-readiness work as
the working pre-overhaul baseline and authorized a Git checkpoint and push.
Prompt 2A, the big UI overhaul and real processing-controls correction, was
approved, invoked, implemented, and synthetically verified on 2026-08-23. It
was reviewed and committed locally as `1c8871b` on 2026-08-24, followed by
read-only CIFS deployment compatibility in `dd28c42`. Controlled live VM
preparation is in progress. On 2026-09-01 the user authorized the narrowly
scoped `front-preview-v3` all-zero-image-header corrective slice; it is
implemented with synthetic verification and awaits review and a separately
approved real-output trial. Release installation, authoritative-source
acceptance, private trial access, reboot persistence, and trial admission remain
incomplete.

V1 has three sequential building blocks:

1. backend preparation and processing operations;
2. reference frontend integration; and
3. TrueNAS VM deployment and trial commissioning.

Each block delivers one reviewable vertical slice and must be accepted before
the next starts.

Prompt 2A is a separately approved corrective overhaul inserted after Building
block 3 repository readiness and before its live commissioning phases. Its
detailed boundary and resolved product decisions are in
`BUILDING_BLOCK_PROMPTS.md`.

## 2. V1 final outcome

V1 is complete when a limited group of engineers can reach the application on
an internal NAS-hosted Ubuntu VM, browse the physical recording hierarchy,
prepare selected recordings, understand the persistent serial queue, and review
real synchronized outputs through the unchanged reference design.

The final trial remains a prototype. Its purpose is structured product feedback,
not public production service guarantees.

## 3. Rules for every block

- Original recordings remain strictly read-only.
- `archive/` remains the visual reference and is not casually edited.
- Scanning does not generate artifacts or jobs.
- Starting services does not scan or prepare recordings.
- Full source processing remains in one serial worker.
- Front, top-down, and IMU remain separate artifact identities.
- Bulk preparation is idempotent and bounded.
- Ready output is identity-compatible and validated; partial output is never
  ready.
- Source unavailability is not recorded as a failed processing attempt.
- Existing timing, coverage, range delivery, IMU null/duplicate, and artifact
  safety contracts remain unless the active block explicitly changes them.
- Routine tests use synthetic fixtures. Real-data and deployment checks are
  explicit, recorded, and source-immutable.
- A block does not imply Git publication authority. The user separately
  authorized the pre-overhaul baseline checkpoint commit and push on
  2026-08-23; later commits, pushes, and remote changes still require explicit
  authority.
- Material scope expansion is documented and reviewed rather than smuggled into
  a convenient change.

## 4. Building block 1 — Backend preparation and processing operations

**Status:** Accepted on 2026-08-04

**Dependency:** Completed V0 backend and accepted V1 documents

### Goal

Expose the complete backend contract required by the Recordings and Processing
views without changing the existing processors, artifact formats, or serial
worker model.

At the end of this block, API-driven clients can browse real physical folders,
read aggregate analysis state, prepare multiple recordings with one request,
and inspect or retry persistent processing work.

### Boundary

This is a backend and API block. It may add the approved catalog-state migration,
repository queries, application services, schemas, routes, focused query
indexes, configuration bounds, and tests. It does not port the new frontend or
deploy the NAS VM.

### Included

#### Catalog and folders

- Replace direct-root-only discovery with bounded recursive physical-folder
  discovery.
- Treat supported metadata directories as recording roots and intermediate
  directories as navigation folders.
- Reject symlink traversal and contain every discovered path.
- Distinguish complete root snapshots from incomplete traversal failures.
- Add a durable successful catalog generation and scan facts.
- Plan and persist one current target per recording/artifact kind during a
  successful scan, including identity or safe unavailability.
- Treat planner/configuration mismatch as rescan-required without route-time
  source reads.
- Reconcile absent recordings as missing only after a complete snapshot.
- Preserve rows, IDs, jobs, artifacts, and history rather than deleting absent
  recordings.
- Keep retained missing history out of ordinary catalog lists, folder nodes,
  summaries, and current scan counts so path moves remain visually singular.
- Expose safe folder nodes, descendant counts, and recording `folder_path`.

#### Aggregate state

- Resolve current front, top-down, and IMU states from catalogued identities.
- Join aggregate state only through the current `preparation_targets`
  projection; do not parse metadata or stat source paths for table rows.
- Add the exact aggregate precedence: processing, queued, failed, ready, then
  not planned.
- Expose precise output facts and a readable/damaged health presentation.
- Produce one bounded catalog response without per-recording browser requests.

#### Bulk preparation

- Add `POST /api/v1/recordings/prepare` with a bounded ordered list of numeric
  IDs.
- Reuse ready artifacts and active jobs.
- Queue missing or explicitly retried current work in stable recording and
  artifact order.
- Preflight all three targets and create no new job for a recording when its
  complete analyzer bundle is unavailable.
- Return per-recording, per-output outcomes and partial failures.
- Preserve advisory-lock and unique-index duplicate prevention under concurrent
  requests.

#### Processing operations

- Add overview and paginated job-query APIs for current work, queue, failures,
  and history.
- Keep API queue positions identical to worker claim order.
- Return safe failure details, completed runtime, output size, and numeric
  recording links.
- Add retry-by-failed-job that recomputes the current identity.
- Report worker online/offline by probing the existing advisory lock without
  mutating worker or jobs.
- Return server time and exact stored timestamps.

#### Estimation

- Add a pure, bounded estimation service using compatible succeeded jobs and
  exact artifact manifest identity.
- Use median seconds per relevant input byte with at least two samples.
- Exclude failed, interrupted, stale, malformed, and missing-artifact samples.
- Return estimate status, predicted total, remaining time, and sample count.
- Return unavailable or exceeded rather than inventing a value.

#### Compatibility and documentation

- Preserve existing V0 state, media, and IMU routes during the transition.
- Update root documents only where implementation evidence or a reviewed
  correction belongs.
- Add migration and rollback notes for the exact schema change.

### Expected implementation areas

- `src/rosbag_analyser/catalog/paths.py`
- `src/rosbag_analyser/catalog/scanner.py`
- `src/rosbag_analyser/catalog/types.py`
- `src/rosbag_analyser/catalog/service.py`
- `src/rosbag_analyser/persistence/catalog_repository.py`
- `src/rosbag_analyser/persistence/processing_repository.py`
- `src/rosbag_analyser/persistence/migrations/`
- `src/rosbag_analyser/config.py`
- new focused preparation and processing-view application modules
- versioned API routes and schemas under `src/rosbag_analyser/api/`
- `src/rosbag_analyser/api/app.py`
- focused unit, PostgreSQL, API, migration, and safety tests

The exact file list may differ after inspection. New modules must represent a
real responsibility rather than a speculative layer.

### Excluded

- Changing front, top-down, or IMU processor output.
- Replacing the artifact cache or adding a combined preparation artifact.
- Multiple workers, priorities, cancellation, reordering, automatic retry,
  leases, or percentage progress.
- Queue completion-time promises for waiting jobs.
- Filesystem watchers, scheduled rescans, uploads, or source writes.
- Frontend visual integration.
- Nginx, system services, VM installation, or public deployment.
- Deleting missing recordings or ready artifacts.

### Implementation sequence

1. Freeze current Git and schema evidence; inspect overlapping user changes.
2. Write nested discovery and complete/incomplete snapshot tests first.
3. Implement recursive discovery without touching persistence.
4. Add and verify the catalog-state migration and safe backfill.
5. Implement transactional generation apply and missing reconciliation.
6. Add bulk current-state repository queries and aggregate resolution.
7. Implement bounded preparation orchestration and concurrency tests.
8. Add processing overview/history queries, stable cursors, and focused indexes.
9. Implement and test the pure estimator.
10. Add versioned schemas/routes and safe validation.
11. Run accumulated processor, worker, PostgreSQL, API, ROS-message, and browser
    regression suites.
12. Run the approved bounded real rescan with before/after source inventory.
13. Record evidence and stop for user review.

### Minimum automated tests

- Recursive folder discovery at root and multiple depths.
- Exact folder paths and direct/descendant counts.
- Symlink, path escape, permission failure, depth bound, entry bound, duplicate
  candidate, malformed metadata, and recording isolation.
- Incomplete scans preserve the previous generation and do not mark rows
  missing.
- Complete scans preserve unchanged IDs and mark unseen rows missing without
  deletion.
- Unambiguous path moves preserve the recording ID, history, private cache
  anchors, and compatible artifacts; ambiguous identical candidates remain
  separate. Retained missing history cannot inflate recording or damaged
  counts.
- Migration from a faithful V0 schema preserves every ID, job, and artifact;
  the first explicit V1 rescan establishes current preparation targets without
  regenerating compatible output.
- Preparation-target planning covers available, unavailable, stale planner,
  scan-generation replacement, and worker-side source-change revalidation.
- Aggregate-state precedence for every combination needed to distinguish
  ready, partial, queued, processing, failed, not planned, and unavailable.
- Catalog response remains bounded and performs no per-row source read.
- Preparation validates IDs, order, duplicates, body size, and maximum count.
- Preparation reuses ready/active work, retries explicitly, reports
  unavailability, and isolates partial database failure.
- All-three preflight prevents partially scheduled unavailable recordings.
- Concurrent identical requests create one active job per identity.
- Queue order and positions match claim order.
- Failure/history pagination is stable while new rows arrive.
- Retry recomputes current identity and cannot retry a succeeded or unknown job.
- Worker lock probe reports online/offline and leaves no acquired lock behind.
- Estimate median, minimum samples, compatibility filtering, zero/invalid size,
  malformed timestamps, exceeded estimate, and bounded sample query.
- API database failures return sanitized diagnostics.
- Existing front, top-down, IMU, artifact, worker, and range tests remain green.

### Visible/manual acceptance

- A synthetic nested archive produces the exact physical folder tree.
- Saved catalog loads without scanning.
- Explicit rescan updates the successful timestamp and retains data on an
  induced incomplete scan.
- Multiple recording IDs prepare in stable order; current artifacts are reused.
- One job runs while later jobs show stable queue positions.
- Restart preserves queue and history.
- A failed job appears with a safe diagnostic and explicit retry.
- Elapsed time is exact; estimates show approximate, unavailable, or exceeded
  states honestly.
- Damaged and missing recordings create no impossible work.

### Real-data acceptance

Use the explicitly approved development archive only for a bounded recursive
rescan in this block. Capture a before/after inventory of relative names, kinds,
sizes, and nanosecond modification times. Do not process artifacts merely to
prove the backend API; reuse existing database history for estimate evidence.

Require unchanged inventory, stable known recording IDs for unchanged paths,
and no jobs created by scanning.

### Completion evidence

Report migration version, schema/table/index changes, API contracts, query
measurements, all tests, manual states, real-scan inventory result, assumptions,
limitations, and Git status. Leave all work uncommitted for review.

#### Recorded Building block 1 evidence — 2026-08-04

- Additive migration `0005_v1_operations.sql` preserves V0 rows and IDs,
  backfills present generation-zero rows, creates three conservative
  rescan-required targets per legacy recording, and adds catalog state,
  preparation targets, estimate fields, the global-running constraint, and
  focused indexes.
- `/api/v1` now exposes saved catalog, explicit rescan, recording detail,
  Prepare selected, processing overview, queued/failed/history pages, and
  retry-current-identity contracts. V0 routes remain intact.
- The accumulated routine/API/ROS run passed 262 tests; the disposable
  PostgreSQL run passed 29 tests; 14 dependency-free browser tests and both
  browser syntax checks passed.
- At the configured maximum of 5,000 synthetic recordings, the catalog query
  and serialization path returned 15,000 output facts in 471 ms and a
  2,652,445-byte response. Processing queries completed in 32 ms on the warm
  repeated run (398 ms on the first measured run).
- `EXPLAIN ANALYZE` used `jobs_succeeded_history`,
  `jobs_actionable_failure`, and `preparation_targets_current_identity`; the
  measured executions were 0.059 ms, 0.301 ms, and 0.029 ms respectively.
- Nested synthetic operational acceptance covered saved startup, folders,
  mixed ready/failed/new/unavailable selection, FIFO positions, offline and
  active worker views, elapsed/available/exceeded estimate states, retry,
  incomplete-scan retention, active-job responsiveness, and restart
  persistence.
- The single approved real V1 rescan found six recordings: five readable and
  the known damaged `2025_11_04_plain_figure8_spotlight_0.db3`. Before/after
  relative-name/kind/size/nanosecond-mtime inventories matched exactly. The
  disposable database contained 6 recordings, 18 targets, 0 jobs, and 0
  artifacts afterward.
- No frontend-reference file, processor format, timing rule, deployment, Git
  commit, or remote was changed by this block.

### Stop conditions

Stop for direction if implementation requires changing a processor format,
source time model, artifact identity rule, adding another worker, deleting
catalog history, following source symlinks, or weakening source immutability.

## 5. Building block 2 — Reference frontend integration

**Status:** Implemented, verified, and accepted on 2026-08-04

**Dependency:** Building block 1 reviewed and accepted on 2026-08-04

### Goal

Make the served application visually match the user-authored `archive/`
frontend while replacing every mock recording, folder, job, media, telemetry,
timer, and interaction with the accepted backend contracts.

### Boundary

This is a frontend integration block. The visual reference is stable. Backend
changes are limited to corrections required to satisfy the already accepted V1
API; any new product capability returns to roadmap review.

### Included

#### Reference preservation

- Inventory the reference DOM, CSS, assets, interactions, breakpoints, and
  accessibility behavior before editing served files.
- Keep `archive/` unchanged as comparison material.
- Port its top bar, rail, Recordings view, folder panel, cards, table,
  Processing view, dialogs, metadata panel, camera grid, sensor selector,
  telemetry graph, and responsive behavior.
- Use supplied local visual assets only where they remain truthful interface
  decoration; never show mock preview imagery as real recording output.

#### Recordings integration

- Load `/api/v1/catalog` on startup without rescanning.
- Build the real folder tree and counts.
- Render real summaries, rows, health, aggregate state, and output tooltips.
- Preserve search, filters, sort, pagination, selection, folder collapse, empty
  states, and retained-table rescan failure.
- Send one bulk prepare request and render each outcome.
- Navigate with refreshable numeric recording URLs.

#### Processing integration

- Render backend current work, queue, failures, and history.
- Implement manual and live refresh, hidden-page throttling, and stale-response
  protection.
- Tick elapsed display locally between authoritative responses.
- Display only backend estimate facts; delete mock elapsed and simulated job
  mutations.
- Wire failure details, retry, and Open Recording.
- Show worker-offline/queue-paused state without rewriting job facts.

#### Analyzer integration

- Render real metadata, components, and analysis outputs.
- Attach real identity-bound front and top-down media.
- Load and validate the real six-channel IMU bundle.
- Preserve the accepted global clock, coverage, drift correction, graph seek,
  cursor, selection, null gaps, duplicate lookup, and consumer isolation.
- Remove ordinary per-pane Generate actions.
- Provide a clear route to Recordings or Processing for incomplete preparation.

#### Quality

- Preserve safe DOM construction, CSP, security headers, keyboard access,
  visible focus, status text, live/busy semantics, reduced motion, and current
  responsive breakpoints.
- Remove all mock arrays, static counts, fake history, fake paths, fake dates,
  simulated rescan, simulated retry, and automatic mock timers from the served
  runtime.
- Keep dependency-free browser delivery unless a separately reviewed need is
  demonstrated.

### Expected implementation areas

- `src/rosbag_analyser/web/index.html`
- `src/rosbag_analyser/web/styles.css`
- `src/rosbag_analyser/web/app.js`
- `src/rosbag_analyser/web/imu_graph.js` only where integration requires it
- packaged local assets derived from `archive/assets/`
- static delivery and API package tests
- dependency-free JavaScript unit/runtime tests
- browser visual and interaction acceptance fixtures

### Excluded

- Redesigning, simplifying, or restyling the user-authored frontend.
- Editing `archive/` as the served implementation.
- A frontend framework, npm runtime, external CDN, analytics, icon library,
  chart library, or remote font.
- Separate per-output generation controls.
- Browser access to source paths or generated filesystem paths.
- A changed clock, drift threshold, coverage rule, or processor format.
- Job cancellation, priority, reordering, or multiple workers.
- NAS service/deployment configuration.

### Implementation sequence

1. Capture reference screenshots and DOM behavior at every accepted viewport.
2. Map every mock field/action to a V1 API fact or mark it as static decoration.
3. Establish the served shell and routing without data behavior.
4. Implement catalog/folder rendering and retained rescan behavior.
5. Implement selection and bulk preparation outcomes.
6. Implement Processing tabs, polling, retry, and history.
7. Integrate recording detail and ready artifacts.
8. Reconnect the accepted shared timeline and IMU graph.
9. Remove mock runtime and prove no mock content can appear.
10. Run syntax, unit, runtime, API, and accumulated backend tests.
11. Perform visual, keyboard, responsive, reduced-motion, failure, and real-data
    acceptance.
12. Record evidence and stop for user review.

### Minimum automated tests

- Static asset routes, packaging, CSP, security headers, and no external assets.
- Saved catalog load and no implicit rescan.
- Folder construction, search, filter, sort, pagination, counts, collapse, and
  empty results.
- Readable/damaged and all aggregate analysis states with truthful tooltips.
- Selection across filters/pages and bounded Prepare selected behavior.
- Partial preparation response, unavailable recording, network failure,
  duplicate click, and retry.
- Current job, queue positions, elapsed tick/resync, estimate variants,
  worker-offline state, failures, detail dialog, history pagination, manual
  refresh, live toggle, hidden-page pause, and stale response rejection.
- Numeric route navigation, refresh, back, and forward.
- Front/top-down media load, range-compatible URLs, media error recovery, and
  isolated consumer failure.
- Six IMU options, labels, units, extrema, null gaps, duplicate-last lookup,
  graph seeking, keyboard seeking, playback reanchor, and persistent cursor.
- Global start/end, play, pause, explicit seek, 100-millisecond correction,
  measured coverage, and outside-coverage behavior.
- Safe text rendering for hostile folder, recording, diagnostic, and search
  strings.
- Keyboard focus, skip link, live regions, status independent of color, 200%
  zoom, reduced motion, and narrow layout without document overflow.
- A guard asserts served code contains no mock recording/job datasets or mock
  state-advancing interval.

### Visual acceptance matrix

Compare reference and served application at minimum:

- 1600×900;
- 1366×768;
- 1024×768;
- both sides of the existing 901/900-pixel boundary;
- 600×800;
- 320×800;
- 200%-zoom-equivalent layout; and
- reduced-motion mode.

Small text substitutions caused by real data are expected. Layout, hierarchy,
density, spacing, colors, controls, and flow should remain recognizably the
authored design.

### Real-data acceptance

With explicit source opt-in and an inventory guard, exercise:

- one short readable recording with all three outputs;
- one longer readable recording, preferably reusing accepted artifacts;
- the known damaged recording; and
- a mixed multi-recording preparation selection.

Confirm videos, graph, folders, statuses, Processing activity, reload/restart
reuse, and unchanged source inventory. Generated output must remain under the
derived root.

### Completion evidence

Provide before/reference and after/served screenshots, viewport results,
keyboard/accessibility observations, network/API traces at contract level,
tests, real-data outcomes, source inventory, removed mock behavior, limitations,
and Git status. Leave changes uncommitted for user review.

#### Recorded Building block 2 evidence — 2026-08-04

- The served dependency-free frontend ports the unchanged `archive/` hierarchy,
  styling, density, responsive behavior, dialogs, and analyzer layout into
  `/`, `/processing`, and `/recordings/{id}`. Mock recordings, previews, jobs,
  timers, and fabricated progress are absent from the served package.
- Startup reads the saved catalog without scanning. Recordings, physical-folder
  navigation, filtering, sorting, pagination, selection, one bounded Prepare
  selected request, processing overview/history/retry, and identity-bound
  Analyzer media and IMU are wired to the accepted API contracts.
- One browser-owned recording clock retains measured coverage, six IMU axes,
  per-series gaps, duplicate-last lookup, and the accepted 100-millisecond
  camera correction. Independent unavailable media remain visibly unavailable.
- The accumulated Python suite passed 260 tests with 25 environment-dependent
  skips. Sixteen dependency-free browser/runtime tests passed, including stale
  request handling, accessibility interactions, queue truth, and synchronized
  Analyzer behavior. A 76,000-sample IMU payload parsed in 83.260 ms and its
  render transforms completed in 32.981 ms in the measured Node runtime.
- Reference and served screenshots covered 1,600, 1,366, 1,024, 901, 900, 600,
  and exact 320-pixel widths plus a zoom-equivalent viewport. Exact 320-pixel
  Recordings and Analyzer measurements had no document-level overflow. Empty,
  error, collapsed-folder, queue, failure, history, dialog, offline, reduced-
  motion, ready, and incomplete states were also inspected.
- The approved real scan completed in 215 ms and found six recordings: five
  readable and one known damaged. A mixed ready/damaged selection reused three
  outputs and truthfully reported three unavailable outputs without creating
  work. The real archive is flat, so nested folder navigation was exercised
  with synthetic data.
- One short readable recording completed all three jobs through the real UI:
  front preview in 427,611 ms, top-down preview in 6,716 ms, and IMU series in
  14,638 ms. A longer ready recording reused existing artifacts. Both showed
  real synchronized cameras and six-axis IMU; the damaged recording remained
  unavailable. Restart preserved the catalog, eight succeeded-history entries,
  and ready reuse with no new jobs.
- The source before/after inventories matched exactly at 30 entries and SHA-256
  `cee38c757e4bd1cd833dac4d8127e1d1dc5a4bbcd70f5de530900f3a3bac6b8c`.
  Derived storage added only the three validated artifact bundles, with no
  removals or temporary/partial entries. No deployment or Building block 3 work
  was performed.
- The in-app browser bridge could not address this WSL workspace, so visual and
  interaction acceptance used the already installed local Chrome in headless
  CDP mode. No browser package, framework, or other runtime dependency was
  installed.

#### Approved smooth front-camera corrective slice — 2026-08-04

- The accepted V0 read-only audit had already isolated reported front-preview
  stalls to irregular ROS database record gaps of approximately 0.245–0.422
  seconds while camera image-header cadence remained near 0.05 seconds. Source
  and output frame counts matched, so this correction does not invent or
  interpolate frames.
- `front-preview-v2` retains the first and last retained record timestamps as
  measured coverage and affinely maps strictly ordered image-header timestamps
  between those endpoints. Invalid, unordered, degenerate, out-of-span, or
  media-timescale-colliding header timing fails before publication.
- The front timing policy participates in planner and cache identity. The
  schema-version-2 front manifest records both spans, affine scale, maximum
  presentation gap, provenance, and an exact media-PTS digest; validation checks
  that digest before publication. No migration, artifact kind, dependency, or
  top-down/IMU identity changed.
- Browser correction retains the accepted 100-millisecond trigger but keeps one
  seek in flight, retries only after a bounded 1.5-second timeout, suppresses
  automatic correction while buffering, and performs one catch-up on readiness.
- The full Python suite passed 264 tests with 25 environment-dependent skips;
  the focused ROS image serialization test also passed in the sourced Humble
  runtime. Frontend syntax plus 18 dependency-free runtime/IMU tests passed,
  including slow-seek and buffering simulations. No real source archive,
  deployment, or Building block 3 work was performed; real-output acceptance
  remains a separate explicit opt-in.

#### `front-preview-v3` all-zero-header corrective slice — 2026-09-01

- Protected VM diagnostics for recordings 84, 30, 10, and 7 inspected 17,492
  decoded front-camera frames. Every image header had exactly `stamp.sec == 0`
  and `stamp.nanosec == 0`; none supplied a valid non-zero capture timestamp.
  The full-source before/after manifests matched exactly at 53,102 entries and
  SHA-256
  `22ee647fd15b82aa7581db16bd06b6718b8aa9e55c5a6cc70e914ce22755380d`.
- `front-preview-v3` keeps the V2 affine policy unchanged for a stream of valid,
  strictly increasing non-zero headers. Only a stream whose every decoded
  image header is exactly zero uses retained ROS database record timestamps as
  presentation cadence. Coverage remains the first and last retained record
  timestamp; duplicate record timestamps still collapse to the last frame.
- The correction does not interpolate frames or fabricate a fixed FPS.
  Missing headers, mixed zero/non-zero streams, negative seconds, invalid
  nanoseconds, out-of-range non-zero values, unordered record or valid-header
  timing, degenerate affine spans, and media-timescale collisions fail safely
  before publication. The all-zero selection is deliberately not broadened to
  another invalid-header case.
- Processor `front-preview-v3` and timing identity
  `image_header_affine_or_all_zero_record_timestamp_v3` participate in planner
  and cache hashes. V2 front artifacts remain historical; top-down and IMU
  identities do not change. Successful fallback artifacts record
  `ros_record_timestamp_all_zero_image_headers` provenance and retain exact
  media-PTS digest validation.
- Focused synthetic verification covers valid V2 cadence, all-zero record-time
  cadence with visible irregular gaps, exact artifact validation, duplicate and
  unordered record timestamps, mixed/missing/invalid headers, worker manifest
  provenance, and V2-to-V3 planner/cache identity separation. The focused
  processor/planner/artifact/worker/API set passed 113 tests; the complete
  default Python suite passed 394 with 39 environment-gated skips; three
  sourced ROS serialization tests and all 49 dependency-free JavaScript tests
  passed. The optional disposable PostgreSQL suite was unavailable because its
  local test server was not running; this slice changes no schema or repository
  query. No real source, VM service, database, deployment, release, or job was
  accessed or changed; a bounded V3 real-output trial remains separately gated.

#### Approved moved-path catalog corrective slice — 2026-08-05

- Read-only catalog diagnosis found six current physical recordings but 15
  persisted rows: nine retained paths from earlier complete generations were
  being returned as ordinary recordings and mapped from precise `missing` to
  presentation `damaged`.
- Complete-scan reconciliation still retains missing rows, components, targets,
  jobs, artifacts, and numeric history safely. Ordinary V0/V1 catalog lists,
  folder nodes, summaries, and persisted successful-scan health counts now use
  only `source_present = true`; explicit internal history queries can still
  retrieve the retained rows.
- A focused PostgreSQL/API test moves one synthetic recording, proves the new
  current path is the only catalog item and folder descendant, verifies
  current-only counts, and confirms the old row and queued job remain intact.
  Reappearance at the same path continues to regain its prior ID.
- The routine Python suite passed 264 tests with 26 environment-dependent skips;
  all 30 disposable PostgreSQL tests and all 20 dependency-free browser/runtime
  tests passed. The 5,000-recording catalog measurement completed in 417 ms with
  the unchanged 2,652,445-byte response bound.
- This correction adds no migration, API schema, dependency, artifact
  reassignment, deployment work, or Building block 3 work. Activating the
  correction required restarting the previously running API process. A guarded
  live rescan then advanced to generation 28 with six recordings, five readable,
  one genuinely damaged, and zero missing; all 32 source inventory entries and
  all processing counts remained unchanged.
- This first correction did not reassign artifacts; the follow-on correction
  below records the separately approved identity-contract decision.

#### Approved move-aware artifact-reuse corrective slice — 2026-08-05

- The scan transaction now separates current physical location from stable
  private cache anchors. A path-independent metadata/component fingerprint is
  used only to identify a one-to-one move; processor cache hashes, versions,
  source-file identities, formats, and timing rules are unchanged.
- A normal move updates the existing recording path in place. A guarded legacy
  recovery reassigns database job/artifact ownership from exactly one
  history-owning missing row to an otherwise history-free current row and copies
  its cache anchors. Neither operation reads, copies, renames, or rewrites a
  derived artifact.
- Multiple identical incoming candidates, multiple history owners, and weak or
  incomplete fingerprints are not merged automatically. Changed device/inode,
  size, mtime, processor, topic, profile, or timing facts remain cache misses.
- Additive migration `0006_move_reconciliation.sql` backfills stable anchors and
  adds the bounded fingerprint lookup index without deleting or renumbering
  existing domain rows.
- The routine Python suite passed 265 tests with 29 environment-dependent skips;
  all 33 disposable PostgreSQL tests, all 20 dependency-free browser/runtime
  tests, both frontend syntax checks, and both sourced ROS tests passed. The
  5,000-recording catalog remained bounded at 463 ms and 2,652,445 response
  bytes; Processing queries completed in 31 ms.
- Live migration and generation-29 rescan retained six current recordings (five
  readable and one genuinely damaged), all 12 succeeded jobs, and all 12
  artifact rows. Source inventories matched exactly at 32 entries and SHA-256
  `c9f0ea58c7f01ae0aaddc74a1e39f38044d41d7db1d38d25bb5736aea66893f3`.
- The existing split histories were reconciled from cache-anchor IDs 3, 4, and 6
  to current recording IDs 12, 13, and 15. Figure 8 regained all three current
  outputs. The other two regained current top-down and IMU output; their sole
  front previews are correctly retained as non-current `front-preview-v1`
  history after the separately approved `front-preview-v2` timing correction.
- Eleven of 12 referenced artifact files remain present at their exact database
  sizes. The sole absent file is the already-stale Figure 8
  `front-preview-v1`; its current `front-preview-v2` replacement is intact.
  Identity-bound one-byte range requests for Figure 8 front, top-down, and IMU
  each returned HTTP 206. The API and worker restarted healthy with zero queued,
  running, or failed work, and no processing was requested.

### Stop conditions

Stop if exact integration needs a new API capability, processor, artifact kind,
timing rule, external runtime dependency, or material visual redesign not
already approved in Building block 1 or the V1 documents.

## 5A. Prompt 2A — Big UI overhaul and real processing controls

**Status:** Implemented and synthetically verified on 2026-08-23; reviewed and
committed locally as `1c8871b` on 2026-08-24; real-source, screenshot, and live
commissioning acceptance remain gated

### Implemented boundary

- The served dependency-free frontend now follows the frozen 2026-08-23
  `archive/` Recordings, Processing, and Analyzer surfaces without serving its
  mock operational payloads. Experiments/Files are removed. The 2026-08-24
  recordings-only review restores the reference's separate Recorded column
  from `start_time_ns` and corrects filters, tooltips, folder styling, focus,
  selected rows, and the single-line Prepare selected action without changing
  Processing or Analyzer.
- Prepare selected freezes the chosen recording IDs and any non-empty subset of
  front, top-down, and IMU output kinds for one bounded authoritative request.
- Additive migration `0007_job_controls.sql` keeps the exact six domain tables
  while adding durable control state, execution phase, pause/cancel timing,
  stable queue order, and canceled-history indexing to `jobs`.
- The one worker uses cooperative checkpoints and a transactional publication
  gate for pause/resume/cancel. Reorder, insertion, queued cancellation, and
  claim share one serialized order; bulk cancel and failed retry are bounded.
- Processing reports wall and active elapsed time, authoritative allowed
  controls, canceled counts/history, and cumulative approximate queue estimates
  only while every required predecessor input is valid. Progress stays
  indeterminate because no existing processor exposes a complete exact unit
  contract suitable for a truthful percentage.
- Analyzer adds graph-window zoom/reset/paging, wheel scrubbing, Shift-drag
  selection, and keyboard navigation over the unchanged full-recording clock,
  media timing, correction, and measured coverage behavior.
- Deployment assets recognize schema 0007 and rate-limit the approved mutation
  routes. Planned drain fails closed on paused or pause-requested work so the
  operator must explicitly resume or cancel before upgrade.

### Verification and remaining gates

Synthetic unit, API, worker, browser-runtime, deployment, migration, repository,
queue-concurrency, and maximum-catalog checks are recorded in the Prompt 2A
completion note in `BUILDING_BLOCK_PROMPTS.md`. The frozen archive hashes and
zero archive diff are rechecked at handoff. No authoritative source was read.
Subsequent exact-command VM preparation provisioned separate derived storage,
local PostgreSQL roles, dependencies, and a read-only application-facing CIFS
bind; it has not installed the release or scanned source content. Automated
browser behavior was exercised, but screenshot comparison remains explicit
visual acceptance work.

## 6. Building block 3 — TrueNAS VM deployment and trial commissioning

**Status:** Invoked on 2026-08-16; repository readiness implemented, locally
verified, and accepted as part of the 2026-08-23 pre-overhaul baseline; external
handoff remains incomplete; controlled live VM preparation in progress

**Dependency:** Accepted backend and frontend, plus the administrator handoff in
Gate 0 below

### Goal

Turn the accepted V1 application into a repeatable, secure, supportable service
on one administrator-provisioned Ubuntu VM. A limited engineer group must be
able to use it through the approved access boundary without a developer session,
while the selected NAS source remains read-only and all application writes stay
on separate derived and database storage.

This is the final V1 delivery block. It includes repository deployment
preparation, first installation, data/schema migration, operational proof, and
trial handoff. It does not claim high availability or production service levels.

### Approval and ownership boundary

Invoking Prompt 3 authorizes the repository implementation in this block and,
after Gate 0 is satisfied, a reviewed installation inside the exact approved VM.
It does not authorize Codex or the application project to create or change
TrueNAS datasets, zvols, snapshots, shares, ACLs, host networking, firewall
rules, the VM definition, the TrueNAS version, or any unrelated service.

The TrueNAS administrator owns those appliance changes and the base Ubuntu
installation. Before any live VM mutation, the implementer must show the exact
target, commands, files, services, expected interruption, backup, and rollback
to the user. Missing live access does not block repository work: finish and test
the deployment assets, then stop at the external handoff gate.

No exact server address, export path, credential, certificate, private mount
path, or backup destination belongs in Git.

### Sanitized target facts that shape this block

- The intended host was observed on a TrueNAS 26 beta release. Official TrueNAS
  guidance classifies early releases as testing/feedback software, so the
  administrator must either move the service to an approved general-use host
  through their own change process or explicitly accept a non-critical,
  reversible trial on the beta host.
- The existing host bridge has globally routable IPv4 and IPv6. The word
  internal is therefore not a security control. The administrator must prove
  the actual VPN, firewall, allowlist, and IPv6 policy before an engineer-facing
  listener is enabled.
- Existing NFS exports include overlapping parent/child locations and the
  candidate source area has broad filesystem permissions. The exact fixed
  recording root must use a dedicated, explicitly server-side read-only export;
  a client ro mount alone is insufficient.
- The accepted application runtime remains Ubuntu 22.04 LTS, Python 3.10, and
  ROS 2 Humble because Jammy is Humble's Tier 1 binary platform. Ubuntu 22.04
  standard security maintenance and ROS 2 Humble support both end in May 2027.
  A supported-platform migration is a separate future block, not an in-place
  Humble-on-newer-Ubuntu experiment.
- The operator, not this repository, chooses final VM storage placement,
  derived capacity, addresses, certificates, identity/access method, backup
  target, and maintenance windows.

### Gate 0 — administrator-provisioned foundation

Before a live install, obtain a sanitized, approved handoff that confirms:

1. A fully patched Ubuntu Server 22.04 LTS amd64 VM exists with UEFI, Secure
   Boot and virtual TPM policy decided by the administrator, UTC, time sync,
   SSH-key administration, remote root login disabled, and no desktop.
2. The deployment baseline is approximately one virtual socket, six cores, one
   thread per core, host CPU passthrough, 16 GiB fixed RAM, and a 100 GiB OS
   disk. Any variance is recorded rather than silently assumed.
3. The VM has a unique approved address, uses the approved existing bridge or
   equivalent, starts automatically with the NAS, and has an orderly shutdown
   timeout compatible with a long serial worker stop.
4. Installation media is detached, console/VNC is disabled after installation
   or loopback-only through an approved administrative tunnel, and a clean-base
   snapshot or equivalent rollback point exists.
5. The exact fixed source folder is exported independently by NFS with the
   server Read-Only control enabled, access restricted to the VM, remote root
   mapped to an unprivileged identity, and parent/child export interactions
   reviewed. Both IPv4 and IPv6 access paths are accounted for.
6. A distinct derived-data virtual disk/filesystem is attached and sized with a
   documented low-space threshold and growth policy. Temporary and final
   artifact locations share that filesystem so atomic publication remains
   possible.
7. PostgreSQL data, deployment configuration, and backup destinations have
   owners, capacity, retention, and restore expectations, and the protected
   off-VM destination is approved and reachable. The first verified dump and
   disposable restore occur after database initialization and before trial
   admission.
8. The engineer access boundary, TLS certificate source, authentication method,
   named trial group, access grant/revocation owner, and firewall rules are
   approved. Raw API, PostgreSQL, NFS, SSH, and console access are not granted
   to ordinary trial users. Both upstream controls and a default-deny guest
   firewall (or an explicitly approved equivalent) cover IPv4 and IPv6.
9. The administrator records the TrueNAS beta risk decision, appliance
   configuration backup/recovery path, maintenance owner, and escalation route.
10. The project owner accepts a platform-lifecycle checkpoint no later than
    2027-01-31 and no continued service beyond Humble support without an
    approved migration to a supported Ubuntu/ROS pairing.

The handoff may contain sensitive values outside Git. The repository records
only placeholders, validation rules, and sanitized evidence.

### Included

#### Deployment package and configuration

- Build a versioned application release from a reviewed source identity with a
  deployment-only verified dependency set, recorded OS/runtime versions, and
  an immutable release directory. Do not deploy an unidentified dirty checkout
  or infer permission to commit it.
- Keep the existing ./dev workflow unchanged. Deployment uses dedicated,
  non-login service identities and root-owned configuration outside the
  repository checkout.
- Provide example configuration with placeholders, strict validation, safe
  file-mode checks, and no secret echo.
- Add deployment preflight that verifies the exact NFS mount, filesystem type,
  client read-only options, source containment/readability, separate writable
  derived root, atomic-rename assumptions, executables, database/schema
  compatibility, and free-space threshold without scanning or write-probing the
  source.
- Add separate liveness and readiness endpoints. Readiness is truthful and
  sanitized; it performs no rescan, processing, job creation, or full source
  read.
- Reject new preparation safely when derived space is below the configured
  threshold while continuing to serve valid ready artifacts.

#### Service lifecycle

- One loopback PostgreSQL instance, one loopback API, exactly one serial worker,
  and one engineer-facing Nginx or approved identity-proxy path.
- Version-controlled systemd templates for controlled migration, API, worker,
  and an application target.
- Ordering on network, database, and exact mounts; failure if a required mount
  is missing or replaced by an ordinary local directory.
- Enable the application target at boot only after live acceptance. Use bounded
  restart behavior, practical systemd hardening, journald, a deliberate long
  worker stop timeout, and documented drain/interruption recovery.
- Never run migrations, rescans, or preparation implicitly at process or VM
  startup.

#### Network and access

- Uvicorn and PostgreSQL listen only on loopback. Nginx listens only where the
  approved firewall/VPN boundary and both IP families have been proven.
- Configure a root-managed default-deny guest firewall for both IP families:
  SSH only from the administration path and HTTPS only from approved VPN/trial
  networks. Apply it through an exact reviewed rule set with a tested recovery
  path so deployment cannot lock out the administrator.
- Same-origin TLS delivery with per-engineer authentication through the
  organization's identity layer, or trial-only individual proxy credentials
  over TLS if no such layer exists.
- Preserve application validation for all artifact and byte-range delivery;
  Nginx never serves the derived directory directly.
- Restrict unexpected hosts, methods, body sizes, cross-origin writes, and
  interactive API documentation. Preserve GET, HEAD, Range, If-Range, ETag, and
  206 behavior through the proxy.
- No public DNS, public forwarding, or direct trial-user access to ports 8000 or
  5432.

#### Release, migration, backup, and rollback

- Stage each release beside the active release, validate it, close the write
  entrance, back up PostgreSQL, drain the worker, stop services, migrate exactly
  once, atomically switch the active pointer, restart, and smoke-test before
  admitting traffic.
- Default a new NAS trial to a fresh database followed by explicit rescan.
  Transfer development history only through a separately reviewed coherent
  database-plus-derived-state plan whose source identities still match.
- Refuse incompatible schema versions. Classify rollback per release as either
  tested code-compatible rollback or database restore; never improvise a down
  migration during an incident.
- Verify each custom-format database dump and restore one into a disposable
  database before trial acceptance.
- Choose and test a coherent derived-artifact recovery policy: either restore a
  quiesced volume snapshot with the database or deliberately invalidate and
  regenerate files absent after a metadata-only restore.
- Never back up, repair, reindex, snapshot through the application, or otherwise
  mutate the source recordings.

#### Operations and handoff

- Write an operator runbook for install, configure, preflight, migrate, boot,
  start/stop/status, logs, explicit rescan, queue recovery, capacity, backup,
  restore, upgrade, rollback, access grant/revocation, certificate renewal,
  patching, and sanitized support collection.
- Write a concise engineer guide for the Recordings → Prepare selected →
  Processing → Analyzer workflow and known trial limitations.
- Record release identity, service state, schema version, safe job facts,
  durations, output sizes, backup results, and operational errors without
  secrets, source payloads, absolute source paths, or credentials.
- Define daily/weekly/monthly ownership, patch cadence, capacity review,
  certificate/credential expiry checks, incident contacts, and the January 2027
  platform decision.
- Provide a clean uninstall/retirement plan that stops the application and
  preserves data for an operator-approved retention decision; it never deletes
  source or derived data automatically.

### Expected repository areas

~~~text
deploy/
  README.md
  environment.example
  systemd/
  nginx/
  scripts/
docs/
  NAS_TRIAL_RUNBOOK.md
  ENGINEER_TRIAL_GUIDE.md
~~~

Exact names can follow repository conventions. Deployment scripts must be
non-interactive where practical, validate every target, fail closed, avoid shell
injection and secret output, and be testable with temporary roots and
disposable databases.

### Excluded

- TrueNAS administration, base VM creation, storage/share/ACL/network changes,
  appliance update, and production certificate or credential issuance.
- Public service, high availability, containers, orchestration, Redis, brokers,
  multiple workers, automatic retry, cancellation, priority, quotas, or
  automatic source watching.
- Application-managed user accounts or roles.
- Frontend redesign, new telemetry, new processors, new artifact kinds, or
  changes to accepted timing and source-safety contracts.
- Automated artifact deletion or retention.
- An Ubuntu or ROS distribution migration. That requires a separately approved
  compatibility block and a new VM or equally reversible target.
- Commit, push, release publication, or destructive live drills.

### Implementation sequence

1. Re-audit the accepted repository, dependency lock, current configuration,
   migrations, API/worker lifecycle, tests, and uncommitted state.
2. Convert Gate 0 into a sanitized operator handoff checklist and deployment
   inventory template. Stop live work until every required owner/value is known.
3. Freeze the release, filesystem, service, access, backup, lifecycle, and
   rollback contracts and write their tests first.
4. Implement configuration/preflight, readiness/liveness, and low-space
   behavior without changing the accepted developer workflow.
5. Implement release packaging, systemd, proxy, migration, backup/restore,
   smoke-check, and support-bundle assets.
6. Run static and automated tests plus a complete disposable deployment
   lifecycle locally.
7. Review the exact live change set, backup, interruption, and rollback with the
   user. The administrator completes any remaining TrueNAS/base-VM work.
8. Install the candidate into the approved clean VM without admitting users.
9. Validate network, derived storage, database migration, and local smoke tests
   with a disposable synthetic source. Keep application services disabled and
   do not traverse the authoritative source.
10. Approve the real-data annex, establish/inspect only the exact mount identity,
    and capture the before manifest before full source preflight or application
    access. Then run bounded live-matrix items 1–12 below.
11. After the pre-boot checks pass, enable rosbag-analyser.target in the guest,
    verify the administrator-provided TrueNAS VM-autostart setting, reboot the
    guest VM, complete live-matrix item 13, and then capture the final inventory
    and containment proof in item 14. Do not reboot the TrueNAS host; observe
    host autostart at its next separately approved maintenance reboot.
12. Record evidence, train the operator, and stop for user approval before
    granting access to the engineer trial group.

### Minimum automated and disposable tests

- Secret/private-path scan, shell syntax/lint where available, and static
  validation of systemd and Nginx templates.
- Configuration bounds, file modes, missing values, and redacted failures.
- Source/derived missing, overlap, symlink, wrong mount type/options,
  permissions, renamed mount, ordinary-directory fallback, atomic rename, and
  low-space cases.
- Liveness/readiness truth table proving no scan, job, artifact, or source
  mutation.
- API/worker boot, restart, graceful stop, forced interruption, advisory-lock,
  and exactly-one-worker behavior.
- Release staging and atomic switch, single migration, incompatible-schema
  refusal, verified dump, disposable restore, and both rollback classifications.
- Proxy TLS/access assumptions, host/method/body limits, trusted headers, and
  application-mediated GET/HEAD/Range/If-Range/ETag behavior.
- Guest-firewall rule validation and allowed/denied IPv4 and IPv6 reachability,
  including a tested administrative recovery path.
- Database/source/derived outage recovery using disposable targets only.
- Persistence across service and VM-style restarts, including queued and
  interrupted work.
- The complete accepted Python, PostgreSQL, ROS-message, JavaScript/browser, and
  local-launcher regressions.

### Live acceptance and real-data boundary

After Gate 0 and the exact live change review, Prompt 3 authorizes read-only
access only to the administrator-approved fixed recording root. Capture a
lightweight before inventory of relative name, kind, size, and high-resolution
modification time before the first application access and an identical after
inventory after every live-data exercise.

The bounded live matrix must prove:

1. A fresh install initializes an empty database and applies the accepted schema
   through the documented release procedure, or an explicitly approved
   coherent state-transfer annex proves every imported history/artifact
   identity.
2. Only the approved TLS endpoint is reachable by a trial user. Unauthorized
   access fails; raw API, PostgreSQL, NFS, SSH, and console paths are not
   reachable by that user over either IPv4 or IPv6.
3. Server export configuration and client mount evidence both show read-only
   source access. No write probe is used. Source identity remains stable across
   remount and reboot; an incompatible identity change is a stop condition.
4. Service start and service restart load saved state without scanning,
   preparing, or creating jobs. The final guest-reboot check follows after the
   application target is enabled.
5. One explicit bounded rescan of the fixed root completes, creates zero jobs,
   respects traversal limits, and leaves the source inventory identical.
6. One selected short healthy recording produces and serves all three artifact
   kinds. One representative long healthy recording is processed only after
   recording expected time/capacity and confirming the approved window. If the
   fixed root contains an already-known approved malformed recording, it
   remains honestly unavailable without source repair; otherwise synthetic
   malformed evidence is retained and the live case is recorded not applicable.
7. Two engineer sessions can browse, prepare a bounded mixed selection, observe
   exactly one running job and the authoritative stable queue order, use only
   allowed Prompt 2A controls, and review synchronized output while work
   continues.
8. Front/top media range semantics, IMU choices, global clock, correction, seeks,
   coverage, stale identities, and saved artifacts work through the proxy.
9. A service restart with queued work preserves the queue. A controlled worker
   interruption marks only the running job interrupted, removes only its proven
   temporary workspace, preserves ready output, and succeeds only after explicit
   retry.
10. PostgreSQL loss, mount loss, and full-disk behavior are drilled against
    disposable substitutes: readiness fails safely, existing valid state is not
    fabricated or deleted, and recovery creates no duplicate jobs.
11. A verified pre-deploy dump restores into a disposable database and the
    recorded rollback path works.
12. API responsiveness, CPU, memory, database load, NAS throughput, processing
    time, and derived growth are measured as observations, not advertised SLAs.
13. After rosbag-analyser.target is enabled, a guest VM reboot, optionally with
    queued work, preserves mount identity, services, proxy, saved state, queue,
    and zero-implicit-work behavior. TrueNAS VM autostart configuration is
    verified separately without rebooting the host.
14. After every check, the final source inventory is exactly unchanged and every
    application-created file is proven below the approved derived, database,
    log, backup, or release roots.

### Repository Phase 1 evidence — 2026-08-16

The invoked repository phase added strict deployment configuration and mount/
capacity admission, capability-aware health, release/preflight/source-manifest/
safe-log support, deployment-only dependency and release contracts, systemd/
Nginx/nftables templates, lifecycle scripts, and the operator/engineer guides.

Local evidence completed:

- 328 default Python tests passed; 32 opt-in deployment, PostgreSQL, ROS, and
  real-archive cases were skipped by the default run;
- 55 focused deployment/API tests passed; the environment-gated real Nginx and
  real-nft checks were skipped in that run. The Nginx check passed separately;
  the nft check could not obtain netlink administration capability;
- 34 PostgreSQL 14 tests passed against an explicitly disposable database; the
  largest synthetic catalog measured 402 ms catalog work, 25 ms processing
  projection, and a 2,652,445-byte response;
- a PostgreSQL custom dump passed `pg_restore --list`, restored into a separate
  disposable database, and passed the exact six-table read-only validator;
- two ROS 2 Humble message tests and 20 dependency-free browser tests passed;
- a real disposable Ubuntu Nginx 1.18 TLS proxy test passed authentication,
  trusted-header stripping, HEAD/Range/If-Range/ETag/206, stale identity,
  cross-origin POST denial, and docs denial;
- the CPython 3.10 Ubuntu 22.04 wheelhouse downloaded all exact runtime/build
  versions, captured licences/source metadata, and passed every checksum;
- the application wheel built, exposed all five console scripts, and passed
  `pip check`; shell syntax, Python compilation, template contract checks,
  release-archive safety, source-manifest, support-bundle, and dirty-release
  refusal also passed.

No live VM, NAS, TrueNAS setting, authoritative source, real-data manifest,
firewall, certificate, service enablement, reboot, or trial-user path was
accessed. The current worktree is dirty by design, so no immutable release was
created; that awaits separate commit/clean-source approval. Static systemd and
firewall contracts passed, but actual guest `systemd-analyze`, `nft --check`,
network vantage-point, shutdown-budget, and reboot evidence belong after Gate 0.

### Approved CIFS-stable cache-identity corrective slice — 2026-08-26

Read-only VM diagnosis of six failed real jobs across two recordings showed
that all front, top-down, and IMU resolvers found valid inputs, but their
scan-time cache hashes differed from the worker's freshly computed hashes.
Those jobs failed in 99–136 milliseconds with `*_inputs_changed`, before any
decoder work. The API process, worker process, and direct host stat calls agreed
on the current file identity, pointing to a persisted cross-process CIFS
identity mismatch rather than damaged bag content.

The corrective slice adds the versioned `portable-stat-v1` cache policy. It
keeps file type, size, nanosecond mtime and ctime in persisted per-file hashes,
while device and inode remain mandatory in the full live descriptor checks
around every source read. The policy version also participates in each planner
identity, so deployment requires one explicit successful rescan before new work
is requested; stale queued or failed identities are not rerun blindly.

Focused planner, resolver, worker, and scanner verification passed 61 tests.
The complete default Python suite passed 358 tests with 38 environment-gated
skips, and the JavaScript syntax/runtime/conformance suite passed all 39 tests.
No VM, NAS, database, service, job, or source state was changed while preparing
this repository correction. Live deployment, explicit rescan, job request, and
a bounded source before/after inventory remain separate reviewed operations.

### Completion gate

Building block 3 is complete only when:

- repository assets and the disposable lifecycle pass review;
- Gate 0 is signed off by the named administrator and project owner;
- the live VM, mount, service, proxy, migration, backup/restore, reboot, and
  bounded real-data evidence are recorded;
- the administrator provides evidence that TrueNAS VM autostart is configured,
  rosbag-analyser.target is enabled, and a guest VM reboot proves application
  startup; NAS-host reboot observation is assigned to the next separately
  approved host maintenance rather than triggered by this project;
- an operator other than the developer can use the runbook to inspect health,
  logs, backups, capacity, queue, and access;
- remaining beta-host, lifecycle, backup, security, and capacity risks have
  named owners and dates; and
- the user explicitly accepts the trial handoff before engineers are admitted.

Repository readiness alone may be handed off as complete local implementation,
but it is not live deployment acceptance.

### Stop conditions

Stop and request direction for any of the following:

- Gate 0 is incomplete, the exact target is ambiguous, or the live change would
  exceed the reviewed command/target list.
- The source is not independently exported server-side read-only to the exact
  VM, the export is effectively open to all hosts, parent/child behavior is
  unclear, or safe root mapping cannot be established.
- The required source mount is absent, writable, the wrong filesystem/export,
  or can silently fall back to an ordinary local directory.
- Derived storage overlaps source, lacks space/atomic semantics, or would
  require automatic deletion.
- The access boundary cannot prevent public/raw service exposure on both IPv4
  and IPv6, or the only console option is publicly reachable VNC.
- The administrator does not accept or remediate the TrueNAS beta risk for this
  non-critical trial.
- A backup cannot be created and restored, a migration is destructive or
  rollback-unsafe, or a destructive target is uncertain.
- The accepted Ubuntu 22.04/ROS Humble runtime cannot be provided, or work
  requires a platform migration, containerization, multiple workers, new
  processing behavior, source mutation, or another major dependency.
- Real source data changes during any check.

Do not stop merely because the VM has not yet been delivered. Complete the
repository-side implementation and report the external gate precisely.

## 7. V1 final gate

V1 is ready for engineer feedback only when:

- all three building blocks are reviewed and accepted;
- the served interface retains the authored reference design and contains no
  mock operational data;
- physical folders, health, preparation, queue, failure, history, elapsed, and
  estimate behavior are truthful;
- front, top-down, and six-channel IMU review retains accepted timing and
  coverage behavior;
- the API, worker, database, proxy, mounts, backup, restore, and rollback have
  passed the trial acceptance matrix;
- no original source changed and every output remains confined to derived
  storage;
- the service is private to the limited group; and
- known limitations and feedback channels are visible.

Feedback after this gate determines the next roadmap. It does not automatically
authorize deferred production or analysis features.
