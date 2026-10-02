# Architecture

## Runtime and code

FastAPI serves the packaged React frontend from `src/rosbag_analyser/web/react/`.
PostgreSQL stores catalog and job metadata; one serial ROS-aware worker creates
derived files. The runtime is Ubuntu 22.04, Python 3.10 and ROS 2 Humble; the
[release contract](../deploy/release-contract.json) defines deployment requirements.

```text
Browser -> private proxy -> FastAPI -> PostgreSQL
                               |           |
                         explicit scan    jobs
                               |           |
                         read-only source <- Worker -> derived files
                                                            |
                                              identity-checked API delivery
```

The API validates requests and delivers data. Services coordinate workflows;
processors decode and transcode. Startup does not scan, prepare or migrate.

| Modules in `src/rosbag_analyser/` | Responsibility |
| --- | --- |
| `catalog/`, `v1_catalog.py` | Bounded discovery, metadata, health and saved catalog |
| `preparation_planner.py`, `preparation.py` | Output identity, prerequisites, reuse and scheduling |
| `processing_view.py`, `estimation.py`, `job_control.py` | Queue views, runtime, estimates and controls |
| `persistence/` | PostgreSQL repositories and ordered migrations |
| `processors/`, `front_preview.py`, `topdown_preview.py`, `imu_series.py` | Output processing |
| `artifact_store.py`, `timeline.py` | Publication, validation, coverage and time mapping |
| `api/`, `worker.py`, `web/` | HTTP delivery, worker and packaged frontend |
| `config.py`, `deployment.py`, `preflight.py`, `health.py` | Configuration, mount/capacity checks and service health |

## Catalog and persistence

The scanner has depth, entry, directory and recording limits and never follows
symlinks. A damaged recording is isolated. An incomplete scan cannot replace the
last successful catalog or mark unseen recordings missing. Scanning creates no jobs.

Six tables hold domain state: `recordings`, `source_components`, `artifacts`,
`jobs`, `catalog_state` and `preparation_targets`. Applied SQL migrations,
currently through `0009_recording_inspection.sql`, remain part of the upgrade path.

Catalog and processing reads use saved projections, without source access per row.
Each successful scan saves three preparation targets per recording. Planner or
configuration changes require an explicit rescan; the worker revalidates inputs.

The scan saves topic names, types and counts in `recordings.scan_details`.
Timestamp inspection uses a verified immutable SQLite descriptor without loading
payloads, bounded to two million messages, five seconds and 256 Image/IMU topics.
A gap must be at least five seconds and twenty times the median of the first
1,024 positive intervals, with at least twenty intervals of cadence evidence.
Checks cover the bag and individual camera/IMU streams; the largest 24 gaps are
saved with relative locations. Incomplete checks are marked partial. Gap evidence
sets presentation health to Review without changing readability or preparation
eligibility; timestamps alone do not prove data loss.

Missing paths disappear from the current catalog but retain history. A unique
one-to-one move match preserves IDs, cache anchors, jobs and reusable artifacts;
ambiguous matches remain separate. Reconciliation changes metadata only.

## Preparation and jobs

Preparation takes a bounded ordered recording list and a non-empty subset of
`front_preview`, `topdown_preview` and `imu_series`. Each output independently
reuses ready/active work, queues missing work or reports unavailability. Active
identities cannot be duplicated. Retry resolves current inputs.

The recording state precedence is failed, processing, queued, ready, not planned.
Any failed output or unavailable front input makes it Failed. Ready requires a
validated front preview and no active or failed output. Top-down and IMU are
optional; Analysis can review available output independently.

A PostgreSQL advisory lock permits one worker. Claim, insertion, reordering and
queued cancellation share a stable queue order. Durable pause/resume/cancel
requests take effect at safe processing and publication checkpoints. Worker
restart marks abandoned running or paused work interrupted; retry is explicit.
The UI exposes cancellation; pause/resume remains available through the API.

Elapsed and active time come from persisted timestamps. Estimates use the ten
newest compatible artifact-backed successes, with at least two samples, excluding
paused time. `recent_rate_v2` uses the 80th-percentile runtime per input byte plus
15% headroom. Queue estimates refresh together when a recording's first output
starts, then freeze across output handoffs. An older useful estimate survives
when refreshed history has too few samples.

The overview groups the current recording run by persisted job timestamps,
including completed siblings and queued outputs, excluding older reused output.
The active card retains that identity during handoffs and sums active elapsed
time and frozen estimates. A missing member estimate makes the total unavailable.
The UI displays elapsed / estimated time, capped at 99%, and **Estimate exceeded**
when elapsed reaches the estimate. This is a runtime estimate, not measured
completion. Cancellation dismisses work immediately and restores it on failure.

During deployment, a root-owned maintenance gate rejects mutations with
503/Retry-After and holds new claims while active work finishes. It stays closed
through migration and health checks, including incompatible-schema failure.
Queued work and recordings are preserved; recovery is in [Operations](OPERATIONS.md).

## Artifacts and source safety

