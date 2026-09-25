# Architecture

## Runtime

One FastAPI application serves the packaged React browser frontend from
`src/rosbag_analyser/web/react/`. The source app in `frontend/` also runs
through a local Vite proxy during development. Production selects the real API
workspace; the synthetic archive is available only in Vite development mode. PostgreSQL
stores catalog and job metadata; one serial ROS-aware worker creates files in
the derived-data root. The VM runtime is Ubuntu 22.04, Python 3.10, and ROS 2
Humble, as recorded in [the release contract](../deploy/release-contract.json).

```text
Browser → private access proxy → FastAPI → PostgreSQL
                                   │          ↑
                      explicit scan│          │jobs
                                   ↓          │
                         read-only source ← Worker → derived artifacts
                                                        ↑
                                      identity-checked API delivery
```

The API owns request validation and delivery. Application services own
workflows; processors own expensive decoding/transcoding. Services do not
scan, prepare, or migrate automatically at startup.

## Code map

| Modules | Responsibility |
| --- | --- |
| `catalog/`, `v1_catalog.py` | Bounded discovery, metadata, health, saved catalog and folders |
| `preparation_planner.py`, `preparation.py` | Current output identities, prerequisites, reuse and scheduling |
| `processing_view.py`, `estimation.py`, `job_control.py` | Queue views, factual runtime, estimates and cooperative controls |
| `persistence/` | PostgreSQL repositories and ordered SQL migrations |
| `processors/`, `front_preview.py`, `topdown_preview.py`, `imu_series.py` | Source resolution and the three output processors |
| `artifact_store.py`, `timeline.py` | Contained publication, validation, coverage and time mapping |
| `api/`, `worker.py`, `web/` | HTTP delivery, serial execution and the served browser |
| `config.py`, `deployment.py`, `preflight.py`, `health.py` | Validated settings, mount/capacity admission and service health |

Paths above are relative to `src/rosbag_analyser/`.

## Catalog and persistence

The scanner traverses one configured source root with depth, entry, directory,
and recording limits. It never follows symlinks. A damaged recording is isolated;
an incomplete traversal cannot replace the last successful catalog or mark
unseen recordings missing. Scanning creates no processing jobs.

Six domain tables hold state: `recordings`, `source_components`, `artifacts`,
`jobs`, `catalog_state`, and `preparation_targets`. Migrations currently run
through `0007_job_controls.sql`; applied migrations remain part of the upgrade
path and must not be removed as old files.

Ordinary catalog and processing reads use saved PostgreSQL projections. Each
successful scan stores three preparation targets per recording. A changed
planner/configuration needs an explicit rescan; browsing does not stat or parse
the source per row. The worker independently revalidates inputs.

Missing paths retain internal history but disappear from the current catalog.
A one-to-one move match preserves IDs, private cache anchors, jobs, and reusable
artifacts. Ambiguous matches remain separate. Reconciliation changes metadata,
never source or derived files.

## Preparation and jobs

Preparation accepts a bounded ordered list of recordings and a non-empty subset
of `front_preview`, `topdown_preview`, and `imu_series`. Each chosen output is
resolved independently: reuse ready/active work, enqueue missing work, or report
unavailability. Repeated requests cannot duplicate an active identity. A failed
attempt is retried using current inputs, not its obsolete identity.

The catalog's aggregate state follows failed → processing → queued → ready →
not planned. Any failed output makes the recording Failed; otherwise any ready
output makes it Ready once active work is finished. Unavailable or absent
sources do not prevent available outputs from being prepared. Each output keeps
its detailed state. Analyzer
can also review available output independently, including a camera-only
recording timeline when IMU is unavailable.

A PostgreSQL advisory lock protects the single worker. Claim, insertion,
reorder, and queued cancellation share the same stable queue order. Durable
pause/resume/cancel requests are acknowledged at safe processing and publication
checkpoints. Restart marks abandoned running work, including paused work,
interrupted; it does not resume the process automatically.

