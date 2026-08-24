# ROS 2 Bag Analyser — V1 Project Definition

**Status:** V1 product contract approved on 2026-08-04; Building blocks 1 and 2
and all three corrective slices accepted; Building block 3 repository readiness
implemented, verified, and accepted as the working pre-overhaul baseline on
2026-08-23; Prompt 2A big UI overhaul implemented and synthetically verified
on 2026-08-23, pending user review; live Gate 0, VM commissioning, real-source
acceptance, and trial admission not completed

**Target:** Limited-group engineering trial hosted in an internal NAS virtual
machine

**Baseline:** Completed V0 processors, artifact model, serial worker, and
synchronized review behavior

## 1. Purpose

V0 proved that the application can safely catalog the known ROS 2 archive,
generate reusable browser media and IMU telemetry, and synchronize those
outputs. V1 turns that proof into a coherent feedback prototype that real
engineers can use against a larger NAS-hosted archive.

V1 is not a production robotics platform. Its purpose is to expose the real
workflow to a limited group, make processing activity understandable, and
collect informed feedback before committing to broader formats, sensors,
deployment scale, or collaboration features.

## 2. Product decisions

Prompt 2A was approved, invoked, and implemented on 2026-08-23. Its corrective
product delta is:

- use only the current reference's Recordings, Processing, and Analyzer
  surfaces; remove the leftover Experiments/Files surface and all mock data;
- show the friendly recording name and a separate Recorded column in the
  Recordings table, while retaining truthful source identity in secondary and
  accessible context; recorded time always comes from `start_time_ns`;
- let users prepare any non-empty subset of the existing front, top-down, and
  IMU outputs without changing the three artifact kinds;
- add persistent pause/resume, cancel, queue reorder, bulk cancel, and bulk
  failed-retry behavior to the single-worker processing model;
- show factual elapsed/active time, approximate likely duration, exact numeric
  progress only where a processor has exact units, and approximate cumulative
  queue estimates only when their inputs are valid;
- add the approved Analyzer graph-window zoom, reset, paging, wheel, pointer,
  and keyboard interactions over the unchanged global recording clock; and
- require state-by-state visual parity with the frozen authored reference,
  allowing only documented truthful-data and dynamic-media differences.

The implementation remains uncommitted pending user review. Its live-VM,
authoritative-source, and visual screenshot acceptance remain gated. The
complete safety, persistence, and acceptance contract is owned by Prompt 2A in
`BUILDING_BLOCK_PROMPTS.md`.

The 2026-08-24 Recordings-page review supersedes only Prompt 2A's earlier
name/date presentation choice. It restores the frozen reference's Recorded
column, attached non-native filter menus, viewport-positioned status tooltips,
reference folder/search styling, single-line selection action, and restrained
selected/focus treatments. Processing, Analyzer, backend, processing, timing,
and deployment contracts are unchanged.

The following decisions define V1:

- The static frontend under [`archive/`](archive/index.html) is the visual and
  interaction contract.
- Its layout, navigation, density, styling, responsive behavior, camera panes,
  telemetry pane, folder browser, table, and Processing view remain visually
  stable unless a reviewed implementation problem makes a small adaptation
  necessary.
- Mock data and simulated behavior are replaced with backend responses.
- Physical archive folders drive the folder browser; the UI does not invent a
  year/month hierarchy unless that hierarchy exists in the source-relative
  path.
- **Prepare selected** is the only ordinary preparation action on the
  Recordings page.
- One preparation request resolves a user-chosen non-empty subset of the three
  existing outputs: front preview, top-down preview, and the six-channel IMU
  bundle.
- Those outputs remain separate artifact jobs internally so each can be
  reused, fail, and retry independently.
- One serial worker is sufficient for the first trial.
- Processing state is persistent and visible in a dedicated Processing view.
- Original recordings remain strictly read-only.
- The trial is available only on a trusted internal network to a limited group.

## 3. Intended users

### 3.1 Reviewing engineer

The primary user finds a recording, prepares it if needed, opens it, reviews
both cameras and raw IMU motion on a synchronized timeline, and reports product
feedback.

The engineer should not need ROS commands, filesystem access, a Codex session,
or knowledge of artifact identities.

### 3.2 Trial operator

The operator installs and upgrades the application, configures the NAS mount,
runs explicit rescans, checks service health and logs, monitors storage, and
recovers from ordinary service failures without editing recordings.

