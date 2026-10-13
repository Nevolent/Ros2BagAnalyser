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
processors decode and transcode. Startup starts an addition-discovery monitor,
with its first check after 15 seconds; it does not migrate or provision models.
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
last successful catalog or mark unseen recordings missing. A successful full rescan
completes missing, failed or cancelled available outputs for all recordings. Scheduling and catalog updates
commit atomically; a scheduling error rolls both back. Valid compatible artifacts and
active jobs are reused, and unavailable inputs are skipped. Preparation admission still applies.
Component/target writes and output-state reads use PostgreSQL pipelines; ready and
active outputs avoid per-output savepoints. Storage admission is checked once per
bounded preparation batch and again by the worker before claiming work. Saved rescan
duration includes catalog validation and scheduling; completion is recorded afterward.

The API checks addition-only discovery every 15 seconds, even without a browser.
Page-load discovery shares the same in-flight operation in the catalog scan pool.
Checks pause during maintenance or full rescan; failures retry on a later check.
Discovery skips known recording
roots before enumerating their contents, and inspects only new paths. Unreadable or
incomplete new bags remain unsaved for a later check or full rescan. New folders
must have an unchanged direct-file inventory for 30 seconds, no nonempty SQLite
WAL/journal, and the same inventory after inspection. Observed changes reset the
quiet period. A copy paused longer than this period cannot be distinguished from
a finished copy; worker identity checks still protect publication. Restart clears
the observations. All new inventories are observed before inspecting individual bags,
so a slow earlier bag cannot postpone another folder's quiet period. An empty
discovery skips the catalog/queue write transaction. New records, targets and all available output jobs commit together
under the catalog/queue locks; admission or scheduling failure rolls the addition back.
Existing rows, targets, jobs and artifacts stay unchanged; the full-scan generation,
completion time and duration do not advance. Discovery can initialize targets at
generation zero. Known-path presence is retained without inspecting contents;
possible moves with matching saved fingerprints wait for full reconciliation.
Only a full rescan reconciles changes, moves and missing sources.

Six tables hold domain state: `recordings`, `source_components`, `artifacts`,
`jobs`, `catalog_state` and `preparation_targets`. Applied SQL migrations,
currently through `0014_comparable_estimates.sql`, remain part of the upgrade path.
Historical migration files stay unchanged. The runner skips the estimate constraint
in 0008, fully replaced by 0014, so replay preserves saved `recent_rate_v3` jobs.

Catalog and processing reads use saved projections, without source access per row.
Catalog lists also avoid opening every derived file: readiness reflects the last
validated saved artifact. Details, preparation, worker publication and delivery
retain artifact validation.
Each successful scan saves six preparation targets per recording. Planner or
configuration changes require an explicit rescan; the worker revalidates inputs.

The scan saves topic names, types and counts in `recordings.scan_details`.
Metadata uses PyYAML's native safe parser when available, with an event pass enforcing
the existing byte, depth, node and alias limits before construction; the bounded
Python parser remains the fallback.
Timestamp inspection uses a verified immutable SQLite descriptor without loading
payloads, bounded to two million messages per pass, a shared five-second query
budget and 256 Image/IMU topics.
The global pass reads the covering timestamp index first, avoiding random source-page
lookups. A sequential table-header pass collects bounded sensor timestamp lists and
sorts them in memory; evidence survives an interrupted sensor check.
Its raw results (including partial checks) persist separately in `scan_details` and
are reused when device, inode, mode, size, mtime, ctime, the 100-byte SQLite header
and timestamp policy/limits match. Schema and descriptor checks still run; metadata,
companions, health presentation and preparation targets are recomputed on every
full rescan. Moves can reuse timing when the physical database identity still matches;
cache misses, replacements and policy changes inspect timestamps again.
The timestamp policy version must advance when inspection semantics change.
A gap must be at least one second and twenty times the median of the first
1,024 positive intervals, with at least twenty intervals of cadence evidence.
Checks cover the bag and individual camera/IMU streams; the largest 24 gaps are
saved with internal relative locations; engineer-facing diagnostics use Unix time.
Incomplete checks are marked partial. Gap evidence
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

