# Development

Use Ubuntu 22.04 / WSL and Python 3.10 to match the VM runtime.
Processing also requires ROS 2 Humble, PostgreSQL and FFmpeg/ffprobe.

## Backend setup

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Reuse a working `.venv`. `requirements.lock` pins development dependencies;
`deploy/` owns runtime and build inputs. Update both when changing dependencies.

The local launcher reads mode-0600/0400 private files:

- `~/.config/rosbag-analyser/environment`: separate source/derived roots and
  optional sensor-topic preferences.
- `~/.config/rosbag-analyser/database.env`: database password and optional
  host, user, database name and port.

The local service wrapper reuses `experiments/qwen3-vl/.venv` and its downloaded
model when present. Run that experiment's `setup.sh` to provision it. Elsewhere,
configure `ROS_BAG_ANALYSER_DESCRIPTION_PYTHON` (the model environment's Python)
and `ROS_BAG_ANALYSER_DESCRIPTION_MODEL_ROOT` (the pinned model directory).
The API/ROS environment needs no Torch or Transformers; missing inference setup
fails only description jobs and preserves prepared media. Inference is offline.
Keep model weights and generated descriptions outside Git. Model settings take
effect after a local service restart; migrate before using the new output kind.

The default database host is the Windows host. Override file locations with
`ROS_BAG_ANALYSER_SETTINGS_FILE` and `ROS_BAG_ANALYSER_DATABASE_SECRET_FILE`.
Keep these files out of Git.

```bash
./dev check
./dev open real
./dev status
./dev logs
./dev rescan          # Explicit source scan; startup does not scan
./dev stop
./dev install        # Install local Windows shortcuts
```

`scripts/rosbag-analyser-service` manages the local services. The Windows
shortcut opens Chrome and retains startup output on failure. Other environments
can use the installed `rosbag-analyser`, `rosbag-analyser-worker` and
`rosbag-analyser-migrate` commands with explicit settings. Migrate a development
database before starting it. Configuration validation lives in `config.py`.

The launcher uses bounded `/health/ready` requests, restarts an unresponsive
managed API and starts a missing worker. Startup waits up to 20 seconds for both
processes and API readiness; failure prints their status and recent logs.
Opening or starting checks backend Python/SQL files, launch configuration and
dependency manifests against both process start markers. Changes reload the API
and worker together, after the worker finishes its current job; it is never
force-killed. Packaged frontend-only changes reload just the API. This does not
rescan sources or retry failed jobs.

Encoder support requires migration `0011_encoder_series.sql`, followed by an
explicit rescan to save the new preparation targets. Prepare Selected reuses
existing compatible output and queues missing encoder work. The optional
`ROS_BAG_ANALYSER_ENCODER_TOPIC` chooses a specific custom encoder stream; empty
selects one unique supported stream automatically. Restart services after
configuration changes, then rescan.

Colour-camera discovery and default selection use `front-preview-v6`. After
updating an existing installation, explicitly rescan and prepare recordings to
save current targets and generate bundles with the new eligibility policy.

## Frontend

The React/TypeScript source is in `frontend/`. Use Node.js 22.12+ or 24:

```bash
cd frontend
npm ci
npm run dev
# http://127.0.0.1:5173
```

Vite proxies `/api`, including media ranges, to `http://127.0.0.1:8000`.
Set `ROS_BAG_API_TARGET` to use another backend. An unavailable API shows an
error; the application never falls back to simulated data.

To run the committed build without backend infrastructure, from the repository root:

```bash
./dev open synthetic
# http://127.0.0.1:4173/?synthetic=1
./dev stop synthetic
```

`?synthetic=1` also works in Vite. It uses in-memory recordings, jobs and shared
camera/IMU/encoder fixtures; reloading resets it. `?demo=1` selects fixed visual fixtures
in the Vite development server only. Neither mode verifies real processing.

From `frontend/`, build the production assets before committing a UI change:

```bash
npm run build:package
```

This typechecks the source and builds into `src/rosbag_analyser/web/react/`.
Commit the source and packaged assets together. The VM serves these files without
Node.js. `npm run build` builds to ignored `dist/`; `npm run preview` serves
that local build with the same API proxy.

### Components and styling

Reuse the shared components in `frontend/src/components/`:

| Purpose | Components |
| --- | --- |
| Page and panels | `Page`, `Workspace`, `SidePanel` |
| Tables | `TablePanel`, `TableBody`, `EmptyState`, `SortableHeader` |
| Inputs and actions | `Button`, `Tabs`, `SearchField`, `FilterMenu`, `Checkbox` |
| Overlays and status | `Dialog`, `Popover`, `StatusBadge` |
| Panel scrolling | `ScrollArea` |

Use semantic tokens from `src/styles/theme.css` for colors, spacing and control
sizes. Put shared layout in `app.css` or `table.css`, and feature rules in their
own stylesheets. Utility classes are a fixed stylesheet, not a generated
Tailwind build. Dark mode uses the document root's `dark` class.

Use buttons for actions, links for navigation, accessible names and visible
focus. Preserve dialog focus restoration, keyboard equivalents and reduced
motion. Loading and empty states use muted text; background refresh never
covers cached content. Restore optimistically dismissed jobs if a request fails.
Sorting changes presentation only, not queue order. Calendar timestamps use
`formatDateTime` (Europe/Tallinn); timeline timestamps keep their own units.

## Verification

From the repository root:

```bash
.venv/bin/python -m pytest -q tests/unit tests/api
node --test tests/js/test_*.mjs
```

Frontend checks, from `frontend/`:

```bash
npx playwright install chromium
npm test
npm run build
npm run format:check
```

Browser tests use synthetic API responses and media. `CHROMIUM_PATH` selects an
installed browser; `PLAYWRIGHT_BASE_URL` selects an existing Vite server.
Inspect affected loading, error, keyboard, responsive and playback behavior.
For visual comparisons, run `npm run visual:capture` before a change, then
`npm run visual:compare` with the same browser and OS. Captures stay in ignored
`artifacts/visual/`; review differences before replacing a baseline.

| Additional suite | Prerequisite |
| --- | --- |
| `tests/ros/` | Source Humble; set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` |
| `tests/postgres/` | Disposable `ROS_BAG_ANALYSER_TEST_DATABASE_URL`, `ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET=1`, and `--require-postgres` |
| `tests/deployment/` | Disposable proxy/tools; see fixtures |
| `tests/real_archive/` | `RUN_REAL_ARCHIVE_TESTS=1`, source settings and disposable database; define a bounded target first |

The PostgreSQL suite resets its target schema. Routine tests use synthetic
archives and temporary output. A skipped integration suite is not a passing
integration check. VM procedures are in [Operations](OPERATIONS.md).