### 3.3 Developer

The developer can reproduce the service locally with synthetic fixtures,
inspect safe diagnostics, evolve one reviewed block at a time, and verify that
source data remains unchanged.

## 4. V1 user experience

### 4.1 Recordings

The Recordings view is the entry point.

It must:

- load the saved catalog without scanning automatically;
- render the real physical folder hierarchy and accurate descendant counts;
- filter the table when a folder is selected;
- search recording and folder names;
- show real recording name, recorded time, duration, source size, source
  health, and aggregate analysis state;
- support the mockup's sorting, filtering, pagination, selection, summary cards,
  loading, empty, retained-data failure, and explicit rescan behavior;
- preserve table data when a rescan fails; and
- allow readable compatible recordings to be selected for preparation.

The visible source-health vocabulary is:

- **Readable** — the catalog has the trusted metadata and ROS prerequisites
  required for supported processing;
- **Damaged** — the recording is damaged, missing, unsupported, incomplete, or
  could not be inspected safely.

The tooltip or detail view retains the precise internal condition and safe
diagnostic. A coarse presentation label must not discard the actual reason.

### 4.2 Analysis state

The Analysis column summarizes the current three-output preparation result for
one recording. It does not replace per-output facts.

The states and precedence are:

1. **Processing** — at least one current compatible output is running;
2. **Queued** — no output is running and at least one is queued;
3. **Failed** — no output is active and at least one attempted current output
   failed;
4. **Ready** — all three current compatible outputs are validated and ready;
5. **Not planned** — none of the preceding states applies and the complete
   output set has not been requested.

The state tooltip lists front, top-down, and IMU separately. A partially ready
legacy recording may therefore show **Not planned** with truthful detail such
as “front ready; top-down not requested; IMU not requested.”

Source unavailability is not a processing failure. A damaged recording does not
gain a failed job merely because it cannot be prepared.

### 4.3 Prepare selected

The user selects visible table rows and chooses **Prepare selected**.

For every selected recording and selected output, the application must:

- calculate current identities and prerequisites for the three supported
  outputs;
- reuse compatible validated artifacts;
- reuse compatible active jobs;
- enqueue missing compatible outputs in stable order;
- treat this explicit action as permission to retry a current failed output;
- create no work for unavailable prerequisites;
- prevent duplicate active jobs and duplicate current artifacts; and
- return a per-recording, per-output result.

Only the chosen outputs are preflighted. An unavailable chosen output is
reported independently and creates no impossible work; compatible ready or
active chosen outputs are still reused and valid output is retained. Other
selected recordings continue independently. Aggregate readiness and Analyzer
admission still reflect all three outputs, so partial preparation is truthful
and never presented as a complete analyzer bundle.

The request is bounded and idempotent. One unavailable recording does not roll
back valid work for the others. The UI reports reused, queued, active, and
unavailable outcomes rather than claiming the entire selection succeeded.

Within a new selection, jobs are inserted in selected-recording order and, for
each recording, in front, top-down, then IMU order. This makes one recording
become completely reviewable before the worker advances far into later
recordings.

### 4.4 Processing

The Processing view is an operational window for engineers, not a general job
administration platform.

It must show:

- one current running job, when present;
- its recording, output kind, start age, exact elapsed time, and estimated
  remaining time when enough compatible history exists;
- an indeterminate activity indicator unless a processor exposes a proven
  exact completed/total unit pair;
- the persistent, explicitly reorderable queue with stable positions and
  queued ages;
- durable pause/resume and cancellation controls at bounded safe checkpoints;
- queued-row and bounded bulk cancellation, reorder, and failed-retry controls;
- failed current attempts with safe diagnostics, runtime, details, and retry;
- bounded, paginated succeeded history with runtime, output size, and a link to
  open the recording;
- queue, failure, and history counts;
- manual refresh and optional live refresh; and
- clear unavailable, empty, stale-response, and database-error states.

Elapsed time is factual. An estimate is explicitly approximate. With
insufficient relevant history it reads **Estimating…** or **Not enough
history**. If elapsed time passes the estimate, it reads **Estimate exceeded**;
it must not display a false zero remaining.

V1 does not add priorities, multiple workers, fabricated percentage progress,
or automatic retry. Cancellation and reorder remain explicit user operations;
they do not introduce preemption, a second worker, or a background scheduler.

### 4.5 Analyzer