Analysis readiness excludes thumbnails. Any failed analysis output, including AI,
makes the recording Failed while preserving ready siblings. Unavailable front input
makes it Partially prepared when another analysis output is ready, and Failed
otherwise, after checking active work. Other state precedence is
processing, queued, ready, partially prepared, not planned. Ready requires a
validated front preview and AI description, with all available analysis outputs ready and
no active or failed analysis output. Any ready analysis output with other preparation still needed
is Partially prepared, when no output failed, including when a rescan changes a
camera target or adds an encoder target. Output failures retain their diagnostics
and Processing retry controls. Unavailable top-down, IMU and encoder inputs are optional;
Analysis can review available output independently.

The default pipeline is front preview, thumbnail strip, AI, top-down, IMU and encoders.
Reordering cannot run thumbnails before active front work, or AI before active
front/thumbnail jobs. Thumbnails first sample the validated front MP4 at six
evenly spaced positions. Without usable front video, other supported raw cameras
or a companion AVI provide fallback images, including a single usable frame.
The AVI fallback needs no CSV. Decoder subprocesses honor pause and cancellation.
Raw fallback uses two sequential immutable SQLite message-header scans selecting
six frames at approximate sevenths of the record-time span,
keeping the last message at duplicate timestamps. The middle frame is the default.
All six selections share the second scan; repeated selections decode once.
At most 256 candidate streams are inspected;
Ouster measurement images are excluded before camera validation. Payloads are bounded
and only up to four initial candidates per stream and the chosen frames are decoded.
Damaged samples are skipped while retaining even one usable image. Scans retain only stream
endpoints and six selections, checkpoint every 1,024 rows, and have a 30-second
budget between checkpoints; expiration reports `thumbnail_query_timeout`. No source index is changed.
A completed inspection with no usable camera or video frame is unavailable for that input identity;
it retains the attempt diagnostic without appearing as an actionable failure or queuing another
identical attempt. Changed inputs require an explicit rescan. Each tile retains aspect ratio
within 448 pixels per side; one to six tiles share a schema-2 horizontal PNG strip capped at 6 MiB.
The strip is validated with tile dimensions, timestamps, decoded content and a
SHA-256 digest before publication and delivery.
Unchanged detail/delivery image validation is cached against full file facts and manifest identity
in a bounded 10,000-entry cache; anchored path/manifest checks still run when validating artifacts.
Unchanged delivery reuses the validation cache. Identity-bound URLs use private
24-hour browser caching, so browsing and hover require one download per strip.
Identity binds recording/cache anchors, metadata, SQLite and optional AVI facts to
the fixed policy, independently of the front encoder. Thumbnail estimates use one
work unit. Historical migration 0013 retains its original front-based policy;
Full rescan saves current visual identities and retries missing or failed thumbnails,
and Prepare Selected fills missing output or retries failed/cancelled attempts.

AI descriptions read the saved strip through a validated, held descriptor, splitting
its exact pixels into one to six chronological PNG tiles rather than sampling video
again. Schema-2 JSON binds visual-source and thumbnail identities.
Qwen3-VL-2B-Instruct Q8_0 and the matching
F16 vision projector run offline through pinned llama.cpp CPU binaries, using the
application's Python environment. A job-owned server accepts one constrained JSON
completion over a private Unix socket; it exposes no TCP listener. The prompt and
formatter retain the three required bunker cues: gravel-like terrain, dark
curtains and artificial lighting. Four CPU inference threads are the default.

Validated JSON is published atomically and exposed in recording details and the saved catalog.
Inference errors leave existing artifacts intact. Historical migration 0012 retains
its original front-based policy; Full rescan selects the current shared-image policy,
preventing reuse of old model/sampling output. Prepare Selected reuses compatible
artifacts. Cancellation terminates inference, the server and decoders; pause
holds their process group at a checkpoint before publication. Generation has a
300-second active-time limit, excluding pauses. Model provisioning is explicit,
verified and separate from application startup and recording processing.

A PostgreSQL advisory lock permits one worker. Claim, insertion, reordering and
queued cancellation share a stable queue order. Durable pause/resume/cancel
requests take effect at safe processing and publication checkpoints. Worker
restart marks abandoned running or paused work interrupted; retry is explicit through
job controls, Prepare Selected or Full rescan.
The UI exposes cancellation; pause/resume remains available through the API.