| Output | Format and identity |
| --- | --- |
| Front preview | `front-preview-v5`; validated MP4 per supported raw CDR Image stream |
| Top-down preview | `topdown-preview-v2`; AVI frames timed by CSV Unix timestamps; H.264/yuv420p MP4 |
| IMU | `imu-series-v2`; schema-2 JSON with three angular-velocity and three linear-acceleration axes |

Front discovery accepts nonempty CDR ROS Image streams with `bgr8`/`rgb8`
encoding. All eligible topics form one job and bundle, ordered by message count
then name. The busiest supported stream is the default; skipped encodings retain
diagnostics. Each MP4 is timed and validated independently before atomic bundle
publication. Stream URLs use artifact identity and numeric manifest index, never
a topic name as a path. IMU selection uses a valid configured preference or one
unique standard IMU stream; ambiguous streams are not combined.

Incomplete output stays in a contained job workspace. Publication follows
validation; failed replacement preserves valid output. Files, manifest, identity
and settings must agree. Delivery, including ranges, binds to one artifact
identity and cannot silently return its replacement. Media and telemetry stay
outside PostgreSQL and Git.

Source SQLite opens read-only and immutable. Source and derived paths never
overlap; source symlinks are not followed. On a shared NAS dataset, the writable
mount exposes only `Rosbag_Analyser_Cache`, which source walkers exclude before
traversal, inventory and identity calculation. Persisted `portable-stat-v1`
hashes tolerate CIFS device/inode differences; live reads still compare full
device/inode/mode/size/mtime/ctime facts. Derived CIFS timestamp handling does not
relax source checks.

Processors use bounded payload reads and one ordered SQLite query per stream.
Video validation streams packet timestamps through ffprobe with bounded,
size-dependent timeouts. Worker control checks reuse its advisory-lock session
in short transactions. Readiness runs in the bounded catalog pool. Low derived
capacity rejects new work without deleting ready output; source loss preserves
saved catalog state. Mount, release and schema checks fail closed.

## Timing and playback

Front coverage uses ROS record endpoints. Strictly increasing valid image-header
timestamps map affinely between those endpoints. Only streams whose headers are
all exactly zero use ROS record cadence directly. Mixed, missing, invalid or
unordered headers fail. Duplicate front record times keep the last frame;
no fixed frame rate or interpolated frames are invented.

IMU uses database record time and preserves source order. Nanoseconds are decimal
strings; lookup selects the last sample at or before the clock, including duplicate
times. Non-finite values are per-axis null gaps. JSON is capped at 64 MiB and
validated row by row. The browser streams parsing and reduces visible points while
preserving spikes and gaps; large sample bundles stay outside subscribed UI state.

One bag-relative clock drives cameras and IMU. Cameras correct drift at 100 ms
and hide outside measured coverage; numeric IMU readouts clear outside coverage.
The graph may visually hold a finite final sample to the recording/camera end
without changing samples or readout coverage. Zoom changes the view, not time.
Without IMU, the clock uses recording metadata Unix time, or relative seconds.

The dense SVG trace is memoized and composited separately from the HTML cursor.
The cursor uses fractional transforms each animation frame; React readouts and
camera drift checks update at up to 20 Hz. Pointer seeks are frame-coalesced.
Cameras show buffering until a frame is decoded, then retain that frame during
seeks. Each decoder finishes an in-flight seek before taking the latest request.
Automatic correction waits 500 ms after seeking; explicit seeks bypass this wait.
An eight-second no-progress watchdog works even while paused. Stalls and load
failures share three bounded reload attempts, then offer a manual Retry control.
Recovery retains the shared clock and clears that camera's diagnostic. Navigation
disposes media, listeners, observers, timers and animation frames.

## Browser and HTTP

React source lives in `frontend/`. `WorkspaceProvider` retains small session
settings across routes; playback stops on unmount. The default service calls the
real API. Explicit `?synthetic=1` selects in-memory fixtures and never calls it;
the synthetic launcher serves only loopback assets without backend services.

`api-types.ts` defines contracts, `api-mapping.ts` maps domain models and
`api-workspace.ts` owns polling and commands. Route cleanup aborts reads and
timers. Mutations invalidate older reads and are never replayed automatically.
Initial loading is separate from cached refresh. Preparation/retry keeps an
empty queue loading until the request and refresh finish, including navigation;
counts come from server results. Errors restore dismissed data and appear in
the dismissible shell message.

Processing follows all overview/list cursors with cycle detection, deduplication
and abort/version guards. A failed page preserves the last complete snapshot.
Successful siblings stay with failed recordings; retries submit only failed job
IDs. History groups latest successful outputs for recordings without failures.

`/api/v1` provides catalog, explicit rescan, details, preparation and job controls.
`/api/recordings/...` delivers identity-bound media and IMU. React routes are
`#/recordings`, `#/processing` and `#/analysis/{id}`; the server also accepts
`/`, `/processing` and `/recordings/{id}`. API schemas live in `api/`.

Backend text is rendered as text, with validated IDs and URLs. Errors are
sanitized and absolute source paths stay server-side. The API listens on loopback
behind the site's access boundary; PostgreSQL is local. Development and component
conventions are in [Development](DEVELOPMENT.md).