The Analyzer keeps the mockup's visual layout:

- recording metadata and source/output facts in the left panel;
- front view and top view in the upper workspace;
- the selectable IMU graph and global transport below; and
- the same top bar, navigation rail, responsive layout, and interaction style.

The Analyzer uses real APIs and artifacts. It has no ordinary per-pane Generate
buttons. A recording that is not completely prepared sends the user back to
Recordings or Processing and identifies which outputs remain queued, failed,
unavailable, or not planned.

The synchronization rules remain product requirements, with the explicitly
approved smooth front-camera timing policy:

- ROS database record endpoints place the front camera on the shared timeline;
- strictly ordered image-header capture cadence determines front-frame spacing
  after one affine mapping between those measured record endpoints;
- ROS database record timestamps continue to drive IMU samples;
- CSV Unix timestamps align top-down frames;
- all consumers map to elapsed time from the ROS bag start;
- one browser clock owns play, pause, and seeking;
- camera drift correction remains 100 milliseconds;
- streams report measured coverage; and
- a consumer hides or clears outside coverage rather than freezing a boundary
  frame.

The six selectable IMU signals remain the exact raw standard fields:

- `angular_velocity.x`, `.y`, and `.z` in `rad/s`;
- `linear_acceleration.x`, `.y`, and `.z` in `m/s²`.

No field is renamed to a rover-relative concept such as yaw rate without a
separate coordinate-system decision.

## 5. Archive and folder model

V1 accepts one configured source root. Under that root, ordinary physical
directories may organize recording directories to a bounded depth.

A recording root is a directory identified by the supported ROS metadata
contract, not every directory encountered during traversal. Folder-only
directories are navigation nodes and are not persisted as recordings.

The browser receives only normalized, safe, archive-relative folder segments.
It never receives the absolute NAS mount path. Symlinks are not followed.
Discovered names are untrusted data and must remain escaped text in the browser.

An explicit successful rescan reconciles the saved catalog. Recordings absent
from the new complete snapshot become retained missing-history rows rather than
being deleted along with their processing history. Ordinary catalog lists,
folder counts, health summaries, and scan health counts include only recordings
present in the latest complete snapshot, so moving a recording cannot leave a
visible duplicate or inflate the damaged count. A one-to-one move identified
from path-independent metadata and component facts retains private cache
anchors, recording history, and compatible ready artifacts. Multiple matching
sources or destinations are not merged automatically. A failed or incomplete
root scan does not invalidate the last complete catalog.

Automatic watching, uploads, and scan-on-start are outside V1.

## 6. Functional requirements

### 6.1 Catalog

- Discover supported recordings through bounded, non-symlink, recursive
  traversal.
- Isolate malformed folders and files.
- Retain safe archive-relative identities across unchanged rescans.
- Persist the latest successful scan generation, completion time, duration, and
  counts.
- Persist one current preparation target per recording and supported output,
  containing the scan-derived cache identity or safe unavailability reason, so
  ordinary catalog browsing never rereads source metadata.
- Mark previously catalogued but now absent recordings missing only after a
  complete successful scan.
- Exclude retained source-missing history from ordinary recording lists, folder
  nodes, and current scan/health counts without deleting it.
- Preserve IDs and compatible artifacts for unchanged recordings and
  unambiguous path moves.
- Expose folder paths, folder counts, health, diagnostics, and current aggregate
  analysis without leaking absolute paths.

### 6.2 Preparation and artifacts

- Preserve the current processors and artifact kinds.
- Keep heavy work in the serial worker.
- Keep incomplete work temporary and publish only validated output.
- Reuse compatible artifacts across reloads, restarts, and rescans.
- Enforce one active job for a current artifact identity.
- Make bulk preparation bounded, idempotent, and partially successful.
- Require all three fixed targets to be available before inserting new jobs for
  one recording.
- Retry only through an explicit user action and against the current identity.

### 6.3 Processing visibility

- Query current, queued, failed, and succeeded jobs without reading the source
  archive.
- Join jobs and artifacts only against the current scan-derived preparation
  target; a changed planner/configuration requires an explicit rescan.
- Use database timestamps for queue age, elapsed time, and completed runtime.
- Join succeeded jobs to matching artifacts for output size.
- Keep the stable mutable queue order identical to worker claim order and
  serialize reorder, insertion, cancellation, and claim against that order.