Elapsed and active time come from persisted timestamps. Estimates use the ten
newest compatible artifact-backed successes, with at least two samples, excluding
paused time. `recent_rate_v3` requires samples within a factor of four of current
input units, then uses the 80th-percentile rate plus 15% headroom. AI and thumbnails
each use one fixed unit; other outputs retain input-byte units. Incomparable history
produces an unavailable estimate. Migration 0014 preserves historical predictions.
Queue estimates refresh together when a recording's first output
starts, then freeze across output handoffs. A prior v3 prediction survives when
sample artifacts disappear; older extrapolation methods are replaced or marked
unavailable before the first output starts. Running predictions remain frozen.

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
| Thumbnail | `thumbnail-v3:preview-or-camera:shared-six:side448:png-strip`; schema-2 PNG strip with one to six shared frames |
| Front preview | `front-preview-v8`; validated MP4 for the main supported raw CDR camera stream |
| Top-down preview | `topdown-preview-v2`; AVI frames timed by CSV Unix timestamps; H.264/yuv420p MP4 |
| AI description | `ai-description-v3`; schema-2 JSON with description and bunker boolean, tied to visual-source/thumbnail identities and fixed model/prompt policy |
| IMU | `imu-series-v2`; schema-2 JSON with three angular-velocity and three linear-acceleration axes |
| Encoders | `encoder-series-v1`; schema-2 JSON with six RPM channels in FL, FR, ML, MR, RL, RR order |

Front discovery accepts nonempty CDR `sensor_msgs/msg/Image` streams whose first
image uses `rgb8`, `bgr8`, `rgba8` or `bgra8`. Named camera streams also support
`mono8` and `mono16`. The KuupKulgur `front_camera/actually_raw_image` topic supports
CDR `std_msgs/msg/UInt16MultiArray` with exactly two labelled `height`/`width`
dimensions, packed strides and a validated offset and payload. Arrays are grayscale
intensities, never inferred colour/Bayer images. Sixteen-bit previews use the upper
eight bits with a fixed 0–65535 range, preserving brightness between frames.
Alpha is discarded for video previews. Other encodings and Ouster measurement images are excluded
before camera validation and produce no stream-failure diagnostics. Every frame
of an eligible stream must satisfy the image and timing contracts; encodings cannot change midstream.
Known ceiling, top, rear, back and downward views are excluded from front inputs.
Names with a `front` component (including camelCase) come first, then message count
descending and topic name ascending. Only the first eligible camera stream is processed,
timed and validated before atomic publication. Stream URLs use
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

New thumbnail, description and telemetry manifests bind validated bytes with SHA-256.
Publication flushes owned output and refreshes its final file facts only after verifying
that digest. Delivery may accept CIFS device/inode/timestamp changes only when the held
file still matches the saved content digest; hash checks are cached against complete live
file facts in a bounded 10,000-entry cache per artifact store, retaining keys rather
than file contents so repeated archive scans avoid rereading unchanged telemetry.
Legacy manifests retain strict file-fact checks;
rejected legacy artifacts require explicit regeneration, never automatic repair.

Processors use bounded payload reads and one ordered SQLite query per stream.
The query sorts only message IDs, timestamps and lengths, then reads selected
payloads by primary key; large images never enter the sort buffer. Cancellation and
pause checkpoints also run during the initial header scan/sort. Telemetry serializes
each complete sample once, preserving the existing JSON bytes and null-gap policy.
Video validation streams packet timestamps through ffprobe with bounded,
size-dependent timeouts. Worker control checks reuse its advisory-lock session
in short transactions. Readiness runs in the bounded catalog pool. Low derived
capacity rejects new work without deleting ready output; source loss preserves
saved catalog state. Mount, release and schema checks fail closed.

## Timing and playback

Front coverage uses ROS record endpoints. Strictly increasing valid image-header
timestamps map affinely between those endpoints. Only streams whose headers are
all exactly zero use ROS record cadence directly. Headerless UInt16 camera arrays
also use record cadence, with distinct timing policy and provenance in the manifest.
Mixed, missing, invalid or
unordered headers fail. Duplicate front record times keep the last frame;
no fixed frame rate or interpolated frames are invented.

