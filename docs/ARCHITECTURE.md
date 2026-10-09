# Architecture

## Runtime and code

FastAPI serves the packaged React frontend from `src/rosbag_analyser/web/react/`.
PostgreSQL stores catalog and job metadata; one serial ROS-aware worker creates
derived files. The runtime is Ubuntu 22.04, Python 3.10 and ROS 2 Humble; the
[release contract](../deploy/release-contract.json) defines deployment requirements.

```text
Browser -> private proxy -> FastAPI -> PostgreSQL
                               |           |
                       discovery/rescan   jobs
                               |           |
                         read-only source <- Worker -> derived files
                                                            |
                                              identity-checked API delivery
```

The API validates requests and delivers data. Services coordinate workflows;
processors decode and transcode. Startup does not scan, prepare or migrate.
API shutdown gives active HTTP responses ten seconds to finish before cancelling
them and closing request resources, so stalled media reads cannot prevent restart.

| Modules in `src/rosbag_analyser/` | Responsibility |
| --- | --- |
| `catalog/`, `v1_catalog.py` | Bounded discovery, metadata, health and saved catalog |
| `preparation_planner.py`, `preparation.py` | Output identity, prerequisites, reuse and scheduling |
| `processing_view.py`, `estimation.py`, `job_control.py` | Queue views, runtime, estimates and controls |
| `persistence/` | PostgreSQL repositories and ordered migrations |
| `processors/`, `front_preview.py`, `topdown_preview.py`, `imu_series.py`, `encoder_series.py` | Output processing |
| `artifact_store.py`, `timeline.py` | Publication, validation, coverage and time mapping |
| `api/`, `worker.py`, `web/` | HTTP delivery, worker and packaged frontend |
| `config.py`, `deployment.py`, `preflight.py`, `health.py` | Configuration, mount/capacity checks and service health |

## Catalog and persistence

The scanner has depth, entry, directory and recording limits and never follows
symlinks. A damaged recording is isolated. An incomplete scan cannot replace the
last successful catalog or mark unseen recordings missing. A successful scan queues
only unattempted, available thumbnails, atomically with the catalog update. Compatible
artifacts and prior attempts are retained; failures and cancellations require explicit retry.

Each browser page load silently requests addition-only discovery in the catalog scan
pool; concurrent requests share one operation. Discovery skips known recording
roots before enumerating their contents, and inspects only new paths. Unreadable or
incomplete new bags remain unsaved for a later page load or full rescan. New records,
targets and unattempted thumbnails commit together under the catalog/queue locks.
Existing rows, targets, jobs and artifacts stay unchanged; the full-scan generation,
completion time and duration do not advance. Discovery can initialize targets at
generation zero. Known-path presence is retained without inspecting contents;
possible moves with matching saved fingerprints wait for full reconciliation.
Only a full rescan reconciles changes, moves and missing sources.

Six tables hold domain state: `recordings`, `source_components`, `artifacts`,
`jobs`, `catalog_state` and `preparation_targets`. Applied SQL migrations,
currently through `0013_thumbnail.sql`, remain part of the upgrade path.

Catalog and processing reads use saved projections, without source access per row.
Each successful scan saves six preparation targets per recording. Planner or
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
`front_preview`, `ai_description`, `topdown_preview`, `imu_series`, `encoder_series`
and `thumbnail`. Each output
independently reuses ready/active work, queues missing work or reports unavailability. Active
identities cannot be duplicated. Retry resolves current inputs.

The recording state precedence is failed, processing, queued, ready, partially
prepared, not planned.
Any failed output or unavailable front input makes it Failed. Ready requires a
validated front preview and AI description, with all available outputs ready and
no active or failed output. Any ready output with other preparation still needed
is Partially prepared, including after a rescan changes a camera target or adds
an encoder target. Unavailable top-down, IMU and encoder inputs are optional;
Analysis can review available output independently.

Thumbnails are independent jobs reading the default eligible colour camera directly
from immutable source SQLite, without preparing videos or AI descriptions. Timestamp-only
queries select the first frame at or after the stream's record-time midpoint, keeping
the last message at duplicate timestamps. At most 256 candidate streams are inspected;
monochrome first frames are excluded before colour-image validation. Payloads are bounded
and only candidate first frames and the chosen frame are decoded. Queries have a 30-second
budget between control checkpoints. The PNG retains aspect ratio, has a maximum side of
480 pixels and a 1 MiB limit, and is validated with dimensions, decoded content and a
SHA-256 digest before publication and delivery.
Unchanged catalog image validation is cached against full file facts and manifest identity
in a bounded 10,000-entry cache; anchored path/manifest checks still run on each poll.
Identity derives from saved front-source identity and the fixed thumbnail policy;
no prepared preview is required. Thumbnail
estimates use one work unit per image. Migration 0013 derives targets from saved front
facts without source access or creating jobs; full rescan queues unattempted thumbnails,
and Prepare Selected fills missing output or retries failed/cancelled attempts.

