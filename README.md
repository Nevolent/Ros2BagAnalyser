# ROS 2 Bag Analyser

ROS 2 Bag Analyser is moving from a completed proof-of-concept into a V1
feedback prototype for robotics engineers. V1 will catalog recordings from a
read-only NAS archive, prepare reusable front-camera, top-down-camera, and IMU
outputs in one user workflow, show persistent processing activity, and provide
a synchronized browser review experience.

## Current status

The mentor-facing V0 is complete. Its accepted contracts, implementation
evidence, real-data acceptance, and post-V0 Building blocks 6–8 are frozen in
[docs/v0](docs/v0/INDEX.md).

V1 planning was approved on 2026-08-04. Building block 1, the backend
preparation and processing operations slice, was accepted on 2026-08-04.
Building block 2, the reference frontend integration slice, was implemented,
verified, and accepted on the same date. A separately approved corrective slice
then versioned the front-camera timing policy and hardened browser correction so
the preview follows smooth capture cadence while retaining measured ROS record
coverage. Approved moved-path corrections now keep retained missing history out
of ordinary catalog views and preserve compatible processed output across an
unambiguous folder move. Building block 3 was explicitly invoked on 2026-08-16.
Its repository-readiness phase is implemented and verified with
synthetic/disposable targets. On 2026-08-23 the user accepted all preceding
application and repository-readiness work as the working pre-overhaul baseline
and authorized its Git checkpoint and push.

The newer 2026-08-23 static frontend in [`archive/`](archive/index.html) is the
frozen visual/interaction source for Prompt 2A. The overhaul and its real
processing controls were reviewed and committed locally as `1c8871b`, followed
by read-only CIFS deployment compatibility in `dd28c42`. Controlled VM
preparation has created separate derived storage, local PostgreSQL roles, and a
read-only application-facing source bind. No authoritative source content has
been scanned or processed.

## V1 outcome

V1 is a limited-group NAS trial, not a public production service. It must let an
engineer:

1. browse recordings through their real archive-folder hierarchy;
2. distinguish readable and damaged source recordings;
3. select one or more recordings and choose **Prepare selected**;
4. see each required artifact move through a persistent serial processing queue;
5. inspect the current job, elapsed time, a truthful estimate when available,
   queued work, failures, and completed history;
6. open a prepared recording and review the front view, top view, and one of six
   raw IMU signals on the accepted shared timeline; and
7. reload or restart the service without losing catalog, queue, failure, or
   reusable-artifact state.

The browser presents one preparation action per recording, while the backend
retains three independently reusable artifact jobs:

- `front_preview`;
- `topdown_preview`;
- `imu_series`.

This keeps failures and retries precise and avoids regenerating compatible
output.

## System shape

V1 remains a modular monolith:

- one dependency-free browser frontend;
- one FastAPI application;
- one PostgreSQL database for catalog and processing metadata;
- one serial ROS-aware worker;
- one strictly read-only source archive; and
- one separate writable derived-data root.

The NAS trial is expected to run inside an Ubuntu 22.04 virtual machine on a
trusted internal network. Public exposure, distributed workers, Redis, and a
general telemetry platform are not part of V1.

## Non-negotiable safety

Original recordings are immutable inputs. The application must never modify,
repair, reindex, rename, move, delete, or write generated data beside a source.
Source SQLite databases are opened explicitly read-only and immutable where
compatible. Generated media and telemetry stay under the configured derived
root.

The frontend never receives absolute source paths and never reads source files
directly. Expensive ROS, video, and telemetry work remains outside HTTP route
handling.

## Active documents

- [PROJECT.md](PROJECT.md) defines the V1 users, product workflow, scope, and
  success criteria.
- [ARCHITECTURE.md](ARCHITECTURE.md) defines V1 system, API, storage,
  processing, timing, estimation, and deployment contracts.
- [ROADMAP.md](ROADMAP.md) defines the three V1 building blocks, order, and
  acceptance gates.
- [BUILDING_BLOCK_PROMPTS.md](BUILDING_BLOCK_PROMPTS.md) contains paste-ready,
  detailed implementation prompts for each block.
- [AGENTS.md](AGENTS.md) defines contribution, safety, approval, testing, and
  Git rules.
- [docs/v0](docs/v0/INDEX.md) preserves the completed V0 record.

## Current implementation

The repository retains the completed V0 processors and served frontend. Its
processors provide:

- bounded, immutable ROS image extraction and H.264 front previews whose image
  header cadence is affinely mapped to measured ROS record coverage;