IMU and encoder series use database record time and preserve source order. Nanoseconds are decimal
strings; lookup selects the last sample at or before the clock, including duplicate
times. Non-finite values are per-channel null gaps. JSON is capped at 256 MiB and
validated row by row. The browser streams parsing and reduces visible points while
preserving spikes and gaps; large sample bundles stay outside subscribed UI state.
Observed timestamp pauses meeting the catalog cadence rule break displayed telemetry
traces and clear readouts until samples resume; straight lines do not bridge them.
For encoders only, brief extreme excursions become trace gaps and inspectable markers,
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
of selection, with the scale label in a separate left lane. Angular velocity,
acceleration and RPM scales fit the visible selected samples, including interpolated
view boundaries, with 4% range padding and five evenly spaced ticks. Constant
signals use 1% magnitude padding (minimum 0.001). Selected traces share one axis;
multi-channel traces use modest opacity. Encoder traces share one RPM axis in the six-wheel
view; individual wheel selection uses the same samples. Without IMU, the clock
uses recording metadata Unix time; a missing origin shows unavailable timestamps.
Engineers see Unix timestamps (seconds since the epoch, with milliseconds), never
elapsed recording positions. Durations and internal clock offsets remain in
seconds. Window arrows pan by 20%
of the current span without seeking or changing playback; spike activation seeks
to its recorded sample and preserves playback.
Playback follows the cursor while it is visible; panning or zooming away keeps
the chosen window until the clock enters it or an explicit seek brings it back.

The dense SVG trace is memoized and composited separately from the HTML cursor.
The cursor uses fractional transforms each animation frame; React readouts and
camera drift checks update at up to 20 Hz. Pointer seeks are frame-coalesced.
Cameras show buffering until a frame is decoded, then retain that frame during
seeks. Each decoder finishes an in-flight seek before taking the latest request.
Automatic correction waits 500 ms after seeking; explicit seeks bypass this wait.
An eight-second no-progress watchdog works even while paused. Stalls and load
failures share three bounded reload attempts, then offer a manual Retry control.
Buffer advances refresh the watchdog's progress deadline. Recovery retains the
shared clock and clears that camera's diagnostic. Navigation
disposes media, listeners, observers, timers and animation frames.

## Browser and HTTP

React source lives in `frontend/`. `WorkspaceProvider` retains small session
settings across routes; playback stops on unmount. The default service calls the
real API. Explicit `?synthetic=1` selects in-memory fixtures and never calls it;
the synthetic launcher serves only loopback assets without backend services.

`api-types.ts` defines contracts, `api-mapping.ts` maps domain models and
`api-workspace.ts` owns polling and commands. Route cleanup aborts reads and
timers. Mutations invalidate older reads and are never replayed automatically.
Initial loading is separate from cached refresh. Recording details and cameras render
before telemetry downloads; IMU and encoder loads run concurrently. JSON requests
have a 30-second deadline and telemetry transfers a 60-second deadline, including
bodies. Preparation/retry keeps an
empty queue loading until the request and refresh finish, including navigation;
counts come from server results. Errors restore dismissed data and appear in
the dismissible shell message.

Processing follows all overview/list cursors with cycle detection, deduplication
and abort/version guards. A failed page preserves the last complete snapshot.
Successful siblings stay with failed recordings; retries submit only failed job
IDs. History groups latest successful outputs for recordings without failures.
Output counts
offer hover/focus lists of names; history runtimes and sizes list each output's
duration and bytes. Triggers fill their cells. Desktop row hover/focus advances
the thumbnail immediately, then every 750 ms; phones and reduced motion stay still.
Move to top
stably promotes selected recording groups under the queue lock, preserving output
order and unselected group order. Legacy API earlier/later controls remain supported.

`/api/v1` provides catalog, explicit rescan, details, preparation and job controls.
`POST /api/v1/catalog/discover` adds new recordings without making catalog reads
touch sources. The browser requests it once per page load, independently of polling
and route changes, without loading text or blocking controls. The bottom-left
**Full rescan** button appears only in Recordings, starts background work and
spins while the server is scanning.
Browser starts use `POST /api/v1/catalog/rescan?background=true` (202); the default
POST remains a completion-waiting API for scripts. Both API versions share and
shield one operation from request cancellation. `GET /api/v1/catalog/rescan/status`
is polled on every route, including Analysis; reloads and other browsers see the
server's running state. PostgreSQL session advisory locks serialize source scans
across API processes and expose active full rescans independently of discovery.
They release on server/session loss, allowing explicit retry; interrupted work
does not resume automatically. The click dismisses its hover label and background;
pointer reentry restores the button cue and **Scanning archive** label. Away from
it, only the retry icon spins.
`/api/recordings/...` delivers identity-bound media, IMU and encoder series. React routes are
`#/recordings`, `#/processing` and `#/analysis/{id}`; the server also accepts
`/`, `/processing` and `/recordings/{id}`. API schemas live in `api/`.

Backend text is rendered as text, with validated IDs and URLs. Errors are
sanitized and absolute source paths stay server-side. The API listens on loopback
behind the site's access boundary; PostgreSQL is local. Development and component
conventions are in [Development](DEVELOPMENT.md).
