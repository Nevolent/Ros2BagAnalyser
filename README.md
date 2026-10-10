# ROS 2 Bag Analyser

Browse ROS 2 recordings, prepare camera previews, IMU and wheel encoder data, and review them
on a shared timeline. The web interface is called **Tectrace**.

Original recordings stay read-only. PostgreSQL stores the catalog and job queue;
a serial worker writes validated thumbnails, previews, AI descriptions and telemetry to separate storage.

## Use the application

1. Find a recording in **Recordings**.
2. Choose **Prepare Selected** and follow the work in **Processing**.
3. Open **Analysis** to review cameras, IMU and six wheel RPM traces.

See [Usage](docs/USAGE.md) for controls, status meanings and supported formats.

## Run locally

On Ubuntu 22.04 / WSL, with the project environment configured:

```bash
./dev open real        # Local API and worker
./dev open synthetic   # In-memory demo; no ROS or database needed
```

For setup, frontend development and tests, see [Development](docs/DEVELOPMENT.md).
Processing requires Python 3.10, ROS 2 Humble, PostgreSQL and FFmpeg.
AI descriptions use the pinned Qwen3-VL-2B Q8 CPU runtime through llama.cpp;
provision it with `scripts/setup-model setup` as described in Development. Frontend
development uses Node.js; the committed browser build needs no Node.js on the VM.

## Deploy to the VM

From the project root in WSL, deploy the committed, pushed revision to the configured VM:

```bash
./vm deploy
```

See [Operations](docs/OPERATIONS.md#deploy-a-commit) for prerequisites, migrations,
model setup and recovery.

## Project layout

| Path | Contents |
| --- | --- |
| `src/rosbag_analyser/` | API, catalog, processing, persistence and packaged browser assets |
| `frontend/` | React and TypeScript source |
| `tests/` | Backend, integration and shared JavaScript tests |
| `deploy/`, `vm`, `deploy-vm` | Release tooling, configuration templates and VM commands |
| `dev`, `scripts/`, `support/` | Local launchers and Windows shortcuts |
| `tools/` | Diagnostics and development utilities |
| `docs/` | Usage, development, architecture and operations |

[Architecture](docs/ARCHITECTURE.md) describes data and timing contracts.
[Operations](docs/OPERATIONS.md) covers deployment, diagnostics and recovery.
[AGENTS.md](AGENTS.md) contains contributor instructions.
