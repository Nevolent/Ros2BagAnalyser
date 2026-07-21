# ROS 2 Bag Analyser — Project Definition

**Status:** Building block 1 completed and user-accepted

**Repository baseline:** Completed archive catalog vertical slice

**Initial environment:** Ubuntu 22.04 under WSL2, ROS 2 Humble

**Development archive:** `/mnt/d/Rosbags`

## 1. Purpose

ROS 2 Bag Analyser will provide a simple web interface for reviewing rover
recording runs.

The immediate goal is a credible V0 for a mentor demonstration. V0 is not a
complete robotics-analysis platform. It must prove that the application can
safely catalog the current archive, generate reusable browser previews, and
synchronize camera and telemetry data on one timeline.

The product must remain understandable and adaptable while later requirements
are uncertain. Technical implementation decisions are owned by
`ARCHITECTURE.md`; delivery order and executable acceptance gates are owned by
`ROADMAP.md`.

## 2. V0 product experience

The V0 user journey is:

1. Open the archive page and scan the configured archive.
2. See one table row for each of the six recording runs.
3. Compare useful metadata and distinguish readable data from damaged or
   incomplete data.
4. Open a recording detail view with metadata and diagnostics.
5. Generate or reuse a front-camera preview for a healthy run.
6. View its separately recorded top-down camera using the CSV capture times.
7. Play, pause, and seek both cameras with one global timeline.
8. View one IMU angular-velocity graph following the same timeline.
9. Reload or restart and reuse compatible completed output.
10. Open the damaged run and receive a clear diagnosis rather than a crash.

The archive table is for discovery and comparison. The recording detail view is
for media review. V0 needs clear loading, unavailable, processing, ready, and
failure feedback, but it does not need a general workflow or operations console.

Source condition and generated-output availability are separate concerns. A run
may have an unreadable ROS database while its AVI and CSV companions remain
independently readable.

## 3. Actual development data

### 3.1 Archive structure

The inspected archive is available at:

```text
Windows: D:\Rosbags
WSL:     /mnt/d/Rosbags
```

It contains:

- 6 recording directories;
- 24 files;
- approximately 106.604 GiB in total;
- one `metadata.yaml` per recording;
- one ROS 2 SQLite `.db3` file per recording;
- one external-camera `.avi` file per recording;
- one external-camera timestamp `.csv` file per recording.

All metadata files describe ROS 2 SQLite3 storage, CDR serialization, metadata
format version 5, one database file, and no bag compression.

V0 supports this known SQLite3 layout. MCAP, ROS 1, compressed bags, and general
split-bag support are later compatibility work.

### 3.2 Readable ROS recordings

Five databases are readable:

| Recording | Duration | Topics | Messages | Front frames | ROS database size |
|---|---:|---:|---:|---:|---:|
| Figure-eight | 152.969 s | 20 | 162,684 | 3,051 | 10.043 GiB |
| PE course, slow | 758.739 s | 9 | 135,229 | 15,171 | 39.151 GiB |
| PE course, fast | 618.915 s | 9 | 110,503 | 12,376 | 31.938 GiB |
| Ceiling-lights run | 145.917 s | 20 | 153,038 | 2,884 | 9.394 GiB |
| Freeform run | 187.196 s | 20 | 197,427 | 3,690 | 12.099 GiB |

These labels describe the inspected recordings. Application logic must use
discovered identities and metadata rather than hard-coded labels.

### 3.3 Damaged ROS database

The following database is truncated and cannot be queried reliably:

```text
2025_11_04_plain_figure8_spotlight_0.db3
```

Observed size information:

- actual file size: `3,813,700,272` bytes;
- size implied by its SQLite header: `9,990,610,944` bytes;
- missing data: `6,176,910,672` bytes;
- approximately 38.17% of the expected database is present.

SQLite reports:

```text
database disk image is malformed (11)
```

The application must catalog this recording and report the ROS failure clearly.
It must never attempt to repair, reindex, truncate, or otherwise change it.

The associated external AVI and CSV are independently readable. V0 is not
required to reconstruct a complete synchronized ROS review session for this
damaged recording.

### 3.4 Front camera

The readable bags contain the preferred front-camera topic:

```text
/kuupkulgur_v1/sensors/front_camera/image_raw
```

Observed message properties:

- message type: `sensor_msgs/msg/Image`;
- dimensions: 1280 × 720;
- encoding: `bgr8`;
- approximate frequency: 20 Hz;
- uncompressed bytes per frame: 2,764,800;
- approximate raw image throughput: 55.3 MB/s.

Front-camera data dominates the database size. Preview generation is expensive,
must not block ordinary web requests, and must produce reusable derived media.
The preferred V0 topic is configurable even though the current archive uses one
known topic name.

### 3.5 External top-down camera

Every recording directory contains an AVI and timestamp CSV pair.

Observed AVI properties:

- all six files decode successfully;
- resolution: 2312 × 1736;
- codec: MPEG-4 Part 2/Xvid;
- nominal container rate: 30 fps.

Observed CSV properties:

- columns include `unix_timestamp` and `human_timestamp`;
- each CSV contains exactly one timestamp row per decoded video frame;
- timestamps are the authoritative timing source;
- observed capture frequency is approximately 3.39–3.73 frames per second.

The nominal AVI rate is not the capture timing. Playing the source directly at
30 fps runs approximately eight to nine times faster than the CSV timestamps
describe.

Relative to the ROS bag starts, sidecar recordings begin approximately
1.38–3.00 seconds later. Their ends range from approximately 3.36 seconds before
the bag end to 36.53 seconds after it.

V0 must represent this partial coverage honestly. It must not imply that a
top-down frame exists outside the stream's measured time range.

### 3.6 Telemetry

A standard `sensor_msgs/msg/Imu` stream is the preferred V0 telemetry source. It
is present in the archive metadata and is typically recorded at roughly 100 Hz
in readable bags.

The initial graph uses the configured angular-velocity component expected to be
`angular_velocity.z`. The rover coordinate convention must be verified before
the interface calls it "yaw rate." Until then, the exact label is:

```text
IMU angular_velocity.z (rad/s)
```

Other observed data includes `geometry_msgs/msg/Twist`, custom encoder and EPS
messages, and Ouster data in four of the five readable full recordings.

Custom packages such as `kuupkulgur_msgs`, `ouster_sensor_msgs`, and
`rosbridge_msgs` are not currently available in the development environment.
V0 must not depend on them.

Ouster data is unsuitable for the first universal graph because it is absent
from the PE course recordings and its headers use a different clock domain.

### 3.7 ROS database access constraints

The inspected SQLite bags use the ROS 2 Humble schema version 3. They contain an
index on message timestamp but no combined topic-and-timestamp index.
Topic-specific extraction may therefore scan substantial source data.

The application must never add an index to an original database. Any future
derived index belongs in separate derived storage.

## 4. Product timing and synchronization rules

V0 uses ROS database record timestamps as the shared ROS time source. User-facing
time is elapsed from the bag start. Header timestamps may be retained for
diagnostics but never silently replace the record clock.

For the top-down camera, CSV Unix timestamps are authoritative. The nominal AVI
frame rate must not control synchronization. The application must validate the
timestamp sequence and its one-to-one relationship with decoded frames before
presenting synchronized media.

The global timeline covers the ROS bag duration and owns play, pause, current
time, and seeking for both cameras and the telemetry cursor. Each stream reports
its actual coverage. Outside coverage, the interface shows an explicit
outside-coverage state rather than freezing a boundary frame as if data existed.

Backend precision, media mapping, drift correction, and derived-media strategy
are architecture responsibilities. V0 acceptance must still demonstrate that
repeated play, pause, and seek operations remain aligned without accumulating a
visible offset.

## 5. V0 functional requirements

### 5.1 Archive catalog

- Scan one configurable archive root.
- Treat each recording directory as one catalog entry.
- Parse `metadata.yaml` and inventory the expected source companions read-only.
- Perform bounded checks sufficient to identify the known truncated database.
- Show all six runs without duplicates after repeated scans.
- Show useful metadata, source-component availability, and clear diagnostics.
- Keep scanning separate from preview and telemetry generation.
- Preserve the association to compatible completed output across reloads,
  restarts, and unchanged rescans.

