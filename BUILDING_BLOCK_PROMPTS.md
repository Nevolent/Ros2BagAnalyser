# ROS 2 Bag Analyser — V1 Building Block Prompts

## How to use this file

Each section below is a complete implementation prompt. In a future task, the
user can say, for example, “Start V1 Building block 1 using its prompt in
`BUILDING_BLOCK_PROMPTS.md`.” That invocation adopts the corresponding section
as the task boundary and authorization.

An explicitly labelled proposed prompt is planning material only. It becomes
invocable only after its mandatory decision record is completed and approved.

Do not run multiple prompts together. Each block ends with user review and an
uncommitted handoff.

These prompts authorize ordinary implementation choices inside their explicit
boundary. They do not authorize commits, pushes, destructive operations,
public exposure, source mutation, or starting the next block.

## Prompt 1 — Backend preparation and processing operations

> **Correction note — 2026-08-05:** The separately approved move-aware
> artifact-reuse slice supersedes only Contract D's deferred rename behavior.
> An unambiguous folder move now preserves stable private cache anchors and
> compatible history/artifacts; ambiguous matches remain separate.

### Authorization and outcome

Implement V1 Building block 1 only: the backend catalog, preparation, aggregate
state, processing console, elapsed-time, and historical-estimate contracts in
the active V1 documents.

This prompt authorizes application code, additive/forward PostgreSQL migration,
tests, and owned documentation changes inside this boundary. It also authorizes
one final bounded read-only rescan of the configured development archive after
synthetic and PostgreSQL verification, provided a before/after inventory is
captured and no artifact processing is requested during that real check.

Do not edit the user-authored `archive/` reference or port the V1 frontend in
this block. Do not deploy a VM. Do not commit or push.

The completed outcome must let an API client:

- load a saved nested physical folder catalog without reading source paths;
- see source health, current per-output facts, and aggregate analysis state;
- submit one bounded **Prepare selected** request;
- see the current job, FIFO queue, current failures, and succeeded history;
- retry a failed current output safely; and
- display exact elapsed time plus a truthful estimate when enough compatible V1
  history exists.

### Mandatory initial audit

Before planning edits:

1. Read `README.md`, `PROJECT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `AGENTS.md`,
   and this prompt completely.
2. Read the relevant V0 archive sections for catalog safety, persistence,
   worker, artifact identity, processors, and real-data evidence.
3. Inspect Git status and every existing diff touching catalog, persistence,
   configuration, API, worker, artifact services, or tests.
4. Inspect all current migrations and the strict schema validator.
5. Trace current source resolution and cache-identity construction for front,
   top-down, and IMU.
6. Trace worker advisory locking, claim order, interruption recovery, artifact
   completion, and failed retry behavior.
7. Inspect current test fixtures and disposable PostgreSQL safeguards.

Then report before editing:

- inspected areas;
- exact Building block 1 boundary;
- expected files and migrations;
- test and acceptance plan;
- real-archive access that will occur only at the final acceptance step; and
- assumptions or existing user changes that affect the work.

Preserve unrelated changes. If an existing uncommitted edit overlaps the block,
integrate with it rather than replacing it.

### Contract A — Recursive physical discovery

Replace direct-child-only recording discovery with deterministic bounded
recursion.

The algorithm must:

1. Begin at the configured archive root without presenting the root as a folder
   node.
2. Enumerate entries without following symlinks.
3. Count every visited entry against a configurable global bound.
4. Count depth, directories, recording candidates, and direct entries against
   explicit bounds.
5. Treat a directory with a direct `metadata.yaml` entry as a recording
   candidate even if that entry is later found invalid; this keeps damaged data
   visible.
6. Stop descending once a recording candidate is identified.
7. Treat a leaf containing recognized recording companions but missing metadata
   as a damaged candidate when the existing V0 diagnostic model can describe it
   safely.
8. Treat other directories as physical navigation containers only.
9. Produce normalized POSIX archive-relative recording and parent-folder paths.
10. Reject `..`, absolute paths, backslash ambiguity, unsafe Unicode/filesystem
    text, and every symlink traversal.
11. Sort deterministically by safe relative path.

Distinguish two failure classes:

- a failure inside an identified recording is isolated into that recording's
  safe health/diagnostic;
- a failure that may have hidden an unknown branch makes the whole root snapshot
  incomplete.

An incomplete snapshot must not reach catalog apply, advance the catalog
generation, or mark saved recordings missing. Startup and catalog GET requests
must never invoke discovery.

Add configuration for maximum depth and global traversal bounds with
conservative defaults. Validate positive ranges and document them as operational
settings, not archive-specific constants.

### Contract B — Catalog generation and persistence

Add the next append-only migration. Preserve all existing IDs and rows.

The target V1 schema has the existing four tables plus:

#### `catalog_state`

One singleton row with constraints enforcing one identity. Store at least:

- successful generation, non-negative bigint;
- successful completion timestamp;
- duration milliseconds;
- recording count;
- precise health counts needed by the catalog response; and
- normal created/updated timestamps where consistent with repository style.

#### `recordings` additions

Add:

- `source_present BOOLEAN NOT NULL`;
- `last_seen_generation BIGINT NOT NULL` with a non-negative constraint.

Backfill current rows as present in generation zero. Do not change their ID,
relative path, source revision, components, jobs, or artifacts.

#### `preparation_targets`

Add exactly one current projection row per `(recording_id, kind)` for the three
supported kinds. Store:

- recording foreign key with cascade only when the recording itself is
  deliberately deleted by a future reviewed policy;
- artifact kind with the existing fixed-kind constraint;
- scan generation;
- 64-character planner identity;
- `available` or `unavailable` target state;
- nullable 64-character cache identity;
- nullable safe diagnostic code/message;
- nullable positive work units;
- created and updated timestamps; and
- a primary/unique constraint on recording and kind.

Enforce relational checks:

- available requires cache identity, work units, and no unavailability
  diagnostic;
- unavailable requires no cache identity and a diagnostic;
- generation and work-unit bounds are valid.

The planner identity covers every output-affecting configuration and version
needed to decide whether the stored target is current: topics, default IMU
component where identity-affecting, fixed registry/schema/policies, processor
versions, preview profile, encoder identity, and relevant executable/library
identity.

If the current application planner identity does not match a stored row, the API
reports `unavailable` with a rescan-required diagnostic. It does not parse or
stat the source in an ordinary request.

#### `jobs` estimate additions

Add nullable V1 fields that remain null for legacy jobs:

- positive `work_units`;
- non-empty bounded `estimate_key` or fixed-length digest;
- positive `estimated_total_ms`;
- bounded `estimate_method`;
- non-negative `estimate_sample_count`.

Add checks tying estimate fields together. Work units and estimate key are set
when V1 queues a job. Estimate result fields are frozen when the worker claims
it.

Add a partial unique index allowing at most one globally `running` job. Preserve
the existing active-identity unique index and FIFO queue index.

Add only measured/focused indexes for current target rollups, actionable
failures, succeeded history, and estimation samples. Update the strict schema
validator and migration tests exactly.

### Contract C — Scan-time target planning

Create a focused pure planning boundary shared by catalog apply and the existing
identity logic. Avoid three independent metadata parses per recording.

During an explicit scan, while validated metadata and source identities are
already available, calculate each target:

- front preview: exact topic/type/CDR/message-count prerequisites, current cache
  identity, ROS database work units;
- top-down preview: trusted bag origin and metadata/video/CSV prerequisites,
  current cache identity, AVI-byte work units;
- IMU series: exact configured standard topic/type/CDR/message-count
  prerequisites, current schema-version-2 cache identity, ROS database work
  units.

Do not perform full ROS message reads, AVI decode, CSV parse, or artifact
processing during scan. The targets describe whether work may be requested, not
whether expensive processing will ultimately succeed.

Apply recording/component/target rows and the generation atomically. Replace
the three targets for each seen recording in the same transaction. Mark targets
of missing recordings unavailable or exclude them from current matching without
deleting their history.

The worker remains authoritative at execution time: it reloads the actual
source, recomputes current identity, compares it with the queued target/cache
identity, and fails safely if anything changed after scan.

### Contract D — Successful reconciliation

Only after a complete snapshot:

1. acquire the catalog-apply advisory lock;
2. increment generation;
3. upsert recordings and components;
4. replace their three target projections;
5. set them present and seen in the generation;
6. mark previously present unseen recordings `source_present = false`, with
   precise missing health/diagnostic and no row deletion;
7. leave jobs/artifacts/history untouched;
8. write `catalog_state`; and
9. commit everything together.

An unchanged rescan preserves recording IDs and reuses compatible artifact rows.
An unambiguous path move preserves the recording ID and stable private cache
anchors while updating its current physical path. Ambiguous matches remain
separate. Retain unmatched old rows, jobs, artifacts, and history internally,
but exclude `source_present = false` rows from ordinary catalog lists, physical
folder nodes, and current scan/health counts so a move does not create a visible
duplicate or a false damaged count.

### Contract E — Aggregate state query

Implement bulk repository/application queries. Do not call the three current
source resolvers once per catalog row.

Ordinary catalog projections resolve only recordings present in the latest
complete generation. Historical missing rows require an explicit internal
history query and do not participate in current aggregate state.

For each current preparation target, derive output state in this order:

1. target missing, stale, or unavailable → `unavailable`;
2. matching compatible artifact → `ready`;
3. matching running job → `processing`;
4. matching queued job → `queued`;
5. latest matching failed job → `failed`;
6. otherwise → `not_requested`.

Validate ready artifacts using existing bounded derived-root rules. Design the
bulk path so it remains bounded and measured; it must not touch the source
archive.

Derive recording analysis state exactly:

```text
any output processing  -> processing
else any output queued -> queued
else any output failed -> failed
else all outputs ready -> ready
else                      not_planned
```

Return all three output facts even when aggregate detail is collapsed in the
table. Map precise ROS health to presentation `readable` or `damaged` without
discarding precise condition/diagnostic.

### Contract F — V1 catalog/detail APIs

Add versioned routes under `/api/v1` and preserve V0 routes during transition.
Use decimal strings for nanoseconds and byte sizes.

`GET /api/v1/catalog` must return one coherent saved view sufficient for the
complete Recordings page:

- latest successful scan generation/time/duration/counts;
- summary counts for recordings, ready, processing, queued, failed, and damaged;
- flat folder nodes with `path`, `parent_path`, `name`, direct count, and
  descendant count;
- bounded recording items with numeric ID, safe name, `folder_path`, recorded
  time, duration, size, storage/topic facts, precise/presentation health,
  diagnostic, aggregate analysis, and three output states.

The list, folder nodes, summaries, and saved scan counts include only
`source_present = true` rows. A retained path that is absent from the latest
complete scan must not appear as a duplicate or presentation-level damaged
recording.

It must perform no scan, create no work, expose no absolute path, and avoid
per-row HTTP/database/source N+1 behavior.

`POST /api/v1/catalog/rescan` must single-flight the bounded scanner, keep the
event loop responsive, apply only a complete snapshot, and return safe scan
facts. A failure retains the last catalog.

`GET /api/v1/recordings/{id}` returns real metadata, components, folder path,
health, aggregate/output states, coverage/provenance, and identity-bound ready
URLs. It starts no work and exposes no filesystem path.

### Contract G — Prepare selected

Add `POST /api/v1/recordings/prepare`.

Request:

```json
{"recording_ids": [12, 15]}
```

Validate a non-empty ordered list of unique positive numeric IDs with a default
maximum of 100. Reject malformed, duplicate, empty, or over-limit bodies with a
bounded 422 response.

For each ID in request order:

1. load current present recording and its three current planner-compatible
   targets;
2. preflight all three;
3. if any target is unavailable/stale, create no new job for that recording and
   return truthful per-output diagnostics;
4. otherwise reuse matching validated artifacts and active jobs;
5. treat this explicit request as retry permission for matching failed current
   outputs;
6. insert missing attempts in front, top-down, IMU order; and
7. return the new aggregate and per-output outcome.

Use the existing cache-identity advisory lock and active unique constraint.
Acquire multiple identity locks in a deterministic order to avoid deadlock.
Never decode/process in the request. One recording-level rejection does not
prevent other selected recordings from succeeding. Unexpected scheduling
transaction failure must be safely repeatable and must not leave duplicate
active work.

Response outcomes distinguish `ready_reused`, `active_reused`, `queued`,
`retry_queued`, `unavailable`, `not_found`, and isolated `request_failed`.
Return 202 when any work is queued/active and 200 when everything was reused or
rejected without work.

### Contract H — Processing query and retry APIs

Add:

- `GET /api/v1/processing/overview`;
- `GET /api/v1/processing/jobs?view=queued|failed|history&limit=&cursor=&q=`;
- `POST /api/v1/processing/jobs/{failed_job_id}/retry`.

Overview returns:

- server UTC time;
- worker online/offline from a non-mutating probe of the existing advisory lock;
- running, queued, actionable-current-failure, and succeeded counts;
- the single current job, if any;
- exact queued/started timestamps and elapsed milliseconds;
- frozen estimate facts;
- a bounded first FIFO queue page with global positions; and
- recommended poll interval.

Queued ordering and positions exactly match worker claim order:
`queued_at`, then job ID.

The failure view contains actionable latest failures for current target
identities only. A ready artifact or active retry supersedes the operational
failure, while the immutable attempt remains in database history.

Succeeded history is newest first, joins exact artifact output size when still
present, and uses stable cursor pagination over finish timestamp and ID. Bound
limit and search length. Cursor parsing must reject tampering/malformed values
safely.

Retry uses the failed ID only to find recording and kind. It resolves the
current target and then reuses/queues current identity. It never blindly reruns
the failed cache identity. Unknown/nonfailed IDs return a safe conflict/not-found
response. Double-click retry returns the already active/current outcome.

### Contract I — Worker availability and estimate

Probe worker ownership using the existing advisory-lock key on a short-lived
database connection. If the probe acquires the lock, release it immediately and
report offline. If it cannot, report online. A probe never starts a worker or
changes a job.

When claiming a V1 job, estimate total time from a bounded recent set of
succeeded jobs with the same estimate key and valid positive work units.

For each sample:

```text
rate = runtime_ms / work_units
```

Require at least two compatible samples. Use the median rate and multiply by the
claimed job's work units. Freeze predicted total, method, and sample count on
the job. Exclude failures, interruptions, null/zero work units, invalid
timestamps, incompatible estimate keys, and missing invalid artifacts.

API/UI semantics:

- valid estimate and elapsed below total → approximate remaining;
- too few samples or invalid facts → unavailable;
- elapsed at or beyond total → exceeded, with no fake `00:00` remaining.

Do not expose percent complete, queue-wide completion promises, or hard-coded
benchmark estimates.

### Required implementation order

1. Write response/state/schema tests that freeze the V1 vocabulary.
2. Implement and verify the migration/backfill on a faithful V0 database.
3. Implement recursive discovery and complete/incomplete scan tests.
4. Add scan-time planning and identity-sharing without duplicating cache logic.
5. Implement atomic generation apply and missing reconciliation.
6. Implement bulk aggregate repository queries and derived-artifact checks.
7. Implement Prepare selected and concurrency/deadlock/idempotency tests.
8. Implement Processing overview, views, stable cursors, and retry.
9. Implement claim-time estimate and worker-lock probe.
10. Add V1 schemas/routes and error sanitation.
11. Measure catalog and Processing queries with the configured maximum-sized
    synthetic catalog; add indexes only from evidence.
12. Run all accumulated routine, PostgreSQL, ROS-message, worker, artifact,
    range, JavaScript, and launcher regressions.
13. Run manual synthetic acceptance.
14. Only then run the approved bounded real rescan and source inventory check.

### Required automated verification

At minimum cover:

- root and deep recordings, folder counts, deterministic sort, stop-at-recording
  root, metadata-missing candidate, symlinks, unsafe names, inaccessible branch,
  depth/entry/recording bounds, and incomplete-scan retention;
- unchanged, missing, and reappearing recording generations without destructive
  cascade;
- path moves retain old rows/history internally while presenting exactly one
  current row and current-only counts;
- exact migration schema, constraints, backfill, global-running uniqueness, and
  preservation of legacy rows;
- available/unavailable/stale target planning for all three kinds;
- planner identity change requiring rescan;
- worker-side post-scan source-change rejection;
- every aggregate precedence combination, including partial legacy ready data;
- no source read from catalog/processing GET routes;
- bounded catalog query count and response size;
- Prepare selected body validation, all-three preflight, stable order, ready
  reuse, active reuse, failed retry, unavailable/not-found mixture, concurrent
  double requests, and rollback/repeat behavior;
- exact FIFO positions and the one-running constraint;
- actionable failure supersession, history output join, stable cursor behavior
  while new rows arrive, search bounds, and retry-current-identity;
- worker probe online/offline and immediate lock release;
- estimate cold start, median, compatibility, invalid/zero units, malformed
  timestamps, interruption exclusion, sample bound, freeze, and exceeded state;
- database failures and safe diagnostics; and
- every existing processor, publication, identity URL, timing, IMU, worker, and
  source-safety regression.

### Manual and real-data acceptance

Use a nested synthetic archive and disposable PostgreSQL database to demonstrate:

- saved startup;
- explicit scan and physical folder counts;
- retained catalog after incomplete scan;
- mixed new/ready/failed/unavailable selection;
- Not planned → Queued → Processing → Ready/Failed transitions;
- one running job and stable queue;
- offline worker/paused queue;
- exact elapsed plus unavailable/available/exceeded estimate examples;
- explicit retry;
- API and worker restart persistence; and
- ordinary catalog/processing responsiveness during an active job fixture.

For the final real rescan, validate the exact configured archive and separate
derived root first. Capture lightweight before inventory outside the archive,
perform only the bounded rescan and API reads, capture after inventory in a
`finally`-equivalent path, and require an exact comparison. Confirm scan created
no job/artifact and no source-side entry.

### Prohibited scope

Do not:

- edit `archive/` or implement the V1 visual frontend;
- add a combined preparation job or artifact;
- change processor formats, cache identities, timing, or coverage;
- add multiple workers, cancellation, priority, reordering, lease recovery,
  auto retry, watchers, uploads, retention, or cleanup;
- add route-time full source reads;
- install a frontend or job-framework dependency;
- access the NAS deployment environment; or
- commit/push.

### Stop conditions

Stop and request direction only if the work requires source writes, following
source symlinks, destructive catalog deletion, another worker, a new processor
or artifact kind, a timing/identity change, a major dependency, or a material
contract change. Ordinary naming, query, refactoring, and test-fixture decisions
inside this prompt should be resolved autonomously and documented.

### Completion handoff

Report:

- exact boundary completed;
- files and migration changed;
- final schema/tables/indexes and backfill behavior;
- final API request/response contracts;
- query count/plans or measurements;
- all commands and test results;
- synthetic/manual and real acceptance actually performed;
- source inventory evidence;
- visible state and estimate observations;
- assumptions, limitations, and deferred work;
- final Git status and explicit uncommitted state; and
- the user review required before Building block 2.

## Prompt 2 — Reference frontend integration

> **Completion note — 2026-08-04:** Building block 2 was accepted. The later,
> separately approved smooth front-camera corrective slice supersedes only this
> prompt's prohibition on image-header timing for internal front-frame cadence.
> Measured coverage and global placement still use retained ROS record
> endpoints. See `ARCHITECTURE.md` section 15 and the recorded correction in
> `ROADMAP.md`.

### Authorization and outcome

Implement V1 Building block 2 only: promote the user-authored frontend under
`archive/` into the served application without redesigning it, and replace all
mock data and simulated behavior with the accepted Building block 1 APIs and
existing real artifact/timeline behavior.

This prompt authorizes served frontend code, packaged local assets, the
refreshable `/processing` shell route, focused static/API/browser tests, and
owned documentation evidence. It authorizes final read-only real-data browser
acceptance against the configured development archive and separate derived root,
including preparation of missing current output for one selected short readable
recording if required. Capture a complete lightweight source inventory before
and after. Prefer reusing existing ready output for long-case acceptance.

Do not alter `archive/` itself. Do not redesign the interface, add a frontend
framework, deploy the NAS VM, commit, or push.

The completed outcome must serve three real, refreshable product views:

- `/` — Recordings with physical folders and Prepare selected;
- `/processing` — current work, FIFO queue, failures, and history;
- `/recordings/{numeric_id}` — metadata, real cameras, six-channel IMU, and the
  accepted global timeline.

No production runtime path may contain mock recordings, mock jobs, fake timers,
fake processing progress, mock sensor samples, or static preview imagery
presented as real output.

### Mandatory initial audit

Before editing:

1. Read all active V1 documents and this prompt completely.
2. Read Building block 1's final handoff, migrations, schemas, API tests, and
   actual response fixtures.
3. Read the archived V0 timing, media delivery, IMU graph, browser acceptance,
   and accessibility evidence.
4. Inspect Git status and all existing diffs in served web files and browser
   tests. Preserve unrelated/user work.
5. Inspect every file under `archive/`, excluding macOS resource-fork debris
   from the implementation asset set.
6. Inspect the current served `index.html`, CSS, application runtime, IMU graph
   helper, static routes, package data, CSP, and browser tests.
7. Render the reference through the approved browser workflow at all acceptance
   viewports and record screenshots/interaction notes before changing served
   files. If browser tooling is unavailable, report that limitation and use a
   deterministic local rendering fallback only when permitted by the available
   tool instructions.

Then report:

- reference and served areas inspected;
- exact frontend-only boundary;
- expected files/assets/tests;
- visual, runtime, API, accessibility, and real-data verification plan;
- which reference interactions map to which V1 API; and
- assumptions affecting dynamic text or absent thumbnail data.

### Contract A — Preserve the authored design

Treat these reference qualities as fixed:

- Tectrace-branded top bar and compact navigation rail;
- Recordings, Analyzer, and Processing navigation icons and active states;
- dark/light theme behavior already present in the authored files;
- physical folder panel, search, collapse/expand, connecting branches, and
  count presentation;
- recording heading, scan status, summary cards, filter bar, dense table,
  selection footer, and pagination;
- Processing heading, auto-refresh control, three summary tabs, current-job
  card, indeterminate track, queue/failure/history tables, and diagnostic dialog;
- Analyzer metadata sidebar, front/top camera proportions, telemetry card,
  sensor picker, transport placement, and graph styling;
- spacing, radii, colors, borders, typography stack, icon language, hover/focus
  behavior, responsive breakpoints, and reduced motion.

Real values will change text length and counts. Make narrow, evidence-driven CSS
corrections for truthful data, but do not simplify the authored hierarchy or
substitute the old V0 visual design.

Keep `archive/` byte-for-byte unchanged as the comparison source. Copy only the
assets genuinely needed by the served package. Do not package `__MACOSX` files.

The reference preview images are mock content. Do not show them for a real
recording. If no ready video exists, keep the camera card shape and render a
neutral state message. Do not create a thumbnail processor in this block.

### Contract B — Frontend routing and state

Implement a small dependency-free browser state model with distinct domains:

- route/view state;
- saved catalog and scan-request state;
- folder/filter/sort/page/selection state;
- preparation-request outcomes;
- processing polling/filter/pagination state;
- selected recording detail/output state; and
- shared timeline/media/IMU state.

Use the History API for `/`, `/processing`, and `/recordings/{id}`. Direct loads,
refresh, back, forward, the brand link, rail buttons, table links, failure/history
Open actions, and incomplete-analyzer actions must all resolve correctly. The
FastAPI shell route serves the same packaged document for all three patterns and
rejects invalid numeric routes safely.

On navigation:

- abort or invalidate obsolete requests;
- stop view-specific polling and animation;
- retain harmless Recordings filters/selection in memory when returning during
  the same page session;
- reset selected-recording media and revoke no shared external resource
  incorrectly; and
- never let a slow older response overwrite the active route.

Use `AbortController` where supported plus a monotonically increasing request
generation or equivalent stale-response guard.

### Contract C — API adapter and safe rendering

Create one focused JSON request helper that:

- verifies HTTP success and expected JSON shape;
- distinguishes network, HTTP, validation, and aborted requests;
- surfaces only safe backend messages;
- provides a retryable presentation error;
- never treats HTML error bodies as markup; and
- works with relative same-origin `/api/v1` URLs.

Render all backend-controlled folder segments, names, filenames, diagnostics,
topics, units, and errors through `textContent`, explicit DOM nodes, or an
equally safe construction. Do not interpolate backend strings into
`innerHTML`, event attributes, CSS selectors, or URLs. Fixed inline SVG/template
markup may be static and reviewed separately.

Only use backend-provided identity-bound relative media/data URLs after
validating their expected same-origin prefix. Never construct a source path or a
derived filesystem URL in the browser.

### Contract D — Recordings view

On initial `/` load:

1. show the authored loading state;
2. request `GET /api/v1/catalog` exactly once;
3. do not rescan or prepare;
4. render saved scan time/counts, summary cards, folder tree, table, and footer;
5. show an authored empty state for an empty saved catalog; and
6. show a retry state on initial failure.

If a later refresh or rescan fails, keep the last successful catalog visible,
mark it retained/stale, show the safe failure and retry, and do not clear table,
folder, filters, or selection unnecessarily.

Build folders from backend flat nodes. Use physical path keys, not display text,
for selection. Selecting a parent includes descendant recordings. Folder search
reveals matching ancestors/descendants and accurate empty state. Collapse state
may persist locally as visual preference only; do not persist source/catalog
facts in browser storage.

Render summary cards from backend global counts. Card clicks toggle the matching
filter and remain synchronized with the select controls.

The table must preserve authored behavior:

- real name and safe source-relative sublabel where the API contract permits;
- recorded time, duration, size, health, and analysis;
- precise status tooltip with all three output states;
- search, health/analysis filters, stable sort, page size, page buttons, and
  empty result;
- row link opens `/recordings/{id}`;
- checkbox click never navigates;
- select-all selects only the visible page;
- selection keys are numeric recording IDs, not row positions/names; and
- selection summary/button disabled state stays correct across filters/pages.

Damaged/unavailable rows may be selected only if the backend is allowed to
return a truthful rejected outcome; preferably disable impossible selections
with an accessible reason if Building block 1 exposes enough facts. Never
silently drop a selected ID.

### Contract E — Prepare selected flow

On **Prepare selected**:

1. freeze the current ordered selected numeric IDs;
2. disable duplicate submission and mark the control busy;
3. send one `POST /api/v1/recordings/prepare` request;
4. validate every returned recording/output outcome;
5. announce queued, reused, unavailable, not-found, and failed counts;
6. refresh the saved catalog view from the server;
7. clear only IDs successfully queued/reused when that is understandable, or
   clear the entire submitted selection with an explicit outcome summary;
8. retain rejected outcomes visibly long enough to be understood; and
9. navigate to `/processing` when at least one output is queued or active.

If all selected recordings were already ready, keep the user on Recordings and
announce reuse. If every selection is unavailable/rejected, keep the user on
Recordings with safe per-recording feedback. A request error creates no fake
status transition and permits explicit retry.

### Contract F — Rescan flow

The authored Rescan control sends `POST /api/v1/catalog/rescan` only after a
user click. While active, show busy/scanning state and prevent an overlapping
click. On success, reload the saved catalog and announce real counts/duration.
On failure, retain the previous catalog and folder state as above.

Opening, refreshing, navigating, polling Processing, or preparing recordings
must never initiate a scan.

### Contract G — Processing view

Render `/processing` from real overview and job APIs.

#### Current job

Show at most one current job with:

- output display name mapped from fixed artifact kind;
- recording name and numeric route;
- started/queued ages;
- exact elapsed duration;
- approximate remaining, Estimating/Not enough history, or Estimate exceeded;
- indeterminate track; and
- worker-offline banner when the advisory-lock probe says offline.

Tick elapsed locally with a monotonic browser clock anchored to server `as_of`
and `started_at`. Resynchronize on each accepted poll. Do not increment backend
mock fields or alter ETA locally.

#### Queue

Render backend FIFO positions and queued ages. Do not renumber after client-side
search as if filtered positions were global. Empty queue and offline-worker
states remain distinct.

#### Failures

Render actionable current failures only. Details dialog uses safe text nodes,
restores focus on close, supports Escape/backdrop behavior, and shows attempted
time/runtime/code/message without paths/traces. Retry disables only the relevant
control, calls the V1 retry endpoint, handles idempotent active reuse, refreshes
overview/failures, and announces the outcome.

#### History

Render succeeded completion time, runtime, output size when present, recording,
output, and Open action. Implement bounded cursor pagination/load-more without
duplicates. Do not imply a missing historical artifact is currently ready.

#### Refresh behavior

- Initial active polling interval follows backend `poll_after_ms` with a safe
  minimum.
- Auto-refresh toggle affects polling only, never worker processing.
- Manual refresh works while auto-refresh is off.
- Pause/slow polling while `document.hidden`; refresh immediately when visible.
- Only one poll per resource is in flight.
- Backoff transient failures and show “last updated” truthfully.
- Discard stale responses after tab/filter/route changes.

### Contract H — Analyzer detail

On `/recordings/{id}`, load one V1 detail response and populate the authored
metadata sidebar with real:

- name, recorded time, duration, source size, storage, messages, topics, and
  precise ROS health;
- metadata, ROS database, top-down video, and top-down timestamps facts;
- front, top-down, and IMU output states, formats, sizes, coverage, warnings,
  and diagnostics.

The Analyzer has no ordinary per-pane Generate buttons. For a complete Ready
recording, attach real media/data. For not planned, queued, processing, failed,
or unavailable output, preserve the card layout with a concise state message
and an action that navigates to Recordings selection or Processing as
appropriate. Do not create a hidden per-output POST shortcut.

Preserve existing accepted functionality rather than reimplementing it from the
mock:

- one browser-owned bag-relative clock;
- play, pause, end, explicit seek, and monotonic reanchor;
- identity-bound front/top media URLs and byte-range behavior;
- `media_time = global_time - coverage_start` mapping;
- 100-millisecond drift correction;
- force seek on explicit slider/graph input;
- measured coverage and hide/clear outside it;
- independent media/data failure without stopping other consumers;
- schema-version-2 IMU parsing with decimal nanoseconds;
- six fixed options in registry order;
- exact label/unit/extrema/gap facts;
- source-order duplicates and duplicate-last current lookup;
- static trace redraw only on data/selection/resize;
- persistent pixel-snapped cursor overlay;
- pointer/touch/keyboard graph seeking and one-frame coalescing.

The authored absolute Unix-time display may show `bag_start + elapsed` while
internal synchronization remains bag-relative integer time. Accessible text
must include meaningful elapsed position and total. Never use message header
time or AVI nominal time to imitate the mock display.

### Contract I — Accessibility, security, and resilience

Retain or improve without redesign:

- semantic landmarks and headings;
- skip navigation;
- visible keyboard focus;
- keyboard folder, table, tabs, dialog, graph, sensor picker, and transport
  interaction;
- accessible selected/expanded/busy/current states;
- polite live announcements that do not fire every poll second;
- status text/icons independent of color;
- reduced motion and disabled decorative processing animation where requested;
- 200% zoom and narrow layout without document-level horizontal overflow; and
- touch target/scroll behavior at small widths.

Respect current CSP and security headers. Use no external CDN, analytics,
tracking, remote font, or dynamically evaluated code.

### Required implementation order

1. Capture reference viewport screenshots and interaction inventory.
2. Write a field/action mapping from every mock element to API/static/removed.
3. Add/verify shell routing and package assets.
4. Port static semantic shell and CSS with reference screenshots unchanged.
5. Build safe API adapter, router, and top-level state lifecycle.
6. Wire saved catalog/folders/table/rescan.
7. Wire selection and Prepare selected.
8. Wire Processing overview/tabs/polling/retry/history.
9. Wire detail metadata and per-output placeholders.
10. Reuse/adapt accepted timeline, media, and IMU code inside authored layout.
11. Remove every mock dataset, fake rescan/retry, fake elapsed interval, and mock
    media/telemetry source from served runtime.
12. Run syntax/static/browser/API and full accumulated regressions.
13. Perform visual/accessibility matrix with synthetic API fixtures.
14. Perform explicitly approved real-data acceptance with inventory guard.
15. Record evidence and stop for user review.

### Required automated verification

At minimum cover:

- package/static routes for `/`, `/processing`, `/recordings/{id}`, CSS, scripts,
  icons/assets, CSP, and security headers;
- no external runtime asset and no `archive/__MACOSX` packaging;
- startup saved-catalog request and proof of no implicit rescan;
- retained catalog/folder/selection after refresh/rescan failure;
- physical folder construction, ancestor counts, search, collapse, selection,
  and empty state;
- summary/filter synchronization, safe sort, pagination, selection by numeric ID,
  and visible-page select-all;
- every health/analysis/output state and hostile backend strings;
- one Prepare request, busy/double-click handling, partial outcomes, navigation,
  all-ready reuse, all-unavailable rejection, and request retry;
- processing current/idle/offline, FIFO positions, elapsed anchor, all estimate
  states, auto/manual/hidden refresh, stale response discard, error backoff,
  failure dialog, idempotent retry, history cursor, and Open navigation;
- direct route refresh/back/forward and request cleanup;
- real metadata and component rendering with no paths;
- existing media range URLs, load/reload failure, synchronized play/pause/seek,
  clock end, coverage, drift correction, and independent consumer failure;
- six-channel IMU validation/selection, graph dimensions, current lookup, null
  gaps, duplicates, graph seek, cursor compositing/coalescing, and render retry;
- keyboard/focus/live/busy/dialog/reduced-motion/zoom/narrow-view behavior; and
- a static/runtime guard proving no mock recording arrays, mock job rows, fake
  state-advancing interval, static preview-as-real source, or mock IMU bundle is
  reachable in the served product.

### Visual acceptance matrix

Use paired reference and served screenshots at:

- 1600×900;
- 1366×768;
- 1024×768;
- 901×800;
- 900×800;
- 600×800;
- exact 320×800 CSS viewport;
- 200%-zoom-equivalent viewport; and
- reduced-motion emulation.

Inspect Recordings with folder open/collapsed, Processing queue/failure/history,
Ready Analyzer, incomplete Analyzer, dialogs, long names, empty states, and error
states. Record intentional differences caused only by real dynamic content.

### Real-data acceptance

After all synthetic/browser tests pass:

1. Validate configured source and derived roots are separate.
2. Capture a complete lightweight before inventory outside the archive.
3. Start exactly one API and one worker using the reviewed code/configuration.
4. Load saved real catalog without scan.
5. Run one explicit rescan and verify physical folders/counts.
6. Exercise a mixed selection containing readable/reusable and damaged cases.
7. If needed, prepare missing current output only for one selected short readable
   recording and observe the real Processing view.
8. Prefer reuse for the accepted long recording; verify load/seek/graph
   responsiveness without unnecessary regeneration.
9. Open the damaged case and verify health, detail, and zero impossible jobs.
10. Reload/restart and verify catalog, queue/history, and ready reuse.
11. Capture the after inventory even if a check fails and require exact match.
12. Confirm every generated file remains under the derived root.

### Prohibited scope

Do not:

- edit the `archive/` reference;
- redesign visual flow or replace it with the old frontend;
- add a framework, npm runtime, chart/icon library, CDN, external font, or
  analytics;
- add a thumbnail, bundle, processor, artifact kind, or backend workflow;
- expose source/derived paths;
- restore per-output Generate buttons;
- change time, coverage, drift, artifact identity, range, or IMU rules;
- add deployment/service/authentication work; or
- commit/push.

### Stop conditions

Stop and request direction if exact integration requires a new API capability
not accepted in Building block 1, new processor/artifact kind, material visual
redesign, major dependency, unsafe DOM behavior, or synchronization contract
change. Resolve ordinary responsive CSS, event lifecycle, request cancellation,
and test-fixture decisions autonomously.

### Completion handoff

Report:

- exact boundary and files/assets changed;
- explicit confirmation that `archive/` stayed unchanged;
- mock-to-real mapping and removed mock behaviors;
- API routes consumed and refreshable browser routes;
- commands/tests with results;
- paired visual matrix and accessibility observations;
- real-data workflow and source inventory actually completed;
- timing, seek, media, graph, polling, and responsiveness observations;
- assumptions, limitations, and deferred work;
- final Git status and uncommitted state; and
- user review required before Building block 3.

## Prompt 2A — Big UI overhaul and real processing controls

> **Invocation note — 2026-08-23:** The user accepted the complete application
> and repository-readiness work preceding this prompt as the working baseline,
> approved the overhaul decisions below, and invoked this prompt as the next
> implementation block. The separately authorized baseline Git checkpoint and
> push happen before overhaul implementation. This does not claim that the
> pending live Building block 3 VM/NAS phases have occurred.

### Why this is a separate overhaul block

The current authored reference consists primarily of:

- archive/index.html, SHA-256
  5373286fcbb810cf57052a2e93c6d7e23fa1a888100635496ca8524e488f85c0;
- archive/styles.css, SHA-256
  01eb93298827c4eb430f8e135184ad0a70904193cafa5d6dc05946195388f3d0;
- archive/script.js, SHA-256
  a5d85e834c7bf6fa5fd8c38f3b917d451ed4857f3df50e43d8e75423427246e9;
  and
- archive/assets/tech-trace-icon.svg, SHA-256
  b2fb92cb3af87871869f2c826d7a17e4617e9572ef82c08915c15f74d4c3646a.

Those three authored page files are dated 2026-08-23. The current served
index.html, styles.css, and app.js predate them. Because archive/ is untracked,
Git cannot prove that the present reference is the same revision used for the
accepted Building block 2 screenshots.

The current reference also contains controls and behavior outside the accepted
pre-overhaul baseline: pausing a running attempt, canceling current or queued
attempts, changing FIFO order, cumulative queue-ready estimates, percentage
progress, selectable subsets of the three preparation outputs, and a zoomed
graph display window. These must become truthful real behavior under the
decisions below rather than remaining DOM simulations. The reference also
contains an Experiments/Files surface that the user explicitly identified as
leftover.

This corrective block exists to freeze the new intended visual reference,
remove its leftover/mock-only material, decide which newly shown operations
become real product contracts, and then integrate the approved result without
weakening source, artifact, identity, timing, or deployment safety.

### Approved overhaul decision record

These decisions were approved on 2026-08-23:

1. **Reference subset**
   - Recordings, Processing, Analyzer, their dialogs/toasts, the dark shell,
     responsive states, focus states, and the graph are the visual reference.
   - Experiments/Files, the hidden old Analyzer recording list, macOS resource
     forks, mock preview thumbnails, mock Figure 8 media, mock IMU payloads, and
     unused prototype/theme surfaces are excluded.
2. **Recording name and date**
   - The Recordings table uses the friendly recording name only as its primary
     identity and removes the separate Recorded column from the front table.
   - Exact source name and recorded timestamp remain truthful in Analyzer
     detail and accessible/title context where useful. Recorded time always
     comes from start_time_ns, never filename parsing.
3. **Preparation output selection**
   - The three checkboxes are real. A non-empty subset of front preview,
     top-down preview, and IMU series can be prepared.
   - A partial completed subset remains Not planned until all three current
     outputs are ready. Ready Analyzer consumers remain independently usable.
4. **Processing controls**
   - The expanded pause/resume, cancel current/queued, queue reorder, bulk
     cancel, and bulk failed-retry state machine in Contract G is approved.
5. **Progress and queue estimates**
   - Factual elapsed/active time and historical likely duration are required.
   - Numeric progress is shown only for phases with exact completed/total units;
     all other phases are indeterminate.
   - Cumulative queue-ready estimates are approved only as explicitly
     approximate and become unavailable when their prerequisites are unknown.
6. **Graph window**
   - Shift-drag zoom, zoom buttons, reset, wheel scrub, keyboard controls, and
     automatic window paging are approved presentation behavior over the one
     global recording clock.
7. **Visual acceptance**
   - The full viewport/state matrix is approved. Every unexplained layout or
     style difference is a failure; controlled masks are limited to genuinely
     dynamic video, canvas, and ticking-time pixels.

Update PROJECT.md, ARCHITECTURE.md, ROADMAP.md, and AGENTS.md for this dated
overhaul contract before application-code implementation. Keep every earlier
acceptance record intact.

### Authorization and outcome

Implement this overhaul block only after the approved baseline checkpoint is
pushed. Pause live Building block 3 work while the overhaul is active. Do not
combine frontend/backend overhaul implementation with live VM/NAS commissioning.

The invoked prompt may authorize:

- porting the approved current reference into the served dependency-free web
  package;
- focused V1 API, persistence, worker, processor-control, migration, and
  deployment-readiness changes required by the approved decisions;
- synthetic/disposable database, media, browser, worker, and interruption
  tests;
- owned contract and acceptance documentation; and
- a separately approved final read-only real-data acceptance annex.

It does not authorize editing archive/, installing a major dependency, changing
source formats or artifact kinds, accessing the authoritative NAS source
without its annex, live VM mutation, public exposure, or source mutation. The
2026-08-23 user instruction separately authorizes one baseline checkpoint
commit and push before implementation; it does not pre-authorize the later
overhaul completion commit or push.

The completed served product must:

- be visually indistinguishable from the approved Recordings, Processing, and
  Analyzer reference states except for documented truthful dynamic content and
  the deliberate removal of Experiments/Files;
- contain no mock recording, folder, status, job, timer, percentage, estimate,
  history, diagnostic, video, thumbnail, or IMU value;
- make every visible enabled control perform a real, persistent, concurrency-
  safe backend or browser action;
- hide or visibly disable a reference control when its capability was not
  approved, rather than simulate it;
- retain one read-only source archive, one separate derived root, one
  PostgreSQL catalog/job model, one serial worker, three artifact kinds, and one
  browser-owned recording clock; and
- preserve all accepted processor, artifact, identity, range, timing, coverage,
  move-reconciliation, low-space, and deployment-readiness behavior outside the
  explicitly approved correction.

### Mandatory initial audit

Before editing application code:

1. Read every active V1 document, this corrective prompt, Prompt 2's completion
   record, and the relevant V0 processor/timing/artifact evidence completely.
2. Inspect Git status and every overlapping diff. Treat accepted uncommitted
   Blocks 1–3, corrective slices, archive/, and user assets as user work.
3. Recompute and record the reference hashes above. Stop if they differ until
   the user confirms the intended revision.
4. Inventory the final rendered DOM and CSS cascade, not only source order.
   Identify visible, hidden, overridden, unreachable, and leftover elements.
5. Render the current reference at every approved viewport and capture:
   - Recordings default, folders collapsed, selected, filtered, empty, scanning,
     preparation dialog, and toast;
   - Processing running, pause-requested, paused, cancel-requested, queue,
     selected queue,
     failures, diagnostic, history, and cancel confirmation;
   - Analyzer default, compact details, sensor menu, scrub, play, zoom
     selection, zoomed window, reset, outside coverage, and unavailable output;
   - keyboard focus, coarse pointer, reduced motion, and long hostile text.
6. Inspect the current served shell, CSS, application runtime, graph helper,
   static routes, CSP, package data, and browser tests.
7. Map every visible text node, badge, count, action, timer, table cell, dialog
   row, graph value, media source, and state to one of:
   - existing backend fact;
   - approved new backend fact;
   - deterministic browser presentation of a backend fact;
   - static interface decoration; or
   - removed leftover/mock behavior.
8. Inspect migrations and exact jobs constraints/indexes, preparation and
   processing repositories, worker claim/recovery, all three processor loops,
   external command handling, artifact publication, low-space admission, and
   deployment schema validation before designing job controls.
9. Prove whether each processor has a bounded safe control checkpoint. Measure
   acknowledgement delay with synthetic work; do not claim immediate pause or
   cancellation from inspection alone.
10. Inspect the current API response fixtures and determine which diagnostic
    facts genuinely exist. Never manufacture topic, filename, expected/actual,
    recovery, percentage, or estimate fields merely to fill the mock layout.
11. Confirm that no new table is required unless separately approved. Building
    block 3 currently validates exactly six V1 domain tables.
12. Report the exact approved decisions, files expected to change, migration
    impact, test plan, visual baseline, real-data boundary, and stop conditions
    before implementation.

### Contract A — Frozen reference and exclusions

Keep archive/ byte-for-byte unchanged. It is comparison material, not served
runtime.

Preserve the approved final rendered qualities:

- graphite dark shell, 44-pixel top bar, Tectrace brand, compact icon rail, and
  active-item treatment;
- folder panel, connector hierarchy, counts, search, collapse/reveal behavior,
  and overlay/card transitions at the final CSS cascade's breakpoints;
- Recordings title/scan status, dense filters/table/footer, selection
  transitions, dialogs, and toast;
- Processing current-job card, three tab views, tables, diagnostics, selection
  treatments, and confirmation flows approved by the decision record;
- Analyzer metadata panel, compact/expanded staged layout, 16:9 front pane,
  4:3 top pane, telemetry pane, picker, graph, controls, and transport;
- typography stack, density, spacing, radii, borders, colors, icon stroke
  language, focus rings, hover states, selected states, and reduced motion.

Exclude from the served product:

- the Experiments rail button and the full Files view;
- fake PDFs, Office/Figma/ZIP entries, owners, email addresses, dates, and file
  states;
- the hidden legacy Analyzer recording list;
- mock recording thumbnails and static preview posters as real output;
- archive/figure8-front.mp4, archive/figure8-top-view.mp4,
  archive/figure8-imu-bundle.json, the missing figure8 JavaScript bundle, and
  synthetic fallback IMU;
- archive/__MACOSX and every Apple metadata sidecar;
- unreachable old processing/diagnostic handlers and unused prototype theme,
  breadcrumb, shortcut, row-menu, and summary surfaces unless the decision
  record explicitly adopts them.

Package only assets needed by the real served interface. The Tectrace SVG may
be copied unchanged. Reference preview images may be used by an isolated visual
fixture but never shipped or selected as a recording's output.

### Contract B — Visual parity method

Create a deterministic visual harness for both reference and served pages.
Where the reference currently generates mock data, inject a fixture whose text
lengths and states match an equivalent synthetic V1 API fixture. Do not compare
an arbitrary real catalog against fixed mock strings and call the resulting
layout drift acceptable.

For every approved state:

- capture reference and served screenshots at identical CSS viewport, device
  pixel ratio, color scheme, reduced-motion, font availability, and scroll
  position;
- compare shell geometry, panel bounds, grid tracks, gaps, padding, line
  heights, control bounds, border radii, colors, shadows, and responsive
  stacking;
- record any intentional difference, its contract reason, and its owning test;
- fail acceptance for unexplained extra controls, missing controls, overflow,
  clipped focus, wrong hierarchy, wrong aspect ratio, or materially different
  density;
- use controlled dynamic masks only for video/canvas pixels and genuinely
  ticking time; do not mask whole panels or controls; and
- keep baseline images/evidence outside runtime package data unless small,
  reviewed test fixtures belong in Git.

Do not copy all 5,879 lines of reference CSS blindly. Port the final effective
rules for approved surfaces, remove leftover selector dependencies, and retain
the rendered result. Add stable semantic hooks only where they do not change
appearance.

### Contract C — Routes, state, and safe rendering

Keep the three refreshable routes:

- / for Recordings;
- /processing for Processing; and
- /recordings/{positive numeric id} for Analyzer.

Use one dependency-free state model with separate route, catalog, folder/filter,
selection, preparation, processing, dialog/toast, recording detail, media,
telemetry, graph-window, and job-control state.

On route or tab change:

- abort obsolete requests and ignore stale responses by generation;
- stop view-specific polling, animation frames, graph gestures, media work, and
  control timers;
- retain harmless Recordings filters/selection for the page session;
- close dialogs and restore focus predictably;
- do not leak one recording's media, diagnostics, graph window, or control state
  into another; and
- keep direct load, refresh, Back, Forward, brand, rail, table, history, and
  diagnostic navigation correct.

Use a single same-origin JSON adapter that validates status and response shape,
distinguishes aborted/network/HTTP/validation/conflict errors, bounds safe
messages, and never renders an HTML error body.

Construct backend-controlled names, folder segments, filenames, topics,
diagnostics, expected/actual facts, recovery text, units, and errors with safe
DOM nodes and textContent. Never interpolate them into innerHTML, selectors,
event attributes, CSS, or URLs. Validate identity-bound media/data URLs against
the exact allowed same-origin route pattern.

### Contract D — Recordings view

Initial load must request the saved V1 catalog once and start no rescan,
preparation, or artifact work.

Render:

- the real physical folder hierarchy and backend descendant counts, without
  inventing the mock's year/month folders;
- the approved name/date presentation from the decision record;
- real duration, source size, source health, aggregate analysis, and precise
  three-output tooltip facts;
- the real last successful scan time and current retained/stale status;
- current filters, stable sort, 20-row pagination, visible-page select-all,
  selection count, and numeric recording links; and
- loading, empty catalog, empty filter, initial failure, and retained-catalog
  rescan failure states in the approved reference layout.

If “name only” means removing a valid leading YYYY_MM_DD_ prefix from the
friendly label, use one tested display helper consistently in Recordings,
Processing, Analyzer, dialogs, search, and friendly-name sorting. Preserve the
exact backend name as secondary text, title, or detail according to the decision
record. Never derive recorded time from a filename; use start_time_ns. If the
Recorded column itself is removed, update PROJECT.md because it currently
requires that table fact.

Folder keys use normalized backend paths, never display labels. Parent selection
includes descendants. Folder search reveals matching ancestors and descendants.
Search must treat user/backend text as text, not a selector or regular
expression.

Selection keys are numeric IDs. Checkbox activation never navigates. Impossible
preparation is either disabled with an accessible backend-derived reason or
submitted and shown as a truthful unavailable result according to the approved
decision; it is never silently discarded.

Rescan occurs only after the explicit control is activated. Prevent overlapping
requests, show the real busy state, reload saved catalog on success, and retain
the previous table/folders/selection on failure.

### Contract E — Preparation flow

Use one bounded Prepare selected request with an ordered numeric recording list
and a non-empty selected output-kind subset. The contract documents and API
must define:

- a non-empty, unique, bounded output_kinds list using only the three fixed
  kinds, while the server retains front, top-down, then IMU scheduling order;
- per-recording versus global selection semantics;
- aggregate Ready only when all three current outputs are ready and Not planned
  for a completed subset with no active/failed work;
- partial Analyzer entry in which each ready consumer works independently and
  every missing consumer remains truthful;
- preflight and job insertion only for selected kinds, without letting an
  unavailable unselected kind reject the request;
- retries and Prepare selected interaction with unselected outputs; and
- selection eligibility based on the chosen kinds rather than an unavailable
  unselected target;
- how existing complete-bundle clients remain compatible.

Selective preparation requires no new table by itself. It must preserve
per-kind identity locks, stable order, idempotency, and source unavailability
semantics. Report queued, retry-queued, active reused, ready reused,
unavailable, not-found, and request-failed outcomes for the selected kinds.

Do not implement ambiguous checkbox behavior.

Freeze the submitted IDs/output choices, block duplicate submission, announce
real result counts, refresh saved catalog, preserve rejected details, and
navigate to Processing only when the response contains active work. Toast and
dialog content comes from the response, not local job simulation.

### Contract F — Processing read model and diagnostics

The Processing page reads PostgreSQL projections through bounded V1 APIs. It
never inspects source files, parses artifact payloads, or infers queue state
from timers.

Current work must show:

- exact recording and output identity;
- factual queued/start/pause ages and elapsed or active-runtime meaning defined
  by the decision record;
- worker online/offline and control-request state;
- an indeterminate track unless approved exact progress facts exist;
- the approved historical likely-duration/remaining state; and
- only controls the server reports as currently allowed.

Queue rows must use the same order and stable positions as worker claim. Search
does not renumber global positions. Failures are current actionable failed
attempts. History is bounded, cursor-paginated succeeded work unless the
decision record explicitly adds a canceled-attempt view.

When cancellation is approved, canceled attempts remain durable and available
to a bounded explicit history/audit query even if the three-tab engineer view
continues to show succeeded history only. Cancellation must not erase the
attempt merely to make it disappear from the queue.

The diagnostic dialog may show only facts actually retained safely:

- safe error code/message;
- attempted time and runtime;
- numeric recording ID and output kind;
- allowlisted topic/component filename/expected/actual fields recorded by the
  worker; and
- code-mapped recovery guidance that does not tell users to repair or modify a
  source.

Do not expose an absolute path, trace, command line, credential, arbitrary
processor payload, or invented “retry settings.” Omit unavailable detail rows
or label them unavailable. Copy diagnostic copies the same sanitized text.

Manual refresh, optional live refresh if retained by the approved visual
contract, hidden-document throttling, single-flight requests, bounded backoff,
last-updated truth, and stale-response rejection remain required.

### Contract G — Expanded job controls

#### State machine

Extend one jobs lifecycle rather than adding a second scheduler. Keep execution
lifecycle and live control intent separate:

- job state remains queued, running, succeeded, failed, or the new terminal
  canceled state;
- queued may become running or canceled;
- while job state is running, control state moves among none,
  pause_requested, paused, and cancel_requested;
- pause_requested remains running work until the worker acknowledges paused;
- paused retains the same attempt and owned temporary workspace, holds the
  single-worker slot, and starts no later job;
- resume returns control state to none on that same running attempt;
- cancel_requested remains running work until the worker proves processing
  stopped and cleanup completed, then job state becomes canceled;
- canceled is not a failure, creates no artifact, and permits a later explicit
  Prepare/retry action to create a new attempt; and
- succeeded, failed, and canceled are immutable terminal facts with no live
  control state.

Add an explicit worker execution phase and atomic publishing gate. Before that
gate, an accepted cancellation must prevent publication. Once the worker has
locked the row, rechecked control state, and entered publishing, cancellation
returns a conflict/already-finalizing outcome; publication or a publication
failure owns the result. Never report both successful and canceled for one
attempt.

Pause is cooperative suspension of the current process, not durable checkpoint
resume. If the worker exits or the VM restarts while an attempt is paused or a
control request is pending, startup recovery marks it interrupted/failed,
cleans only its proven workspace, preserves earlier ready output, and requires
explicit retry. Document this visible limitation.

#### Persistence

Use one additive migration, expected to follow 0006, to update the existing
jobs table and indexes without deleting or renumbering rows. The reviewed
migration should add only the minimum fields needed for:

- active control state, execution phase, and monotonically increasing control
  revision;
- pause/request/ack timestamps and accumulated paused duration;
- cancel request/finish facts;
- stable mutable queue order independent of historical queued_at; and
- approved progress or queued-estimate facts, if selected.

Replace the existing state check and timestamp/error constraints with exact
new transition-shape constraints. Backfill all existing rows without changing
their state, timestamps, identity, or artifact ownership. Backfill queued order
from queued_at then ID.

Update:

- the one-active-identity index to cover queued and running, independent of
  running control state;
- the one-execution-owner global index to continue covering the single running
  lifecycle row;
- claim/display order indexes to the new stable queue order; and
- failure, history, estimate, migration, and six-table deployment validators as
  required.

Do not add a control-events table or seventh domain table without a separate
data-contract decision.

#### Repository and concurrency

Every control command is a short transaction with validated positive IDs,
bounded bulk size, locked target rows, and explicit per-ID outcome.

- Cancel queued succeeds only while the row is still queued.
- Pause succeeds only for the current running attempt and returns requested,
  already-requested, already-paused, or conflict truthfully.
- Resume succeeds only for the matching paused/pause-requested attempt.
- Cancel current succeeds only before terminal publication.
- Reorder affects queued rows only; it never moves the current attempt.
- Bulk reorder preserves the selected rows' relative order.
- Insertion, claim, queued cancellation, and reorder share one documented
  queue advisory/row-lock order so they cannot deadlock or show a display order
  different from actual claim order.
- A bulk reorder is all-or-none when any selected row has already been claimed;
  bulk cancel/retry may return explicit per-row partial outcomes.
- Concurrent duplicate control requests are idempotent.
- Stale/racing requests return the actual current state, never pretend success.

Reordering deliberately supersedes the pre-overhaul FIFO rule. Keep queued_at
as historical age; do not falsify it to change order.

Bulk failure retry remains a collection of current-identity recomputations, not
blind job cloning. Each failed ID returns ready-reused, active-reused,
retry-queued, unavailable, not-found, conflict, or request-failed. One bad ID
does not roll back valid outcomes for other IDs.

#### Worker and processors

Introduce a small dependency-free control token/callback passed through the
worker into each processor and publication/validation phase. It may read only
bounded job-control state and must not import HTTP or browser code.

At measured safe checkpoints:

- acknowledge pause, stop advancing source decode/encode, retain only the
  proven job workspace, and wait with bounded database/control polling;
- acknowledge resume and continue the same attempt;
- acknowledge cancel, stop in-process work or terminate only the exact
  job-owned external process group, close immutable source handles, validate
  that no publication occurred, and remove only owned temporary output; and
- acquire the publishing gate and recheck cancel/control state immediately
  before artifact publication.

The UI shows Pause requested or Cancel requested until acknowledgement. Do not
change the button label instantly and imply the processor has stopped.

Measure control latency separately for front, top-down, IMU, media validation,
and external-command phases. Stop for design review if a phase cannot be
controlled safely without process isolation, a major dependency, source risk,
or unbounded latency.

#### API

Add only the approved versioned operations, for example:

- POST /api/v1/processing/jobs/{id}/pause;
- POST /api/v1/processing/jobs/{id}/resume;
- POST /api/v1/processing/jobs/{id}/cancel;
- POST /api/v1/processing/jobs/cancel with a bounded ordered ID list;
- POST /api/v1/processing/jobs/reorder with bounded ordered IDs and a
  server-defined earlier/later operation; and
- POST /api/v1/processing/jobs/retry with bounded failed IDs.

Exact route names and schemas must be reviewed before code. Responses include
actual job/control state, allowed controls, per-item result, and server time.
Overview/pages expose enough state for the UI without leaking private paths or
worker internals.

Do not add a generic arbitrary state-transition endpoint.

#### Frontend controls

Render current Pause/Resume/Cancel, queued row controls, bulk queue controls,
and bulk retry only when allowed by the current response state.

- Disable only the submitted controls while a request is active.
- Use a confirmation dialog for destructive cancellation.
- Preserve focus after completion/error and announce the actual outcome.
- Treat request, accepted-request, worker-acknowledged, and terminal states
  separately.
- Refresh authoritative overview/page data after every result.
- Do not mutate local arrays to simulate movement, cancellation, or retry.
- Keep four-second confirmation styling, animation, and toast behavior purely
  presentational; the backend remains authoritative.

### Contract H — elapsed time, progress, and estimates

Factual timestamps come from PostgreSQL and server time. Browser ticks are
cosmetic anchors corrected by each accepted response.

Because pause is approved, define and return both:

- wall elapsed since started; and
- active processing elapsed excluding acknowledged paused intervals.

The interface labels whichever value it displays; historical estimator samples
exclude acknowledged pause duration so user pauses do not make processor rates
look slower.

#### Default progress rule

Without separately approved instrumentation, preserve the reference track's
shape but render an indeterminate activity treatment with no aria-valuenow,
filled percentage, or numeric percent. Elapsed and likely duration do not imply
fraction complete.

#### Exact progress where measurable

For every phase that exposes numeric progress, each processor must define:

- an exact total available without a new expensive source pass;
- monotonically increasing completed units;
- named phases in which the ratio is meaningful;
- bounded update frequency to PostgreSQL;
- behavior during validation/publication where a decode ratio is no longer
  overall completion; and
- restart/cancel/pause semantics.

Show a percentage only while the response says it is determinate. Never pin an
unmeasured final phase at 99 percent or derive progress from elapsed/estimate.
Front and IMU may use a revalidated trusted topic-message count when it exactly
matches the processed unit. Top-down needs an exact truthful frame denominator;
a bounded worker-side CSV count/validation pass may be proposed, but no HTTP or
catalog query may read the full sidecar for progress. Decode progress,
validation, and publication remain separately named phases. Only completed
validated publication reaches 100 percent. Throttle persistence updates so
per-frame progress cannot overload PostgreSQL.

#### Running estimate

Retain the accepted kind/profile/processor-compatible median-rate model with at
least two valid succeeded samples. Display Approximate remaining, Estimating,
Not enough history, or Estimate exceeded. A paused/offline/cancel-requested job
does not show a wall-clock completion promise.

#### Queued ready estimate

Either compute a bounded transient estimate from each queued
target's persisted work_units/estimate_key and compatible history, or freeze a
compatible per-job estimate at enqueue time. Record which rule owns stability;
do not add persistence merely for display when the existing projection can
calculate the same bounded fact. Cumulative Ready in for a queued row is:

- current active estimated remaining; plus
- the estimated totals of every preceding queued row in actual claim order;
  plus
- that row's estimated total.

If any required predecessor estimate is unavailable, worker is offline, current
work is paused, or queue order changes during the response, return an explicit
unavailable/stale status rather than a number. Label every value approximate,
include sample confidence facts, and recompute after acknowledged reorder,
cancel, retry, pause, or resume. Never advertise it as an SLA.

### Contract I — Analyzer and graph

Populate the approved Analyzer layout from one numeric recording-detail
response:

- real name/date decision, duration, source size, storage, messages, topics,
  precise health, and safe diagnostics;
- real component filenames, sizes, and conditions;
- three output states, formats, sizes, coverage, provenance, warnings, and
  identity-bound URLs; and
- one clear workflow action when the approved preparation contract is
  incomplete.

Never show mock posters or a prior recording while new detail loads. A missing,
queued, processing, failed, canceled, stale, or unavailable output retains the
camera/telemetry card geometry with a truthful neutral state.

Preserve:

- one bag-relative global clock using integer nanoseconds at domain boundaries;
- identity-bound GET/HEAD/Range/If-Range/ETag delivery;
- front image-header cadence affinely mapped between measured ROS record
  endpoints;
- top-down CSV Unix timing;
- schema-version-2 six-axis raw IMU data;
- 100-millisecond camera correction, one seek in flight, buffering suppression,
  and readiness catch-up;
- measured coverage with hide/clear outside it;
- source-order duplicates, duplicate-last lookup, per-series null gaps, exact
  labels/units/extrema, and isolated consumer failure.

Graph-window behavior must:

- default to the full recording range;
- keep view_start and view_end as browser presentation state only;
- plain pointer drag and wheel scrub the global clock;
- Shift-drag selects and clamps a new window;
- zoom in/out preserves a documented anchor, reset restores full range, and
  plus/minus keys mirror the buttons;
- Arrow keys move one percent of the current window, Page Up/Down move ten
  percent, Home/End reach accepted bounds, and Space/K control playback;
- playback may page the view window when the global cursor crosses its edge,
  without seeking or changing the global clock merely because the window moved;
- graph labels may show bag_start plus elapsed as Unix time, while internal time
  remains bag-relative; and
- selection, resize, zoom, and data changes redraw the static trace, while
  ordinary clock ticks move one persistent pixel-snapped cursor overlay.

Measure the 76,000-row six-channel case. If a visible-window display transform
is needed, preserve per-pixel extrema and the selected series' gaps; do not
change the stored artifact or silently discard source samples.

### Contract J — accessibility and responsive behavior

Retain or correct without visual redesign:

- semantic landmarks, headings, labels, table headers, captions, native
  buttons, and dialogs;
- skip navigation and visible focus;
- roving processing tabs with Arrow, Home, and End behavior;
- aria-sort on the owning column header;
- selected, expanded, current, pressed, busy, requested, paused, and disabled
  states;
- polite announcements that do not repeat every timer/poll tick;
- focus restoration after dialogs and route changes;
- graph slider/value text plus pointer, touch, wheel, and keyboard equivalence;
- status text/icon shapes independent of color;
- 44-pixel coarse-pointer targets;
- the final reference cascade at desktop, folder-overlay, stacked-table, and
  narrow Analyzer widths;
- 200-percent zoom without document-level overflow; and
- reduced motion that removes decorative motion while preserving state.

Backend-controlled text must remain usable with long names and diagnostics at
every breakpoint. Truncation needs title or accessible full text and must not
hide the only explanation.

### Contract K — safety, security, and compatibility

- Original source files remain immutable and explicitly read-only.
- Control requests never touch a source path or create a source-side file.
- Cancel removes only a proven job-owned temporary workspace under the derived
  root and never an earlier valid artifact.
- Reorder changes database scheduling metadata only.
- Paused work retains only bounded owned resources and cannot block planned
  deployment shutdown indefinitely.
- Low-space admission/claim pause remains distinct from user pause.
- Startup still scans, prepares, cancels, resumes, or reorders nothing.
- Every request body, ID list, search string, cursor, and diagnostic field is
  bounded.
- CSP, no external runtime assets, no evaluated code, and no unsafe DOM sink
  remain enforced.
- No absolute source/derived path, command, trace, database URL, or secret
  reaches the browser.
- Existing V0 routes remain only as compatibility surfaces; new controls are
  V1-only and proxy/operator policy is updated explicitly.
- Building block 3 release/schema/preflight/backup/rollback assets are updated
  for the additive migration, but no live deployment action is performed.

### Expected implementation areas

The final file list follows inspection, but likely areas are:

- PROJECT.md, ARCHITECTURE.md, ROADMAP.md, AGENTS.md, and concise README status;
- BUILDING_BLOCK_PROMPTS.md completion evidence;
- src/rosbag_analyser/web/index.html;
- src/rosbag_analyser/web/styles.css;
- src/rosbag_analyser/web/app.js;
- src/rosbag_analyser/web/imu_graph.js;
- src/rosbag_analyser/api/v1_routes.py and v1_schemas.py;
- src/rosbag_analyser/processing_view.py and preparation.py;
- src/rosbag_analyser/persistence/processing_repository.py;
- one additive migration under persistence/migrations for job controls;
- src/rosbag_analyser/worker.py and the three processors only for approved
  cooperative control/progress checkpoints;
- deployment schema/release/backup validation affected by the migration,
  including release-contract identity, Nginx mutation routes/rate limits,
  smoke checks, paused-worker drain behavior, operator runbook, and engineer
  guide;
- API, unit, PostgreSQL, processor, worker, deployment, JavaScript, browser,
  visual, accessibility, and real-archive acceptance tests.

archive/ must not change.

### Required implementation phases

#### Phase 0 — freeze and decide

1. Complete the mandatory audit and reference screenshots.
2. Publish the mock-to-real/removal matrix.
3. Verify the approved seven-item decision record against the frozen reference.
4. Update owning contracts for approved scope changes.
5. Stop for explicit invocation of this corrective prompt.

#### Phase 1 — contract-first tests

6. Add reference-hash and prohibited-asset guards.
7. Add failing static/browser visual-state fixtures for the approved DOM.
8. Add migration/state-machine/concurrency/worker control tests before
   production code.
9. Add graph-window, routing, accessibility, and safe-rendering tests for newly
   approved behavior.

#### Phase 2 — backend operations

10. Apply and test the additive migration against faithful current and empty
    schemas.
11. Implement repository transitions, queue ordering, bulk retry, and read
    projections.
12. Implement worker/processor cooperative control and publication races.
13. Add thin schemas/routes and sanitized diagnostic context.
14. Update deployment schema, release, backup, and rollback validation.
15. Run backend, PostgreSQL, worker, processor, ROS, range, artifact, source-
    safety, and deployment-readiness regressions before frontend wiring.

#### Phase 3 — reference shell and Recordings/Processing

16. Port the approved semantic shell and final effective CSS.
17. Remove Experiments/Files and every prohibited asset/runtime path.
18. Wire routes, safe API adapter, stale-request lifecycle, catalog, folders,
    table, filters, selection, pagination, rescan, preparation dialog, and toast.
19. Wire current work, queue, failures, diagnostics, history, polling, estimates,
    and only the approved real controls.
20. Prove there is no local mock job mutation or fake timer.

#### Phase 4 — Analyzer and graph

21. Bind real detail/components/output facts and identity URLs.
22. Reconnect accepted media clock, coverage, correction, and isolated failure.
23. Reconnect schema-version-2 IMU selection and exact graph styling.
24. Add approved zoom/window/scrub/keyboard behavior without a second clock.
25. Prove no mock poster, media, metadata, or IMU fallback can render.

#### Phase 5 — synthetic acceptance

26. Run syntax, static, routine Python, API, PostgreSQL, ROS, JavaScript, and
    deployment regressions.
27. Run control latency/race/interruption tests with synthetic recordings and
    disposable derived/database roots.
28. Run the full paired visual, responsive, keyboard, reduced-motion, error,
    long-text, and performance matrix.
29. Record every intentional visual difference and resolve every unexplained
    one.

#### Phase 6 — separately approved real-data acceptance

30. Approve the exact short/long/damaged cases, operations, time window, roots,
    and inventory destination.
31. Capture the source before inventory as the first authorized content read.
32. Load saved state without implicit work; explicitly rescan once if approved.
33. Exercise the approved Recordings, preparation, Processing controls, reload/
    restart, and Analyzer flows without unnecessary regeneration.
34. Capture the after inventory in success or failure and prove exact equality.
35. Prove every created file stayed below the derived/database/log/test roots.
36. Record evidence and stop for user review. Do not resume live Building
    block 3 commissioning without a separate decision.

### Required automated verification

At minimum cover:

#### Reference and package guards

- exact approved reference hashes and unchanged archive/;
- no Experiments/Files DOM, data, CSS entry point, route, or navigation item;
- no macOS sidecar, mock preview, Figure 8 media/JSON, mock job/recording array,
  synthetic IMU fallback, external asset, or runtime package-manager path;
- shell/static routes, CSP, headers, MIME types, and package data.

#### Recordings and preparation

- saved catalog loads once with no implicit scan/work;
- physical folder construction, counts, ancestors, search, collapse/reveal,
  overlay, and empty state;
- approved name/date presentation;
- hostile names/folders/diagnostics render as text;
- health/analysis states and three-output detail;
- sorting, filtering, pagination, selected numeric IDs, visible select-all, and
  selection retention;
- explicit rescan success/failure with retained data;
- one bounded idempotent preparation request, duplicate-click suppression,
  complete or selective preflight according to the decision record, partial
  outcomes, dialog/toast, and navigation.

#### Persistence and controls

- faithful migration preserves every row, ID, identity, artifact, timestamp,
  and terminal state;
- empty/current schema migration and rollback classification;
- exact state/timestamp/check constraints and active/global/order indexes;
- pause request/ack/resume, cancel queued/current, bulk cancel/retry, reorder
  up/down, selected relative order, and terminal immutability;
- claim-versus-cancel, claim-versus-reorder, publish-versus-cancel,
  pause-versus-finish, duplicate request, stale request, and database error
  races;
- worker death/restart while running, pause-requested, paused, and cancel-
  requested;
- owned temporary cleanup and prior ready-artifact preservation;
- queue display order exactly matches claim order after every mutation;
- low-space worker pause remains distinct and resumes safely;
- no source write/sidecar and no job created for unavailable prerequisites.

#### Time, progress, and estimate

- server-time anchoring and local elapsed resynchronization;
- wall versus active elapsed around multiple pauses;
- estimator excludes pauses, failures, canceled work, stale identity, invalid
  sizes, and incompatible profiles;
- insufficient, available, exceeded, paused, offline, and stale states;
- determinate progress totals/monotonicity/phases/update bounds;
- cumulative queue estimate order, unknown predecessor propagation,
  and invalidation after every queue/control change;
- no fabricated percent, duration, or wall-clock readiness.

#### Processing browser behavior

- queue/current/failed/history real rendering and counts;
- controls appear only when capability/state allows;
- request/requested/acknowledged/terminal UI states;
- confirmation, idempotency, partial bulk outcomes, conflict recovery, toasts,
  dialog focus, and live announcements;
- failure diagnostic allowlist and absent-detail rendering;
- manual/auto/hidden polling, single flight, backoff, stale response discard,
  and route cleanup;
- history cursor deduplication and numeric recording navigation.

#### Analyzer and graph

- direct numeric route, refresh, Back/Forward, and stale detail cleanup;
- real metadata/components and no absolute paths;
- identity-bound media/data URL validation and range regressions;
- front/top timing, play/pause/end/seek, 100-millisecond correction, buffering,
  one seek in flight, coverage, and consumer isolation;
- six fixed IMU signals, labels, units, extrema, null gaps, duplicate-last
  lookup, and one payload parse;
- pointer drag, wheel, Shift-drag zoom, buttons, reset, plus/minus, arrows,
  Page Up/Down, Home/End, Space/K, clamping, playback reanchor, and automatic
  window paging;
- one persistent pixel-snapped cursor, bounded animation frames, no trace redraw
  on ordinary ticks, and narrow/high-DPI rendering;
- 76,000-row performance with no unjustified artifact reduction.

#### Accessibility and visuals

- skip link, landmarks, headings, labels, captions, aria-sort, tab roving,
  selected/expanded/current/busy/requested states, dialogs, focus restoration,
  graph value text, touch targets, and status independent of color;
- 200-percent zoom, narrow/card layouts, coarse pointer, reduced motion, long
  names, long diagnostics, and no document overflow;
- paired screenshot/geometry comparison for every approved matrix state;
- zero unexplained visual differences.

### Visual acceptance matrix

Capture paired reference/served evidence at minimum at:

- 1600×900;
- 1366×768;
- 1024×768;
- 901×800 and 900×800;
- 820×800 and 819×800 where processing bulk labels change;
- 721×800 and 720×800 where the current-job card changes;
- 701×800 and 700×800 where recording/processing tables become cards;
- 600×800;
- exact 320×800 CSS viewport;
- a 200-percent-zoom-equivalent viewport;
- coarse-pointer emulation; and
- reduced-motion emulation.

At each relevant size cover:

- Recordings default, folder open/collapsed/overlay, selected, filtered, empty,
  scanning, long/hostile names, preparation dialog, and toast;
- Processing idle, running indeterminate/determinate as approved, pause/
  cancellation requests, paused, queue selected/reordered, cancel dialog,
  failure selected, diagnostic, history, offline worker, stale/error response,
  and long text; and
- Analyzer ready, incomplete, unavailable, media failure, outside coverage,
  details expanded/compact, sensor menu, play/scrub, zoom selection/window,
  auto-page, reset, and graph error.

### Real-data and source-safety acceptance

Real-data work is not authorized by writing or invoking the repository-only
parts of this prompt. Approve a separate annex naming exact cases and operations.

When approved:

- validate source and derived roots are separate and correctly mounted;
- write the lightweight before inventory outside the source;
- start one API and exactly one worker;
- load saved catalog without scanning;
- run no more than the approved explicit bounded rescan;
- use one short readable, one representative long/reused, and one known damaged
  case;
- exercise only approved pause/resume/cancel/reorder/retry operations, preferably
  with synthetic queued work when a real expensive run is unnecessary;
- confirm canceled work publishes nothing, prior ready output survives, and
  retry recomputes current identity;
- verify real cameras, all six IMU signals, graph interaction, coverage, reload,
  restart, and reuse;
- capture the after inventory even after failure and require exact equality; and
- prove all generated/temporary output stayed below the derived root.

### Prohibited scope

Do not:

- rewrite the accepted Building block 2 history or pretend the August 23
  reference was accepted on August 4;
- edit archive/ to make implementation comparison easier;
- serve Experiments/Files or any mock media/data;
- add a framework, npm runtime, chart/icon library, CDN, remote font, analytics,
  or major runtime dependency;
- fabricate progress, estimates, queue movement, pause, cancel, retry, history,
  diagnostics, coverage, or readiness;
- use SIGSTOP as a pause mechanism, or use SIGKILL/broad process termination
  without exact job ownership, a bounded graceful stop, tested cleanup, and
  reviewed semantics;
- cancel or replace a valid artifact before replacement publication;
- change source formats, add processors/artifact kinds/workers, or weaken
  current identity and timing rules;
- expose source/derived paths or let Nginx serve derived files directly;
- scan or prepare on startup;
- perform live VM/NAS, firewall, mount, database, deployment, or real-source
  work without the existing gates;
- commit, push, change remotes, open a pull request, or publish a release.

### Stop conditions

Stop and request direction if:

- reference hashes differ or verbal/table/processing/graph decisions remain
  unresolved;
- exact visual parity requires serving mock operational content or weakening
  accessibility/security;
- a visible enabled control has no approved truthful backend/browser contract;
- pause/cancel cannot reach a bounded safe checkpoint without a new process
  model, major dependency, source risk, or unowned process termination;
- cancel can race to delete/replace a valid artifact or clean an unproven path;
- queue reorder cannot share one exact order with worker claim;
- partial preparation would make Ready/Analyzer semantics ambiguous;
- numeric progress lacks an exact total or queued estimate requires a promise
  unsupported by compatible history;
- graph zoom would create a second clock or change accepted media coverage;
- migration requires destructive row changes, a seventh table, or an unproven
  deployment rollback;
- work would overlap live Building block 3 mutation or authoritative source
  access; or
- any source inventory changes.

### Completion handoff

Report:

- the approved decision record and dated corrective boundary;
- frozen reference hashes and confirmation archive/ stayed unchanged;
- every file changed and every intentional visual difference;
- removed Experiments/Files, mock assets, mock datasets, timers, and handlers;
- mock-to-real/static/removed mapping;
- migration, state machine, indexes, API routes, worker checkpoints, control
  latency, concurrency results, and rollback classification when applicable;
- exact elapsed/progress/estimate semantics;
- served routes and backend routes consumed;
- all automated, PostgreSQL, ROS, browser, visual, accessibility, performance,
  real-data, and source-inventory evidence actually completed;
- visible behavior at every viewport/state;
- limitations such as non-durable pause across worker restart;
- preservation of processor, artifact, timing, coverage, move, low-space, and
  deployment contracts;
- Git status and uncommitted state; and
- the exact user decision required before resuming Building block 3 or admitting
  trial users.

> **Implementation handoff — 2026-08-23:** Prompt 2A was implemented against
> the accepted checkpoint `810ae16` and left uncommitted for user review. This
> is synthetic repository evidence, not user acceptance, authoritative-source
> evidence, or permission to resume live Building block 3 work.

#### Implemented corrective boundary

- The frozen reference hashes remain exactly
  `5373286f…` (`index.html`), `01eb9329…` (`styles.css`), `a5d85e83…`
  (`script.js`), and `b2fb92cb…` (`tech-trace-icon.svg`); `archive/` has no
  diff.
- The served shell retains only Recordings, Processing, and Analyzer. Saved
  catalog/detail, job, media, and IMU APIs replace reference mock rows, images,
  jobs, timers, and graph payloads. Experiments/Files and their handlers are
  removed. The separate Recordings Recorded column is intentionally removed;
  the full source identity and recorded time remain accessible in row context
  and Analyzer detail.
- Prepare selected freezes ordered numeric recording IDs plus any validated
  non-empty subset of the existing three output kinds. Results preserve only
  rejected selection and navigate to real Processing state when active work
  exists.
- Migration `0007_job_controls.sql` adds durable control state/revision,
  execution phase, pause/cancel timestamps, accumulated pause time, stable
  queue order, its owned sequence, and queue/canceled indexes to `jobs`. It
  keeps exactly six domain tables, preserves `queued_at`, and is classified as
  forward-only/database-restore rollback unless old code is separately proven
  schema-0007 compatible.
- The single worker uses one dependency-free control token through front,
  top-down, IMU, validation, cleanup, and the transactional publication gate.
  Paused work resumes in the same process/attempt, but a worker restart marks
  it `worker_interrupted`; pause is not durable execution across restart.
- Display, insertion, claim, queued cancel, and earlier/later reorder share one
  serialized `queue_order`. The V1 API now exposes pause/resume/cancel, bounded
  bulk cancel/reorder/retry, canceled history, authoritative allowed controls,
  wall/active/paused time, and response server time. Bulk retry also carries a
  response server time.
- Running progress remains indeterminate because no existing processor has a
  fully proven phase-wide exact denominator. Estimates freeze at enqueue (with
  a compatibility fallback at claim), exclude paused/canceled/invalid samples,
  and produce cumulative approximate queued Ready in only while the worker,
  current state, predecessor order, and every estimate input remain valid.
- Analyzer graph-window zoom/reset, wheel/pointer scrub, Shift-drag selection,
  plus/minus/arrows/Page/Home/End/Space/K behavior, and playback paging remain
  presentation over the one unchanged full-recording clock.
- Deployment contracts now identify migrations 0001–0007, rate-limit the new
  mutations, and make planned drain fail closed on paused/pause-requested work.

#### Files changed in the handoff

`AGENTS.md`, `ARCHITECTURE.md`, `PROJECT.md`, `README.md`, `ROADMAP.md`,
`BUILDING_BLOCK_PROMPTS.md`, `deploy/README.md`,
`deploy/nginx/rosbag-analyser.conf.template`, `deploy/release-contract.json`,
`deploy/scripts/drain-worker`, `deploy/scripts/smoke_check.py`,
`docs/ENGINEER_TRIAL_GUIDE.md`, `docs/NAS_TRIAL_RUNBOOK.md`,
`src/rosbag_analyser/api/v1_routes.py`,
`src/rosbag_analyser/api/v1_schemas.py`,
`src/rosbag_analyser/artifact_store.py`, `src/rosbag_analyser/job_control.py`,
`src/rosbag_analyser/persistence/database.py`,
`src/rosbag_analyser/persistence/migrations/0007_job_controls.sql`,
`src/rosbag_analyser/persistence/processing_repository.py`,
`src/rosbag_analyser/preparation.py`, `src/rosbag_analyser/processing_view.py`,
the three files under `src/rosbag_analyser/processors/`,
`src/rosbag_analyser/web/app.js`, `src/rosbag_analyser/web/index.html`,
`src/rosbag_analyser/web/styles.css`, `src/rosbag_analyser/worker.py`, and the
focused API, JavaScript, PostgreSQL, deployment, preparation, worker,
processor, artifact-control, and Prompt 2A guard tests under `tests/`.

#### Synthetic verification completed

- Routine unit/API/deployment: 340 passed, 2 environment-dependent skipped.
- Disposable PostgreSQL: 38 passed, including faithful/empty migration,
  pause/ack/resume/cancel, every nonterminal restart state, canceled history,
  publication race, claim/cancel, and concurrent insertion/claim/reorder.
  Maximum 5,000-recording response remained
  2,652,445 bytes; catalog was 434 ms and Processing 29 ms in the final run.
- Dependency-free browser/runtime: 22 passed, plus JavaScript syntax. The
  76,000-row/six-channel measurement was 10,141,317 payload bytes, 109.905 ms
  parse, 28.638 ms visible transform, and 5.748 ms for 10,000 lookups.
- ROS Humble focused serialization: 2 passed with third-party pytest plugin
  autoload disabled to avoid an unrelated missing `lark` plugin dependency.
- Synthetic cancellation reached the front and IMU checkpoints in 20 ms,
  top-down in 10 ms, validation-before-command in 10 ms, and the
  validation-after-external-probe checkpoint in 550 ms. Normal token polling is
  capped at 250 ms between per-unit calls; each owned external validation
  command has a 30-second timeout and immediately rechecks afterward.
- Python byte-compilation, shell syntax for shell-owned deployment scripts,
  HTML parsing, CSS brace/comment/string balance, Git whitespace checks,
  frozen-reference hash guards, prohibited-asset guards, and zero archive diff
  passed. No dependency was added.

#### Acceptance still deliberately incomplete

No authoritative source content, real archive, live database, VM, NAS,
firewall, mount, service, or deployment target was accessed or changed. The
real-data annex, source before/after inventory, live restart/interruption proof,
and Gate 0 remain pending. Automated DOM/interaction checks passed, but a usable
local browser/screenshot path was unavailable, so paired reference screenshots,
the full viewport/state visual matrix, 200-percent zoom, coarse-pointer,
reduced-motion, and manual keyboard/focus review remain explicit user-visible
acceptance work. No Prompt 2A commit or push was made. User review is required
before committing this handoff or deciding whether Building block 3 may resume.

> **Recordings visual review correction — 2026-08-24:** During user review, the
> user explicitly superseded decision-record item 2 only for the Recordings
> table and restored the frozen reference's separate Recorded column. The value
> remains derived solely from `start_time_ns`. This bounded follow-up also
> authorizes attached non-native Recordings filter menus, viewport-aware status
> tooltips that cannot widen the table, the reference folder/search icon and
> spacing treatment, a single-line Prepare selected transition, and removal of
> the white rectangular focus treatment from Recordings controls while
> retaining a restrained keyboard-visible state. Processing, Analyzer, API,
> persistence, worker, processor, source, artifact, timing, deployment, and
> `archive/` behavior remain outside this follow-up.


## Prompt 3 — TrueNAS VM deployment and trial commissioning

> **Invocation note — 2026-08-16:** This target-informed prompt was explicitly
> invoked. Repository Phase 1 was implemented without VM/NAS or authoritative
> source access. Gate 0, clean-release creation, live installation, real-data
> acceptance, commit, and push remain separately gated as stated below.

### Authorization and outcome

When the user explicitly invokes this prompt, implement V1 Building block 3
only: repository deployment readiness followed by controlled commissioning of
the application in the exact administrator-provisioned VM.

The invocation authorizes:

- deployment-related application code, tests, templates, scripts, and owned
  documentation inside the contracts below;
- disposable local lifecycle, proxy, database, filesystem, and failure testing;
- read-only inventory of the approved VM and its mounted filesystems;
- installation and configuration inside that VM only after the mandatory
  handoff is complete and the exact live change set has been reviewed with the
  user; and
- the bounded real-source acceptance described below only after its site annex
  identifies the exact root, recordings, window, and inventory destination and
  the user approves that annex.

It does not authorize TrueNAS appliance changes. The administrator creates the
VM and owns datasets, zvols, shares, ACLs, snapshots, host networking, firewall,
appliance updates, base OS installation, certificates, and recovery access.
Never change an existing share or permission merely to make this project fit.

It also does not authorize a commit, push, release publication, public
exposure, destructive live drill, source mutation, or work on another building
block.

The completed outcome must provide:

- one reproducible, immutable application release with a recorded identity;
- one local PostgreSQL database, one loopback API, and exactly one serial worker;
- a fail-closed read-only mount of one fixed approved NAS source root;
- a distinct writable derived filesystem with bounded low-space behavior;
- authenticated same-origin HTTPS through the approved network boundary;
- controlled schema migration, backup, restore, upgrade, and rollback;
- TrueNAS VM-autostart configuration evidence plus orderly guest application
  startup after a mandatory VM reboot, without implicit rescan or preparation;
- operator and engineer runbooks; and
- recorded disposable and live acceptance evidence sufficient for the user to
  decide whether to admit the limited trial group.

Repository readiness may finish before the VM exists. It is not live deployment
acceptance.

### Mandatory initial audit

Before planning implementation edits:

1. Read README.md, PROJECT.md, ARCHITECTURE.md, ROADMAP.md, AGENTS.md, and this
   prompt completely.
2. Read the relevant V0 source-safety, processor, timing, artifact, real-data,
   and limitation evidence under docs/v0/.
3. Inspect Git status and all relevant diffs. Treat the accepted but
   uncommitted Building blocks 1 and 2 and corrective slices as user work.
4. Inspect packaging, requirements.lock, configuration, migrations, PostgreSQL
   access, API startup, worker startup/shutdown, artifact publication, range
   delivery, local ./dev workflow, tests, and current operational scripts.
5. Inventory the exact runtime imports and external executables actually needed
   by API, worker, migrations, media, IMU, PostgreSQL, proxy, NFS, backup, and
   health checks. Record versions, source repositories, maintenance role, and
   licence implications.
6. From read-only evidence, compare the administrator handoff with the VM,
   disks, mounts, addresses, routes, firewall boundary, NFS export, time sync,
   patch state, console state, and recovery route. Do not probe the source by
   writing.
7. Identify every unresolved decision, security gap, destructive step,
   interruption, credential requirement, and source-data action.
8. Before editing, report the exact block boundary, files expected to change,
   local verification plan, live phases currently possible, deployment and
   real-data access, assumptions, and stop conditions.

Do not begin live mutation during the audit. First present a sanitized
pre-change inventory and exact live execution/rollback sequence.

### Fixed target decisions and known risk facts

Preserve these decisions unless the user approves an architecture change:

- Ubuntu Server 22.04 LTS amd64 and ROS 2 Humble remain the V1 runtime. Humble
  has Tier 1 Ubuntu 22.04 binaries; running Humble on a newer Ubuntu release is
  not an approved shortcut.
- Ubuntu 22.04 standard security maintenance and ROS 2 Humble support end in May
  2027. Assign a named platform owner and complete a supported-platform decision
  by 2027-01-31. Ubuntu extended maintenance does not extend ROS Humble.
- A future Ubuntu/ROS migration uses a separate reversible target and its own
  compatibility block. It is excluded here.
- The target observed during discovery used a TrueNAS 26 beta. TrueNAS states
  that early releases are for testing/feedback and not critical tasks. Before
  trial admission, the infrastructure owner must either provide an approved
  general-use host or explicitly accept a non-critical reversible trial with an
  appliance configuration backup, recovery path, maintenance owner, and
  escalation route. Do not update the appliance in this block.
- The observed host bridge carries globally routable IPv4 and IPv6. Do not infer
  privacy from the word internal. Prove VPN/firewall/allowlist behavior for both
  IP families.
- Existing NFS exports may overlap at parent and child locations, may have other
  consumers, and the candidate source area has broad filesystem permissions.
  Audit exact exports and consumers before the administrator changes anything.
- TrueNAS treats child datasets as separate filesystems; a parent NFS export
  cannot be assumed to expose a child dataset. Establish whether the fixed
  recording folder is a directory or its own dataset.
- Exact hostnames, addresses, MACs, export paths, filesystem UUIDs, credentials,
  certificate paths, dataset/zvol names, and backup destinations stay in a
  root-owned site inventory outside Git.

The dated platform assumptions above come from the official
[ROS 2 Humble release](https://docs.ros.org/en/humble/Releases/Release-Humble-Hawksbill.html),
[ROS 2 distribution lifecycle](https://docs.ros.org/en/humble/Releases.html),
[Ubuntu release cycle](https://ubuntu.com/about/release-cycle),
[TrueNAS 26 version notes](https://www.truenas.com/docs/scale/26/gettingstarted/versionnotes/),
[TrueNAS software-status guidance](https://www.truenas.com/docs/softwarestatus/),
and [TrueNAS NFS guidance](https://www.truenas.com/docs/scale/26/shares/nfs/addingnfsshares/).
Revalidate these sources at implementation time because platform status can
change without a repository edit.

### Gate 0 — administrator handoff

Do not install on the live VM until the administrator and project owner provide
or approve the following handoff.

| Area | Required handoff evidence |
|---|---|
| VM identity | TrueNAS VM ID/name, guest hostname, responsible owner, clean-base snapshot/recovery point |
| Base OS | Fully patched Ubuntu Server 22.04 LTS amd64, UTC and time sync, minimal/no GUI, SSH-key administration, remote root login disabled |
| Compute | Recorded vCPU topology, memory, CPU mode, and any host limits |
| Boot/console | Start on Boot configured, install ISO detached, VNC/serial console disabled or loopback-only through an approved admin tunnel, IPMI/recovery route confirmed |
| Network | Stable unique MAC and address, bridge/interface, routes, DNS/NTP, IPv4 and IPv6 policy, SSH admin path, engineer HTTPS path, upstream and guest-firewall owners/allowlists |
| OS disk | VirtIO disk identity, size, backing zvol, guest filesystem/UUID, snapshot and backup ownership |
| Derived disk | Separate VirtIO disk/zvol, capacity basis, filesystem/UUID, mount target, quota/reservation, low-space threshold, growth owner |
| Source NFS | Exact fixed export/root, dataset-versus-directory status, NFS version/security, server Read-Only evidence, exact VM host/network allow entry, root/all mapping, service bind/firewall, known parent/child exports and consumers |
| Access | Approved hostname, TLS issuer and renewal owner, identity proxy or individual trial credential owner, named trial group, grant/revoke procedure |
| Database/backup | Database owner, role/credential delivery, off-VM protected destination, encryption, RPO, retention, restore owner |
| Host risk | TrueNAS release/risk decision, configuration backup, rollback/recovery procedure, maintenance window and contact |
| Real-data annex | Exact mounted root, approved recording identifiers/cases, allowed operations, expensive-processing window, before/after inventory location |

The proposed base VM baseline is:

- current official Ubuntu Server 22.04.x amd64 media, fully patched after install;
- UEFI; Secure Boot and virtual TPM disabled unless site policy explicitly
  requires and tests them;
- UTC, no desktop, no CPU pinning or speculative NUMA tuning;
- one virtual socket, six cores, one thread per core, host CPU passthrough;
- 16 GiB fixed RAM;
- a 100 GiB VirtIO OS disk;
- a separate capacity-sized VirtIO derived-data disk;
- one VirtIO NIC on the approved existing bridge with a stable unique MAC and
  address; and
- TrueNAS VM Start on Boot enabled for the commissioned VM.

The administrator may approve a different value, but every variance must be
recorded and tested. The 100 GiB OS disk is not the artifact store.

Reconcile the NAS VM shutdown timeout with worker behavior. Planned maintenance
drains long work before shutdown. For host shutdown, systemd must terminate the
worker within a measured margin before the NAS forces the VM off. If the
synchronous job does not finish after SIGTERM, the tested forced-stop path may
end it; startup recovery must then mark only that abandoned job interrupted and
clean only its proven workspace. Do not set an untested timeout that merely
hopes a 30-minute processor finishes.

The handoff can reference a secure operator record. Do not copy its sensitive
values into repository examples, logs, evidence bundles, or chat responses.

### Contract A — release identity and supported runtime

Do not deploy an unidentified dirty checkout. Create a deterministic release
artifact from a user-reviewed source state and record:

- source revision or reviewed source-archive identity;
- whether the worktree was clean;
- checksum of the release artifact and dependency lock;
- application, schema, processor, artifact-format, Python, ROS, FFmpeg,
  PostgreSQL, Nginx, and OS versions; and
- build time and operator.

If producing the release identity requires a Git commit, stop for the separate
commit approval required by AGENTS.md. Prompt 3 does not grant it.

Use Python 3.10, ROS 2 Humble packages required by actual imports, FFmpeg and
ffprobe with the accepted H.264/yuv420p capabilities, a supported local
PostgreSQL release, Nginx unless the approved identity proxy replaces it, the
NFS client, and narrowly required backup/health tools. Install OS packages only
from approved Ubuntu, ROS, PostgreSQL, or internal APT repositories. Build
Python artifacts beforehand from reviewed hash-locked inputs or an approved
checksummed wheelhouse, then activate without network dependency resolution.
Do not curl-pipe installers.

Build a wheel or equivalently immutable package plus a locked virtual
environment in a new release directory. Run imports, pip check, console-script
identity, ROS environment, FFmpeg capabilities, application tests, and
preflight before activation. Keep ./dev unchanged for local development.

The existing requirements.lock is an exact version list but includes
development packages and has no hashes. Produce a deployment-only,
hash-verified runtime lock or a checksummed approved wheelhouse for Ubuntu
22.04; do not silently present the current file as stronger evidence than it
provides. Install only the ROS Python/message packages proven necessary by the
audit rather than an unmeasured desktop stack. Prefer PostgreSQL 14 for the
first VM because it is the conservative Ubuntu 22.04 default already covered by
the accepted tests; record and retest any approved alternative.

Record the May 2027 support boundary in the runbook, health/support output, and
operator calendar without claiming that Ubuntu Pro extends ROS support.

### Contract B — guest filesystem and service identities

Use an equivalent versioned layout:

~~~text
/opt/rosbag-analyser/releases/<release-id>/
/opt/rosbag-analyser/current -> releases/<release-id>
/etc/rosbag-analyser/application.env
/etc/rosbag-analyser/database.env
/srv/rosbag-analyser/source
/var/lib/rosbag-analyser/derived
/var/lib/postgresql/
/var/backups/rosbag-analyser/   # staging only when approved
~~~

Paths are deployment configuration, not core constants. Site-specific mappings
stay outside Git.

Use a dedicated non-login, non-sudo application user and group. The running
user cannot modify releases, configuration, database files, mount definitions,
backups, or unrelated home directories. It can read only the approved source
mount and write only the derived paths and narrowly required runtime state.

Use separate least-privilege PostgreSQL credential paths for runtime,
migration, and backup where supported. Root owns configuration and environment
files; secret-bearing files are mode 0600 or the tightest tested group-readable
mode. Services use UMask=0027.

Release directories are root-owned and immutable to the service. The derived
mountpoint is root-owned; only its proven application subdirectory is writable.
No active logs, PID files, environments, secrets, database data, backups,
mounts, or service state live in the checkout.

### Contract C — NAS source is independently read-only

The source archive remains authoritative and immutable. The application must
not create a journal, WAL, lock, cache, index, repaired metadata, or sidecar
beside it.

Before mounting, the administrator must audit the exact fixed folder, whether
it crosses a child dataset, all parent/child NFS exports, current consumers,
server bind addresses, firewall rules, allowed hosts/networks, Read-Only flag,
NFS version/security, and Maproot/Mapall behavior. Prefer a dedicated
exact-path export. Do not alter or reuse a broader existing export without its
owner's review.

Require all of these layers:

1. TrueNAS exports the exact source server-side Read-Only.
2. Allowed Hosts/Networks identifies only the approved VM or protected storage
   network; an empty list that means everyone is not acceptable.
3. Remote root is mapped/squashed to an unprivileged NAS identity. Mapall is used
   only if its ownership and compatibility effects are understood.
4. NFS is reachable only on the approved storage path. If AUTH_SYS is used, the
   infrastructure owner records its host-trust limitation; use a protected
   storage network or Kerberos when site confidentiality/integrity policy
   requires it.
5. The guest mount is also ro,nosuid,nodev,noexec,_netdev where compatible.
6. The application user has read/traverse access and no write authority.
7. Systemd and preflight verify the exact server/export, filesystem type,
   mountpoint, and read-only mount state before API or worker starts.

An absent mount must never reveal an ordinary writable local directory at the
same path. Use an exact mount unit plus fail-closed mount identity checks, not
only path existence or RequiresMountsFor.

Prove the server layer from the administrator's saved export configuration and
the client layer with read-only tools such as findmnt and mountinfo. Never use
touch, mkdir, SQLite open, or any other write attempt as a test.

Broad NAS ACL/POSIX permissions or other SMB/NFS clients mean this project can
prove only that its VM did not write. Do not claim that no other client can
change the data.

Application-level path containment, no-symlink traversal, bounded scanning,
read-only/immutable SQLite access, and source-identity revalidation remain
mandatory.

### Contract D — derived storage and low-space behavior

Use a separate mounted filesystem for derived output, preferably a dedicated
guest filesystem on the approved derived zvol. It must not overlap the source,
release, database, log, or backup roots. A separate zvol on the same NAS/pool is
logical isolation, not an independent failure domain; record that residual
risk.

Size it from measured short/long artifact growth, expected trial recording
count, concurrent temporary workspace, regeneration cost, and explicit
headroom. Record capacity, quota/reservation, warning and rejection thresholds,
monitor owner, and expansion procedure. Do not guess a production-sized number
or silently use the OS disk.

Temporary and final artifact paths must share the filesystem and support the
accepted atomic publication behavior. Validate mount identity, owner marker,
containment, symlinks, permissions, free space, and a disposable atomic-rename
check before service activation.

Check the rejection threshold both before queue insertion and immediately before
worker claim. A low-space worker leaves queued work queued and does not claim or
fail it; it resumes only after capacity is restored and revalidated. If space
is exhausted during an already-running job, preserve the existing validated
failure/owned-workspace cleanup behavior. When space is low:

- reject or mark new preparation unavailable without creating stale work;
- do not delete ready artifacts or source data;
- do not publish partial output;
- keep valid catalog and ready artifacts available; and
- expose a sanitized preparation-capability warning to operators.

No automatic cleanup, retention, quota eviction, or artifact deletion is added
in V1. Full-disk and mount-loss drills use disposable filesystems only.

### Contract E — PostgreSQL state and schema migration

Run one local PostgreSQL instance through a Unix socket or loopback only. It is
never engineer-facing. Use explicit database names, roles, ownership, timeouts,
connection bounds, and root-owned secret delivery.

Separate these questions:

- **Schema migration:** always apply the repository's numbered forward
  migrations exactly once under a controlled migration lock.
- **Application-state transfer:** default a fresh NAS trial to a new empty
  database followed by an explicit source rescan when development paths and
  source identities do not match.
- **History/artifact transfer:** perform only under a separately reviewed annex
  that transfers PostgreSQL state and compatible derived files coherently,
  revalidates source/cache identities, and defines invalidation for every absent
  or incompatible artifact.

Never import the development database alone and claim its ready artifacts still
exist. Never rewrite source paths, fabricate source identity, or copy generated
files into source storage to make a migration pass.

Services refuse an incompatible or partially migrated schema. API and worker
startup never run migrations. Migrations are one-shot operator/release actions.
Expose the existing exact structural schema validator through a read-only
preflight path for both services. Do not casually add a schema-history table:
an accepted contract currently requires exactly the six V1 domain tables, so a
seventh table needs a separately reviewed data-contract decision.

### Contract F — configuration, preflight, and health

Provide committed placeholder examples and strict parsing for all deployment
values. Reject missing/empty values, unexpected URLs, relative or overlapping
roots, symlinks, unsafe topic/profile/bound values, wrong file modes, unknown
release/schema, missing executables, incorrect mounts, and unsafe listener
addresses. Never print secret values.

Preflight is read-only with respect to source data and does not rescan, decode,
create jobs/artifacts, or make a source database connection that could write
auxiliary files. It verifies:

- release and dependency identity;
- database reachability and schema compatibility;
- exact source mount identity and client read-only state;
- source containment and service-user readability;
- distinct derived mount, ownership, write authority, atomic semantics, and
  free-space thresholds;
- ROS and FFmpeg/ffprobe capabilities;
- approved loopback listener configuration; and
- certificate/access configuration without exposing key material.

Add or refine sanitized health endpoints:

- /health/live reports only process liveness and release identity.
- /health/ready reports core serving readiness and separate capabilities for
  catalog, valid-artifact delivery, source access, new preparation, database,
  and worker observation.

Database/schema loss or loss of the trusted derived mount makes core readiness
fail closed. Source loss or low derived space disables scan/preparation but
does not unnecessarily hide a saved catalog or already validated ready
artifacts. Health JSON never includes paths, addresses, database URLs,
credentials, stack traces, or source facts.

Liveness must not restart-loop on a dependency outage. Starting services or
calling either health endpoint never scans or creates a job.

### Contract G — systemd, boot, and interruption safety

Provide version-controlled, statically verified templates for:

- an explicit migration/preflight one-shot workflow;
- rosbag-analyser-api.service;
- rosbag-analyser-worker.service; and
- rosbag-analyser.target.

API and worker use the same validated release and configuration, start after
network-online, PostgreSQL, and exact required mount units, and fail before
launch when mount identity/preflight is wrong. The target starts no rescan or
preparation.

Use Restart=on-failure with bounded delays/start limits, journald, absolute
executables, exact working directories, and tested systemd hardening such as
NoNewPrivileges, ProtectSystem, ProtectHome, PrivateTmp, RestrictSUIDSGID,
read-only source paths, and explicit derived write paths. Apply only hardening
that passes ROS, FFmpeg, PostgreSQL-client, and artifact tests.

Exactly one worker process is configured; the PostgreSQL advisory lock remains
defence in depth.

Define two shutdown paths:

- planned release/maintenance stops accepting new preparation, waits for the
  worker to become idle within the approved window, then stops worker before
  API; and
- host/emergency shutdown sends termination, prevents partial publication,
  exits within the tested systemd/NAS timeout margin, records or recovers only
  the running job as interrupted, removes only its proven temporary workspace,
  preserves ready artifacts, and requires explicit retry.

Do not claim a long job can finish inside the NAS shutdown timeout. Reconcile
and record the guest TimeoutStopSec and host VM shutdown timeout from measured
interruption behavior.

Enable the application target at boot only after all pre-boot live checks pass.
Then reboot the guest VM and prove source/derived mounts, PostgreSQL, migration
gate, API, worker, and proxy order correctly. Startup must load saved state
without rescan or new jobs.

TrueNAS VM Start on Boot is a separate administrator-owned setting established
in Gate 0. Verify its saved configuration, but do not reboot the TrueNAS host in
this block. The operator observes end-to-end VM autostart at the next separately
approved NAS maintenance reboot and records the result or incident.

### Contract H — engineer-facing access boundary

Use the organization's identity-aware proxy when available. Otherwise, for this
limited trial only, use individual per-engineer proxy credentials over TLS
inside the approved VPN/firewall boundary. Shared credentials are not the
default. Record grant, rotation, expiry, and revocation.

Uvicorn binds 127.0.0.1:8000 and PostgreSQL binds loopback/Unix socket only.
Nginx or the approved proxy is the sole engineer-facing listener. It listens
only after the operator proves default-deny ingress and exact allowed
administration, HTTPS, and NFS paths for both IPv4 and IPv6.

Configure a root-managed default-deny guest firewall using ufw, nftables, or an
approved equivalent. Permit SSH only from the administration path and HTTPS
only from approved VPN/trial networks; permit no inbound NFS, API, or PostgreSQL
service. Cover IPv4 and IPv6 explicitly. Stage and review the exact rules,
confirm console/recovery access, and test rollback before activation so a rule
error cannot strand the VM. An upstream firewall remains required defence in
depth; replacing the guest firewall needs an explicit documented operator
decision.

The proxy must:

- serve frontend and API same-origin over TLS;
- accept only the approved hostname and methods;
- enforce bounded bodies, connection/time limits, and rate protection on
  operator/state-changing routes;
- strip untrusted forwarded headers and add only the required trusted values on
  the loopback hop;
- reject cross-origin state-changing requests;
- preserve application security headers or document the single header owner;
- preserve GET, HEAD, Range, If-Range, ETag, Accept-Ranges, and 206 behavior;
- avoid an uncontrolled proxy artifact cache;
- disable directory listing and direct derived-file serving; and
- restrict or disable interactive API documentation for trial users.

Restrict explicit rescan and deployment/operator surfaces to the operator
identity or loopback administrative path. Engineers retain the approved V1
preparation workflow but do not inherit obsolete state-changing V0 routes merely
because those routes remain for compatibility.

Media and IMU always pass through identity-bound application routes. VNC is
disabled after install or stays loopback-only through an approved admin tunnel.
SSH is administration-only. Ports 8000 and 5432 are unreachable remotely. NFS
is reachable only by the VM. No public DNS, port forwarding, wildcard listener,
or unreviewed IPv6 path is allowed.

Application-managed accounts and authorization roles remain deferred.

### Contract I — controlled release, backup, restore, and rollback

Implement and document this release order:

1. Verify Gate 0, maintenance approval, active release/schema, service state,
   queue/running work, mount identity, and capacity.
2. Close the engineer-facing proxy/API write entrance, resolve any durable
   paused or pause-requested current work through an explicit resume-and-drain
   or cancel decision, then drain the worker for planned work. Do not rewrite
   control state directly.
3. Stage and fully validate the candidate beside the active release.
4. Create a PostgreSQL custom-format pre-deploy dump to the approved protected
   destination and verify it with pg_restore --list.
5. Stop worker, then API.
6. Apply the candidate migration once under the migration lock.
7. Atomically switch the current release pointer.
8. Start API and worker, keeping the engineer proxy unhealthy/closed.
9. Verify local liveness, readiness/capabilities, catalog, processing overview,
   detail, media byte range, IMU, saved artifact, and zero implicit jobs.
10. Admit proxy traffic only after smoke checks.
11. Retain the previous release and exact configuration mapping until user
    acceptance.

Every release classifies rollback before activation:

- code-compatible rollback is allowed only when the previous release has been
  tested against the post-migration schema; or
- database-restore rollback uses the verified pre-deploy dump and the chosen
  coherent derived-state rule.

Do not improvise a down migration.

Minimum trial backup policy:

- PostgreSQL custom dump daily and before every schema change;
- pg_restore --list on every dump;
- an encrypted operator-approved off-VM copy with recorded owner, RPO,
  retention, expiry, and failure alert;
- a real restore into a disposable database before trial admission; and
- root-owned secret-safe configuration backup.

A VM/ZFS snapshot is not by itself a database-consistent backup. An off-VM copy
on the same NAS/pool protects against VM loss but not NAS/pool failure; record
that residual risk and the operator's decision.

The source archive is outside application backup ownership. For derived
artifacts choose and test exactly one rule:

- quiesce API/worker and take a coherent database plus derived-volume snapshot;
  or
- restore database metadata, mark absent derived files unusable, and explicitly
  regenerate them.

Never claim a database-only restore preserved ready output when its file was not
restored and revalidated.

### Contract J — logs, maintenance, support, and retirement

Use journald for API/worker and bounded Nginx access/error logs. Log release ID,
schema/migration result, scan counts/duration, bounded preparation outcomes, job
ID, numeric recording ID, artifact kind, state, duration, output size, safe
error code, worker lock/start/stop/interruption, mount/capacity capability
changes, backup result, and access administration outcome.

Never log source payloads, absolute source paths, database URLs, secrets,
Authorization headers, cookies, private keys, or certificates. Browser errors
and support bundles remain sanitized.

Provide an operator runbook with exact commands and expected output for:

- install/configure and site inventory;
- preflight and mount-identity validation;
- migrate, start, stop, drain, restart, boot enablement, and status;
- local and proxied health;
- logs and sanitized support collection;
- explicit rescan and queue/worker/interrupted-job handling;
- source/derived/database outage response;
- capacity inspection and expansion handoff;
- backup verification, disposable restore, upgrade, and rollback;
- OS/ROS/FFmpeg/PostgreSQL/Nginx security patching and reboot;
- TLS renewal and access grant/revoke;
- TrueNAS/VM escalation without appliance commands hidden in project scripts;
  and
- trial retirement that disables access and preserves data until a separately
  approved retention/deletion decision.

Provide a bounded, non-mutating source-manifest command for acceptance evidence.
It records only relative names, entry kinds, sizes, and high-resolution
modification times; it follows no symlinks, respects configured traversal
bounds, reads no payload hashes, writes outside the source, and is separate
from the disposable-database real-archive test helper.

Assign daily/weekly/monthly checks, log retention, backup failure monitoring,
capacity owner, certificate/credential expiry, security update cadence,
incident/escalation contacts, January 2027 platform decision owner, and engineer
feedback owner.

Provide an engineer guide with the approved URL/access path, Recordings →
Prepare selected → Processing → Analyzer flow, read-only source promise, known
prototype limitations, expected queue behavior, how to report a recording/job
ID safely, and access-support contact.

### Required repository implementation areas

Prefer a small explicit structure:

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

Exact names may follow established conventions. Scripts must use explicit
validated targets, be non-interactive where practical, fail closed, use safe
quoting, avoid secret output, never edit TrueNAS, and support temporary-root
testing. Do not commit active /etc, /opt, /var, mount, database, backup,
certificate, credential, or service state.

### Required implementation phases

#### Phase 1 — freeze and test repository contracts

1. Complete the mandatory audit and sanitized target gap report.
2. Turn Gate 0 and the real-data annex into operator templates outside secret
   values.
3. Write deployment/security/lifecycle tests before implementation.
4. Implement configuration, preflight, capability-aware health, and low-space
   behavior.
5. Implement immutable packaging, systemd, proxy, release/migration,
   backup/restore, smoke, and support assets.
6. Write operator and engineer guides.
7. Run full static, application, browser, PostgreSQL, ROS, proxy, and disposable
   lifecycle verification.

If no VM exists, finish Phase 1 and hand off the exact external gates. Do not
fake live evidence.

#### Phase 2 — accept the administrator foundation

8. Review every Gate 0 value without committing sensitive details.
9. Prove patch state, SSH/recovery, console state, boot setting, time sync,
   disk/filesystem identities, start/stop budget, network policy, source export,
   derived capacity, backup destination, and beta-host decision.
10. Present the exact inside-guest command/file/service change set, interruption,
    backup, and rollback. Obtain user confirmation before live mutation.
11. Test base VM recovery/snapshot handling with the administrator; do not alter
    TrueNAS from repository scripts.

#### Phase 3 — commission storage and application

12. Stage the authoritative source mount unit and configuration, but keep
    application services disabled and do not traverse the live source. Use a
    disposable synthetic read-only source for installation tests.
13. Format/mount only the exact approved derived disk, after destructive target
    resolution and explicit authority, then verify ownership, separation,
    atomic behavior, and thresholds with disposable content.
14. Install the immutable release, local PostgreSQL, migration workflow,
    services, and proxy without admitting trial users.
15. Initialize a fresh empty database and apply/validate its schema by default,
    with zero source rescan. Use the separately approved state-transfer annex if
    history/artifacts must migrate.
16. Run local smoke, backup/restore, rollback, access, service-restart, and
    outage/full-disk tests only with the disposable synthetic source
    configuration. Keep live API/worker services stopped and unable to traverse
    the authoritative mount until Phase 4 approval and before-inventory capture.

#### Phase 4 — bounded real-data acceptance and handoff

17. Confirm the exact real-data annex. Establish the exact source mount and use
    mount metadata only to verify server/export, filesystem, mountpoint, and ro
    identity; do not traverse source entries yet.
18. Capture the source before inventory as the first project-controlled content
    read. Only then run full source-aware preflight and live matrix items 1–15;
    do not capture the final after inventory yet.
19. After those checks pass, enable rosbag-analyser.target, verify the existing
    administrator-owned TrueNAS VM-autostart setting, reboot the guest VM, and
    complete live matrix item 16. Do not reboot the NAS host.
20. Complete live matrix item 17: capture the final after inventory in success
    or failure and prove every application write remained in an owned root.
21. Have an operator other than the developer follow the runbook. Access
    grant/revoke was already proved by live matrix item 15.
22. Record evidence and stop for user acceptance before admitting the trial
    group.

### Required automated and disposable verification

At minimum cover:

- secret, credential, private-address/path, source-payload, and generated-data
  repository scans;
- locked build/package identity, imports, pip check, ROS and FFmpeg capabilities;
- environment parsing, bounds, root/file modes, redaction, and unsafe listeners;
- source/derived missing, overlap, symlink, wrong mount/export/filesystem,
  writable-source, local-directory fallback, permissions, atomic rename, and
  low-space behavior, plus source identity stability across remount/reboot;
- proof that preflight/health/startup performs no rescan, job creation, full
  source read, or source mutation;
- capability-aware health truth tables for database, source, derived, space, and
  worker states;
- systemd static verification for identities, paths, environments, mounts,
  ordering, boot target, restart limits, stop timing, hardening, journald, and
  exactly one worker;
- Nginx syntax/static checks for TLS/access, both IP-family assumptions,
  hostname/method/body/header/cross-origin limits, docs restriction, no direct
  file serving, and no uncontrolled cache;
- guest-firewall rule/static validation plus allowed/denied IPv4 and IPv6
  reachability and tested administrative recovery;
- proxied GET/HEAD/Range/If-Range/ETag/206 and stale-identity behavior;
- single migration, incompatible-schema refusal, fresh database initialization,
  optional coherent state-transfer rejection cases, atomic release switch, and
  both rollback classifications;
- dump verification, disposable restore, coherent derived recovery, and
  backup-failure reporting;
- API/worker drain, restart, forced interruption, advisory lock, persistence,
  and zero implicit scan/preparation;
- disposable PostgreSQL loss, NFS loss/wrong mount, and full-derived-filesystem
  recovery without duplicate jobs or ready-artifact deletion; and
- all accepted Python, PostgreSQL, ROS-message, JavaScript/browser, and local
  launcher regressions.

Tests never depend on the live source archive.

### Live network, lifecycle, and real-source acceptance

Complete the real-data annex before this phase. It must name outside Git:

- the exact export and guest source root;
- the exact short healthy and representative long healthy recording
  identifiers/cases, plus an already-known approved malformed case when the
  fixed root contains one;
- whether history/derived state is fresh or transferred;
- permitted rescan and three existing artifact kinds only;
- expected capacity and the approved long-processing window;
- before/after inventory command and protected evidence location; and
- operator, project owner, and rollback contact.

After explicit approval, the allowed source actions are read-only lightweight
inventory, one bounded recursive rescan, existing front/top-down/IMU processors
for the named healthy cases, ordinary identity-validated delivery, and bounded
user-flow checks. No other recording, processor, source repair, reindex,
database write mode, or write probe is authorized.

Record and prove:

1. Clean installation/migration and local smoke checks complete without exposing
   the proxy.
2. From approved and denied IPv4 and IPv6 vantage points, only the intended TLS
   endpoint is available to a trial user. Verify HTTPS allow/deny, SSH admin
   restriction, NFS VM-only restriction, VNC disabled/loopback-only, and remote
   rejection of ports 8000 and 5432.
3. Administrator export evidence and client mountinfo/findmnt both prove the
   exact read-only source path; absent/wrong mount makes services fail closed.
   Record source device/inode identity across remount and reboot; if otherwise
   unchanged recordings acquire incompatible current identities, stop rather
   than changing the accepted identity contract inside deployment work.
4. Start and service restart load saved state and create no scan, job, or
   artifact. The guest-reboot proof occurs in item 16 after target enablement.
5. The source before inventory is captured. One explicit bounded rescan
   completes, creates zero jobs, reports incomplete traversal honestly if
   applicable, and leaves the inventory identical.
6. The named short healthy recording produces and serves all three accepted
   artifact kinds.
7. The named long healthy recording runs only in the approved window after
   checking free space. Measure duration, peak temporary/final growth, CPU,
   memory, database load, and NAS throughput without promising an SLA.
8. When an already-known approved malformed case exists in the fixed root, it
   stays honestly unavailable and is never repaired. Otherwise retain the
   synthetic malformed acceptance and record this live item not applicable;
   never search outside the fixed root merely to manufacture the case.
9. Two engineer sessions can browse saved catalog and ready artifacts while one
   serial worker runs. A bounded mixed Prepare selected request is idempotent,
   displays the exact authoritative queue order after allowed controls, and
   never shows more than one running job.
10. Through the proxy, verify front/top byte ranges and HEAD, stale identity
    rejection, all six IMU choices, global clock, seek, 100 ms correction, and
    coverage hide/clear behavior.
11. Restart API/worker services with queued work and prove persistence. In a
    controlled case, interrupt one running worker: only that job becomes
    interrupted, only its owned temporary workspace is cleaned, ready artifacts
    remain, and explicit retry succeeds.
12. Stop PostgreSQL only in an approved window and verify sanitized degradation,
    bounded restart/backoff, recovery, and no duplicate jobs.
13. Simulate source loss/wrong mount and derived-full threshold only with
    disposable substitutes; verify capability degradation, fail-closed
    identity, safe rejection, and preservation of valid state.
14. Verify a database dump, restore it into an exact disposable database, and
    rehearse the recorded previous-release rollback.
15. Grant then revoke one test engineer and prove revoked access fails.
16. After rosbag-analyser.target is enabled, reboot the guest VM, optionally
    with queued work, and repeat mount identity, services, proxy, saved-state,
    queue persistence, and zero-implicit-work checks.
    Verify the administrator's TrueNAS VM-autostart configuration separately;
    observe a full NAS-host boot only at its next independently approved
    maintenance event.
17. Capture the final source inventory in success or failure. It must match
    exactly. Prove every created file is below the approved release,
    configuration, database, derived, log, or backup root.

Never run mount-loss, disk-full, restore-overwrite, share-edit, snapshot
rollback, or destructive cleanup against authoritative source/live targets.
Use exact disposable targets.

### Prohibited scope

Do not:

- create/change a TrueNAS dataset, zvol, share, ACL, snapshot, network, firewall,
  VM, appliance setting, or appliance version;
- reboot or otherwise interrupt the TrueNAS host or unrelated workloads;
- expose any application, database, NFS, SSH, or VNC path publicly;
- run Humble on an unsupported newer Ubuntu or perform an in-place platform
  upgrade;
- add containers, Kubernetes, HA, Redis, broker, multiple workers, priority,
  new processing control kinds, automatic retry, quota eviction, or source
  watching;
- add application-managed users/roles;
- add processors, source formats, artifact kinds, telemetry, timing changes, or
  frontend redesign;
- automatically delete source, derived output, database state, backups, or
  releases;
- repair, reindex, migrate, back up, snapshot, hash large payloads, or write-probe
  original recordings;
- copy a development database without its coherent identity/derived-state rule;
- run destructive commands without exact target resolution and explicit
  authority; or
- commit, push, change remotes, open a pull request, or publish a release.

### Stop conditions

Stop and request direction if:

- the administrator handoff, site annex, exact target, owner, or recovery path
  is incomplete;
- live commands or targets differ from the reviewed change set;
- the source cannot be exported independently server-side read-only to the
  exact VM, the allow list is effectively open, root mapping/security is
  unresolved, parent/child exports are ambiguous, or an existing consumer could
  be disrupted;
- source mount identity cannot fail closed, the source is writable, or any
  process requires a write-capable source open;
- source and derived overlap, derived capacity/atomic semantics are inadequate,
  or safe operation would require automatic deletion;
- IPv4 or IPv6 can bypass the approved private/VPN TLS boundary, or VNC/raw
  API/PostgreSQL/NFS is unexpectedly reachable, or no tested default-deny guest
  firewall/equivalent and recovery path exists;
- TrueNAS beta risk, VM shutdown timing, support lifecycle, credentials,
  patching, certificate renewal, access revocation, capacity, backup, or
  escalation has no named owner;
- no verified off-VM database backup/disposable restore exists;
- migration is destructive, incompatible, or lacks a proven rollback;
- an immutable reviewed release cannot be identified without unapproved Git
  action;
- implementation requires a new platform, major dependency, multiple workers,
  processor/artifact/timing behavior, source mutation, public exposure, or
  application authentication; or
- any before/after source inventory differs.

Do not stop merely because the VM or operator value is not yet available.
Complete safe repository-side work, mark live phases unverified, and hand off
the precise external gate.

### Completion handoff

Report local implementation and live commissioning separately.

Include:

- approved boundary and every repository file changed;
- unchanged accepted Blocks 1 and 2 behavior and ./dev workflow;
- release source identity/checksum and dirty/commit status;
- Gate 0 decisions and owners without secrets or private paths;
- OS, ROS, Python, PostgreSQL, FFmpeg, Nginx, NFS, and application versions;
- package/repository/licence inventory;
- installed release layout and exact sanitized service identities;
- mount topology, server/client read-only evidence, derived isolation/capacity,
  and atomic/low-space results;
- database initialization or coherent state-transfer choice, schema/migration,
  backup verification, disposable restore, and rollback classification;
- listeners, firewall/VPN/TLS/authentication evidence for IPv4 and IPv6;
- TrueNAS VM-autostart configuration evidence; systemd target enabled/active
  state; guest-reboot boot order; next NAS-host observation status;
  restart/drain/interruption timing, hardening, and exactly-one-worker evidence;
- liveness/readiness capability behavior;
- every automated/static/disposable command and result;
- live acceptance items actually completed and those still pending;
- measured resource, duration, throughput, and derived-growth observations;
- source before/after inventory equality and generated-path containment;
- access grant/revoke and operator-runbook exercise;
- TrueNAS beta, same-NAS failure-domain, single-VM/no-HA, support-lifecycle,
  backup, capacity, and security residual risks with owners/dates;
- Git status and explicit uncommitted state; and
- the exact user decision required before admitting engineers.

Building block 3 is not accepted until the user reviews this evidence and
explicitly approves the limited trial handoff.