- CSV-timed top-down preview generation;
- one schema-version-2 bundle containing six raw IMU axes;
- validated atomic artifact publication and identity-based reuse;
- one persistent serial job queue; and
- one browser-owned bag-relative clock with measured coverage and
  100-millisecond camera correction.

Building block 1 extends those capabilities with bounded recursive discovery,
durable catalog generations, three scan-time preparation targets per recording,
bulk preparation, aggregate output state, processing overview/history/retry,
worker availability, and historical estimates. Versioned JSON routes live
under `/api/v1`; the V0 routes remain available during transition.

Move reconciliation keeps private cache-identity anchors separate from the
recording's current physical path. A one-to-one move therefore retains the
recording, jobs, history, and exact compatible artifacts without copying or
rewriting derived files. Ambiguous matches remain separate and require review.

Building block 2 ports the user-authored `archive/` design into the served
dependency-free frontend. Recordings, Processing, and Analyzer routes now use
saved catalog, preparation, queue/history/retry, identity-bound media, and
schema-version-2 IMU data without mock recordings, previews, jobs, or timers.
Front-video correction keeps the accepted 100-millisecond threshold while
allowing only one automatic seek in flight and pausing correction during
buffering.

Prompt 2A updates that served frontend to the frozen 2026-08-23 reference,
removes Experiments/Files, adds selective preparation and Analyzer graph-window
interactions, and keeps all operational content API-backed. The 2026-08-24
Recordings review restores the reference's separate Recorded column from
`start_time_ns` and corrects only that page's visual interactions. Additive
migration `0007_job_controls.sql` adds durable
pause/resume/cancel state and stable mutable queue order without adding a
domain table. The single worker cooperatively acknowledges controls at safe
processor, validation, publication, and cleanup checkpoints; the Processing
view also exposes authoritative reorder, bulk cancel/retry, wall/active elapsed
time, and cumulative approximate queue estimates.

Building block 3 adds strict loopback deployment configuration, exact mount and
low-space admission checks, sanitized capability-aware health, release/source
identity preflight, safe logging, checksummed offline packaging, systemd/Nginx/
firewall templates, backup/restore/smoke/support tools, and operator/engineer
guides under [`deploy/`](deploy/README.md) and
[`docs/NAS_TRIAL_RUNBOOK.md`](docs/NAS_TRIAL_RUNBOOK.md). These assets are a
repository candidate, not evidence of a commissioned trial.

The existing local launcher remains the development baseline:

```bash
./dev start
./dev status
./dev logs
./dev rescan
./dev stop
```

Starting the application must not scan the archive or create processing work.
Rescanning remains explicit.

## Operational bounds

Catalog traversal and bulk preparation are validated configuration rather than
archive-specific constants. Defaults are:

| Environment variable | Default | Meaning |
|---|---:|---|
| `ROS_BAG_ANALYSER_CATALOG_MAX_DEPTH` | 8 | maximum physical folder depth |
| `ROS_BAG_ANALYSER_CATALOG_MAX_ENTRIES` | 100000 | maximum entries visited in one complete scan |
| `ROS_BAG_ANALYSER_CATALOG_MAX_DIRECTORIES` | 10000 | maximum directories visited |
| `ROS_BAG_ANALYSER_CATALOG_MAX_RECORDINGS` | 5000 | maximum recording candidates and saved response rows |
| `ROS_BAG_ANALYSER_CATALOG_MAX_DIRECTORY_ENTRIES` | 2000 | maximum direct entries in a navigation folder |
| `ROS_BAG_ANALYSER_CATALOG_MAX_RECORDING_ENTRIES` | 256 | maximum direct entries inspected inside one recording |
| `ROS_BAG_ANALYSER_PREPARE_MAX_RECORDINGS` | 100 | maximum unique IDs in one Prepare selected request |

All values must be positive. Exceeding a traversal bound makes that root scan
incomplete, so it cannot advance generation or mark saved recordings missing.

## Current implementation gate

Building block 3 repository readiness is accepted as part of the working
pre-overhaul baseline. Prompt 2A and the CIFS deployment correction are locally
committed and fully synthetically verified. Controlled live VM preparation is
in progress; release installation, authoritative-source acceptance, private
trial access, reboot persistence, and trial admission remain gated.

The established V1 sequence remains:

1. backend preparation and processing operations;
2. reference frontend integration; and
3. TrueNAS VM deployment and trial commissioning.

Prompt 2A is an approved corrective overhaul between repository readiness and
the remaining live commissioning phases. Gate 0, the exact live guest
change/rollback review, and the real-data annex are still required before any
VM/NAS or authoritative-source work.