- Paginate history and bound every processing response.
- Estimate duration only from compatible completed attempts and relevant
  catalogued input measures.

### 6.4 Browser

- Preserve the reference design.
- Use safe DOM construction for backend-controlled text.
- Keep URLs refreshable and bookmarkable with numeric recording IDs.
- Keep keyboard navigation, focus visibility, accessible names, live updates,
  reduced-motion support, and narrow layouts.
- Poll only while needed and reduce activity while the page is hidden.
- Distinguish request failure, processing failure, unavailability, missing
  output, and outside coverage.

### 6.5 NAS trial operation

- Run on Ubuntu 22.04 because ROS 2 Humble is the accepted runtime.
- Run one API service and exactly one worker service under the operating-system
  service manager.
- Use local PostgreSQL in the VM for trial metadata.
- Mount source data read-only and keep derived data on a separate writable
  location.
- Apply migrations explicitly during a controlled release, not concurrently
  from every service process.
- Bind the application behind an internal reverse proxy or equivalent trusted
  access boundary.
- Keep secrets outside Git with least-privilege file permissions.
- Provide health, logs, disk checks, backup, restore, upgrade, rollback, and
  manual-rescan procedures.
- Never expose the trial directly to the public internet.

## 7. Quality requirements

### 7.1 Truthfulness

Statuses describe stored facts. Estimates identify themselves as estimates.
The UI never presents unavailable work as failed, stale output as current, or
out-of-coverage media as available.

### 7.2 Responsiveness

Catalog and processing reads remain responsive while the worker processes a
large recording. Browser polling uses bounded queries. The table supports the
configured catalog limit without per-row HTTP calls.

### 7.3 Durability

Catalog, queue, failures, and ready artifact identities survive API, worker, and
VM service restarts. Worker interruption becomes a safe visible failure and can
be retried explicitly.

### 7.4 Accessibility

The reference design must remain usable by keyboard, retain visible focus,
provide meaningful status text independent of color, honor reduced motion, and
remain usable at the documented responsive breakpoints and 200% zoom.

### 7.5 Security and privacy

- No source or derived absolute path reaches the browser.
- Diagnostics omit credentials, traces, and private paths.
- External commands use argument arrays.
- API request sizes and list limits are bounded.
- The deployment has a trusted access boundary and no public listener.
- Credentials, private configuration, recordings, and derived artifacts are not
  committed.

## 8. Trial success criteria

V1 is ready for the limited engineering trial when:

1. A nested synthetic archive and the approved real archive scan into an
   accurate physical folder tree without modifying a source.
2. Recordings show truthful health and aggregate analysis states.
3. Selecting multiple recordings and choosing **Prepare selected** queues only
   missing current output and reuses compatible work.
4. The Processing view accurately reports current work, authoritative queue
   positions, wall and active elapsed time, cautious estimates, controls,
   failures, retries, cancellation, and history across restarts.
5. The served browser matches the `archive/` reference and contains no mock
   catalog, job, media, or telemetry data.
6. A prepared short and long recording remain synchronized and reusable.
7. The damaged case stays visible, gives useful diagnostics, and creates no
   impossible work.
8. The VM can be installed, upgraded, restarted, backed up, restored, and
   rolled back using the documented runbook.
9. The source mount is demonstrably read-only and before/after source inventory
   evidence is unchanged.
10. A limited engineer can reach the service through the approved internal
    access boundary without shell or Codex assistance.

## 9. Explicitly outside V1

- Public internet exposure or a public SaaS product.
- Application-managed user accounts, roles, or fine-grained permissions.
- Multiple workers, distributed scheduling, Redis, brokers, priorities,
  quotas, or automatic retry.
- Fabricated or approximate percent-complete processor instrumentation.
- Browser uploads, automatic filesystem watching, or source mutation.
- ROS bag repair, reindexing, conversion, or deletion.
- ROS 1, general MCAP, compression, split-bag, or arbitrary format support.
- Arbitrary topics, user-authored expressions, custom-message processing,
  commanded-motion graphs, LiDAR, point clouds, GPS, or maps.
- Annotations, comments, collaborative sessions, or saved shared views.
- Automated artifact retention or deletion.
- High-availability database, cross-region backup, or disaster-recovery
  guarantees.
- Redesigning the V1 reference frontend.

These are candidates for feedback-driven work after the NAS trial, not hidden
requirements of the three V1 blocks.