AI descriptions are separate jobs after the front preview. They read its default
stream through a validated, held file descriptor and sample six chronological PNG
frames at a maximum side of 448 pixels. Qwen3-VL-2B-Instruct Q8_0 and the matching
F16 vision projector run offline through pinned llama.cpp CPU binaries, using the
application's Python environment. A job-owned server accepts one constrained JSON
completion over a private Unix socket; it exposes no TCP listener. The prompt and
formatter retain the three required bunker cues: gravel-like terrain, dark
curtains and artificial lighting. Four CPU inference threads are the default.

Validated JSON is published atomically and exposed in recording details and the saved catalog.
Inference errors leave existing artifacts intact. Migration 0012 derives current
description targets from saved front targets without scanning sources or creating
jobs; the new identity prevents reuse of old model/sampling output. Prepare
Selected reuses compatible artifacts; a reordered description waits for active
front work. Cancellation terminates inference, the server and decoders; pause
holds their process group at a checkpoint before publication. Generation has a
300-second active-time limit, excluding pauses. Model provisioning is explicit,
verified and separate from application startup and recording processing.

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
| Thumbnail | `thumbnail-v1:default-colour:record-midpoint:side480:png`; validated PNG from one source image |
| Front preview | `front-preview-v6`; validated MP4 per supported raw CDR Image stream |
| Top-down preview | `topdown-preview-v2`; AVI frames timed by CSV Unix timestamps; H.264/yuv420p MP4 |
| AI description | `ai-description-v2`; bounded JSON with the short description and bunker boolean, tied to front identity and fixed model/prompt/sampling policy |
| IMU | `imu-series-v2`; schema-2 JSON with three angular-velocity and three linear-acceleration axes |
| Encoders | `encoder-series-v1`; schema-2 JSON with six RPM channels in FL, FR, ML, MR, RL, RR order |

Front discovery accepts nonempty CDR `sensor_msgs/msg/Image` streams whose first
image uses `rgb8`, `bgr8`, `rgba8` or `bgra8`. Alpha is discarded for video previews.
Other encodings, including monochrome Ouster measurement images, are excluded
before camera validation and produce no stream-failure diagnostics. Every frame
of an eligible stream must satisfy the colour-image and timing contracts.
All eligible topics form one job and bundle. Names with a `front` component
(including camelCase) come first, then message count descending and topic name
ascending; the first eligible stream is the default. Each MP4 is timed and
validated independently before atomic bundle publication. Stream URLs use
artifact identity and numeric manifest index, never a topic name as a path.
IMU selection uses a valid configured preference or one
unique standard IMU stream; ambiguous streams are not combined. Encoder selection
uses a configured preference or one unique CDR `kuupkulgur_msgs/msg/EncodersStamped`
stream. Its bounded decoder reads `Header` plus `Float64MultiArray` with exactly
six values, following RD01. No custom ROS message package is required. Migration
0011 adds the optional kind; an explicit rescan discovers its targets.

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

IMU and encoder series use database record time and preserve source order. Nanoseconds are decimal
strings; lookup selects the last sample at or before the clock, including duplicate
times. Non-finite values are per-channel null gaps. JSON is capped at 64 MiB and
validated row by row. The browser streams parsing and reduces visible points while
preserving spikes and gaps; large sample bundles stay outside subscribed UI state.
For display, brief extreme excursions become trace gaps and inspectable markers,
without changing recorded samples. With at least twenty finite reference values
(uniformly sampled up to 4,096), the envelope uses the 10th/90th percentiles plus
ten times their magnitude or range (minimum 0.001). Excursions must return to
finite ordinary data within one second, or end at coverage within one second of
ordinary data. Sustained changes and runs beside null gaps remain plotted.
Gap bands span the surrounding ordinary samples and retain the largest excursion
per wheel/axis in each display bucket; zoom reveals finer events. Coverage-edge
bands stop at measured coverage. Original values do not affect autoscaling.

One bag-relative clock drives cameras, IMU and encoders. Cameras correct drift at 100 ms
and hide outside measured coverage; numeric telemetry readouts clear outside coverage.
Telemetry traces stop at their first and last measured samples; no endpoint hold
is drawn. Zoom changes the view, not time. Five dotted grid lines keep fixed
positions across channel selections and zoom; readout space is reserved independently
of selection, with the scale label in a separate left lane. Angular velocity and
RPM scales are symmetric about zero. A single acceleration axis centers on its
first visible value (interpolated at the view boundary when needed); combined
acceleration axes fit their shared range. Encoder traces share one RPM axis in the six-wheel
view; individual wheel selection uses the same samples. Without IMU, the clock
uses recording metadata Unix time, or relative seconds.

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
`POST /api/v1/catalog/discover` adds new recordings without making catalog reads
touch sources. The browser requests it once per page load, independently of polling
and route changes, without loading text or blocking controls. Sidebar Settings
provides **Do a full rescan**.
`/api/recordings/...` delivers identity-bound media, IMU and encoder series. React routes are
`#/recordings`, `#/processing` and `#/analysis/{id}`; the server also accepts
`/`, `/processing` and `/recordings/{id}`. API schemas live in `api/`.

Backend text is rendered as text, with validated IDs and URLs. Errors are
sanitized and absolute source paths stay server-side. The API listens on loopback
behind the site's access boundary; PostgreSQL is local. Development and component
conventions are in [Development](DEVELOPMENT.md).
