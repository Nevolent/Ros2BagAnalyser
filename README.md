# ROS 2 Bag Analyser

Browse ROS 2 recordings, prepare camera previews and IMU data, and review them
on a shared timeline. The web interface is called **Tectrace**.

Original recordings stay read-only. PostgreSQL stores the catalog and job queue;
a serial worker writes validated previews and telemetry to separate storage.

## Use the application

1. Find a recording in **Recordings**.
2. Choose **Prepare Selected** and follow the work in **Processing**.
3. Open **Analysis** to review cameras and IMU data.

See [Usage](docs/USAGE.md) for controls, status meanings and supported formats.

## Run locally

On Ubuntu 22.04 / WSL, with the project environment configured:

```bash
./dev open real        # Local API and worker
./dev open synthetic   # In-memory demo; no ROS or database needed
```

For setup, frontend development and tests, see [Development](docs/DEVELOPMENT.md).
Processing requires Python 3.10, ROS 2 Humble, PostgreSQL and FFmpeg. Frontend
development uses Node.js; the committed browser build needs no Node.js on the VM.

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
