# ROS 2 Bag Analyser

A browser application for robotics engineers to find ROS 2 recordings, prepare
reusable camera previews and IMU data, and review them on a shared timeline.
The interface also uses the **Tech Trace** name.

## Where the project stands

The application is deployed on the VM and working, as confirmed by the project
owner on 2026-09-19. Cataloguing, processing, persistent job controls, artifact
reuse, and synchronized review are implemented. The immediate priority is
finishing the frontend for everyday engineering use.

This is an engineering product under active development. The old V0/V1
building-block workflow has been retired. Current priorities are in the
[roadmap](docs/ROADMAP.md); old plans are [historical backups](docs/history/README.md).
This repository cleanup did not inspect the live VM or certify its current
access, backup, or recovery configuration.

## Engineer workflow

1. Browse or search the saved **Recordings** catalog.
2. Select recordings and choose **Prepare selected**, selecting the outputs needed.
3. Follow work in **Processing**, with cancel, reorder, and retry.
4. Open a prepared recording in **Analyzer** to review cameras and six raw IMU axes.

Preparation reuses compatible output. Originals stay read-only; generated data
lives in separate storage. See the [engineer guide](docs/ENGINEER_GUIDE.md) for
states, controls, and current limitations.

## Work on the frontend

Preview the served application with synthetic data, without ROS or PostgreSQL:

```bash
python3 tools/serve_frontend_mock.py
# Open http://127.0.0.1:4173/?mock=all-ready
```

The React UI in `frontend/` is now the default served application and uses the
real `/api` backend in production. The synthetic archive remains available only
through Vite development mode for local UI work. See [frontend setup](frontend/README.md).

```bash
./dev start
# Open http://127.0.0.1:8000
```

The production bundle is committed under `src/rosbag_analyser/web/react/` so
Python releases serve the same tested React build without Node on the VM.

## VM workflow

```bash
./vm status                  # Bring service/release facts back to this PC
./vm deploy --push           # Push an existing commit and deploy it
./vm run tools/diagnostics/runtime_info.py
```

Diagnostics return private reports to ignored `.vm-reports/` without requiring
a release. See [Operations](docs/OPERATIONS.md) for source checks and custom scripts.

## Repository map

| Location | Purpose |
| --- | --- |
| `src/rosbag_analyser/` | API, catalog, persistence, processors, worker, and served frontend |
| `frontend/` | React source and local Vite development app; React is also the served default UI |
| `tests/` | Application, browser, database, ROS, and deployment verification |
| `vm`, `deploy/`, `deploy-vm` | VM commands, release tooling, configuration examples, and service templates |
| `dev`, `scripts/`, `support/windows/` | Existing local development launcher and optional Windows shortcut |
| `tools/` | Frontend preview and VM diagnostic helpers |
| `docs/` | Current guidance, with old documents bundled under `history/` |

## Documentation

- [Development](docs/DEVELOPMENT.md): setup, local workflows, and tests.
- [Architecture](docs/ARCHITECTURE.md): component boundaries, data, and timing.
- [Operations](docs/OPERATIONS.md): VM layout, deployment, diagnostics, and recovery.
- [Roadmap](docs/ROADMAP.md): next priorities and release readiness.
- [AGENTS.md](AGENTS.md): concise contributor instructions.