Elapsed and active time come from stored timestamps. Estimates freeze a median
runtime-per-input-byte prediction from at least two compatible successful jobs.
They can be unavailable or exceeded. The UI does not invent percentage progress.

## Artifacts and time

| Output | Current behavior |
| --- | --- |
| Front preview | `front-preview-v4`; standard ROS Image `bgr8`/`rgb8`; H.264/yuv420p MP4 |
| Top-down preview | `topdown-preview-v2`; AVI frames timed by CSV Unix timestamps; H.264/yuv420p MP4 |
| IMU | `imu-series-v2`; schema-2 JSON with three angular-velocity and three linear-acceleration axes |

Front coverage uses measured ROS record endpoints. Valid, strictly increasing
image-header timestamps are affinely mapped between those endpoints. Only a
stream with every image header exactly zero uses ROS record cadence directly.
Mixed, missing, invalid, or unordered headers fail safely. No fixed frame rate
or interpolated frames are invented; duplicate front record times keep the
last frame.

IMU uses ROS database record time and preserves source order. Nanoseconds travel
as decimal strings; duplicate-time lookup selects the last sample at or before
the clock. Non-finite values are per-axis null gaps. The browser owns one
bag-relative clock, corrects camera drift at 100 ms, and clears/hides consumers
outside their measured coverage. Graph zoom changes the view, not the clock.
IMU JSON is capped at 64 MiB and validated row by row; the browser parses the
response stream and draws only a bounded set of points for the visible window,
preserving spikes and visible null gaps. Camera panes show buffering until the
first frame is decoded, then retain the last frame during seeks.

Video validation streams packet timestamps through ffprobe instead of collecting
the full packet list. Probe time limits scale with output size and remain bounded.
Worker control checks reuse its advisory-lock database session in short
transactions. Front-camera and IMU processors fetch bounded payloads with one
ordered SQLite query per stream. Readiness runs in the bounded catalog read pool
so database and mount checks do not block other HTTP requests.

Incomplete output stays in a contained job workspace. Validation precedes
publication; failed replacement preserves valid output. Files, manifests,
identity, and requested settings must agree before delivery. Artifact URLs bind
to a specific identity, including range requests, and cannot silently return a
replacement. Generated media and telemetry stay outside PostgreSQL and Git.

Persisted source hashes use `portable-stat-v1` to tolerate CIFS device/inode
differences between scan and worker contexts. Live source checks still compare
full device/inode/mode/size/mtime/ctime facts around reads. Derived CIFS timestamp
finalization is handled separately; it does not relax source immutability.

## HTTP and browser

`/api/v1` provides saved catalog, explicit rescan, recording detail, preparation,
processing overview/history, and job controls. Existing `/api/recordings/...`
routes still deliver identity-bound media and IMU; their older naming does not
make them unused. Schemas and routes in `api/` are the detailed API reference.

Default browser routes serve the React shell at `/`, `/processing`, and
`/recordings/{id}`. React uses `#/recordings`, `#/processing`, and `#/analysis/{id}`;
its integration is described in
[frontend architecture](../frontend/docs/architecture.md). Backend values are rendered as text and validated IDs/URLs, never arbitrary HTML. Errors are
sanitized; absolute source paths stay server-side. Polling, accessibility, and
media synchronization are covered by the JavaScript runtime tests.

## Storage and deployment

Source access is explicitly read-only, including SQLite. Source and derived
application paths do not overlap. When both use one NAS dataset, the writable
mount exposes only `Rosbag_Analyser_Cache`; all source walkers exclude that
reserved top-level name before traversal, inventory, and identity calculation.

The API listens on loopback behind the site's access boundary. PostgreSQL is
local. Low derived space rejects new work without deleting ready output;
source loss preserves saved catalog state. Mount, release, and schema checks
fail closed. Configuration, release procedures, and recovery belong in
[Operations](OPERATIONS.md).