The table shows at least the recording name, start time, duration, total source
size, storage format, topic count where available, and source health. The detail
view shows component information and generated-output availability.

### 5.2 Front-camera preview

- Detect the configured preferred topic and verify the standard image type.
- Safely support the observed `bgr8` data and reject incompatible input clearly.
- Generate browser-compatible, seekable media outside the source archive.
- Keep expensive generation outside ordinary HTTP request handling.
- Publish only validated completed output and reuse it when its relevant inputs
  and output settings still match.
- Show the preview in the detail view under the global timeline.

### 5.3 Top-down camera

- Pair the AVI and CSV belonging to the selected recording.
- Validate required timestamps, monotonic ordering, video decodability, and
  frame-count agreement without modifying either source.
- Use CSV capture time rather than the nominal AVI frame rate.
- Produce or expose browser-compatible media with correct elapsed timing.
- Reuse compatible completed output.
- Show measured coverage and explicit outside-coverage periods.
- Respond to the same global timeline as the front camera.

### 5.4 Synchronized review

- Provide one visible global play, pause, and seek control.
- Show elapsed and total bag time.
- Seek every available view when the user scrubs.
- Keep both cameras aligned during continuous playback and after seeking.
- Move the telemetry cursor and current value with the same time.
- Never manufacture coverage or hide synchronization uncertainty.

### 5.5 Basic IMU graph

- Extract one configured component from a standard `sensor_msgs/msg/Imu` topic.
- Align samples using ROS record time relative to the bag start.
- Preserve the time domain and important extrema when reducing data for the
  browser.
- Display the exact signal identity, units, current value, and timeline cursor.
- Reuse compatible extracted data and report missing or unsupported telemetry.

### 5.6 Processing and reuse behavior

- Normal browsing and API requests remain responsive while expensive work runs.
- Repeated requests for the same compatible result do not duplicate expensive
  active work or completed output.
- Incomplete or invalid output never appears ready.
- A failed or interrupted operation has a clear result and can be requested
  again safely.
- Completed compatible output remains reusable after page reload and application
  restart.
- Implementation-specific storage, worker, status, and publication mechanics are
  defined in `ARCHITECTURE.md`.

## 6. V0 acceptance profile

V0 must demonstrate:

1. A real scan of all six recording directories, with five readable ROS bags
   and the known damaged database identified correctly.
2. Metadata and diagnostics for healthy and damaged runs without modifying the
   archive.
3. The complete front-camera, top-down, global-timeline, and IMU workflow on one
   short healthy recording.
4. One final opt-in scale acceptance of the same complete workflow on one long
   healthy recording, establishing that processing and browser use remain
   practical at the current data scale. This is not a routine development or
   automated test.
5. Reuse of compatible completed previews and telemetry after reload or restart.
6. Honest unavailable and failure states, including the damaged run.
7. Before-and-after evidence that the source archive is unchanged.

`ROADMAP.md` owns the exact demonstration sequence, per-block definitions of
done, automated verification, and review gates.

## 7. Explicitly outside V0

V0 does not include:

- authentication, users, roles, or permissions;
- annotations or collaborative review;
- browser uploads or automatic archive watching;
- bag repair or corrupted-database recovery;
- LiDAR, point-cloud, GPS, or map visualization;
- arbitrary custom message decoding;
- multiple telemetry dashboards or user-defined graphs;
- embedded PlotJuggler;
- arbitrary camera or topic configuration in the user interface;
- ROS 1, MCAP, compressed, or general split-bag support;
- Redis, distributed workers, or production-scale scheduling;
- cloud object storage;
- production deployment or orchestration;
- automated artifact retention, backup, or disaster recovery.

These features require separate product decisions and roadmap approval after V0
demonstrates the core review workflow.

## 8. Safety and integrity guarantees

- Original recordings are immutable inputs.
- Damaged bags are reported clearly and are never repaired or rewritten.
- Generated data is stored separately from source recordings.
- Partial or invalid output is never presented as complete.
- Large source or generated files, credentials, and secrets are never committed.

`ARCHITECTURE.md` owns the technical controls behind these guarantees, and
`AGENTS.md` owns the rules contributors must follow while working with data.
