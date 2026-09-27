# Development

The packaged UI in `src/rosbag_analyser/web/react/` is built from `frontend/`
using React, TypeScript and Vite. Run `npm ci && npm run dev` from that folder:
Vite uses port 5173 and proxies `/api` to port 8000. Override
`ROS_BAG_API_TARGET` for a different backend. Use Node
22.12+ or 24. See [frontend development](../frontend/README.md) for its explicit
visual demo, build, browser tests and visual comparison commands. Copy a tested
build into the packaged directory before committing frontend changes.

## Python setup

For a new environment matching the VM's Python 3.10 baseline:

```bash
python3.10 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
```

Reuse an existing working `.venv`. `requirements.lock` pins development
packages; `deploy/` owns VM runtime/build inputs. Update both deliberately when
changing dependencies. Full processing also requires ROS 2 Humble and
FFmpeg/ffprobe.

## Frontend without infrastructure

```bash
./dev open synthetic
# http://127.0.0.1:4173/?synthetic=1
./dev stop synthetic
```

This serves the same packaged frontend with over 500 in-memory recordings,
failures, history, a timed queue, and shared camera/IMU visual fixtures. No local
backend configuration, ROS, PostgreSQL, or Node is needed. Reloading resets the
simulation; it does not verify ROS processing or real camera timing. The real
app and Vite also accept `?synthetic=1`; omitting it selects the real API and
never falls back to simulated data. Both modes are maintained on `main`.

## Full local application

The existing WSL/Windows launcher remains supported:

```bash
./dev check
./dev start
./dev open real
./dev install # two local Windows shortcuts; existing VM launchers are untouched
./dev status
./dev logs
./dev rescan   # explicit source scan; startup does not scan
./dev stop
```

It reads private mode-0600/0400 files from
`~/.config/rosbag-analyser/environment` and `database.env`. The first sets
existing separate source/derived roots and front/IMU topics; the second holds
`ROS_BAG_ANALYSER_DATABASE_PASSWORD` and optional database host/user/name/port.
The launcher defaults to PostgreSQL on the Windows host and sources Humble for
the worker. File locations can be overridden with
`ROS_BAG_ANALYSER_SETTINGS_FILE` and `ROS_BAG_ANALYSER_DATABASE_SECRET_FILE`.
Never commit them.

For other environments, use the installed `rosbag-analyser`,
`rosbag-analyser-worker`, and `rosbag-analyser-migrate` entry points with explicit
environment settings. `config.py` validates roots, database URL, topics, tools
and bounds. Migrate the development database explicitly before starting.

`scripts/rosbag-analyser-service` is used by `./dev`;
`scripts/install-local-dev` installs the Real data and Synthetic data Windows
shortcuts without starting either mode. Both remain
active. VM release instructions are in [Operations](OPERATIONS.md).

## Verification

From the repository root:

```bash
.venv/bin/python -m pytest -q tests/unit tests/api
node --test tests/js/test_*.js
```

Node needs the built-in test runner; it is a development tool, not an application
runtime dependency. Additional suites have explicit prerequisites:

| Suite | Prerequisite |
| --- | --- |
| `tests/ros/` | Source `/opt/ros/humble/setup.bash`, then run with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` to avoid unrelated ROS pytest plugins |
| `tests/postgres/` | Disposable database in `ROS_BAG_ANALYSER_TEST_DATABASE_URL`, `ROS_BAG_ANALYSER_ALLOW_TEST_DATABASE_RESET=1`; use `--require-postgres` |
| `tests/deployment/` | Configured disposable proxy/tools; see its fixtures |
| `tests/real_archive/` | `RUN_REAL_ARCHIVE_TESTS=1`, source settings and disposable database; inspect fixtures and bound the check first |

The PostgreSQL suite resets its target schema. Never use a database whose data
you need to retain. Routine tests use small synthetic archives and temporary
output. Skipped integration tests are not evidence that those integrations pass.

For frontend changes, inspect affected workflows in a browser, including
loading/error states, keyboard access, responsive layout and playback when
relevant. Tests should protect behavior, not freeze whole stylesheets by hash.

## Git

Use focused, descriptive commits and preserve shared release commit IDs.
Commit, push and deployment are separate actions. There is no numbered-phase
workflow. Local recovery files belong in ignored `.local-backup/`.
