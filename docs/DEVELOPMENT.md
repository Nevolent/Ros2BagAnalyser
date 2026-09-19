# Development

Edit `src/rosbag_analyser/web/` to change the served frontend.

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
python3 tools/serve_frontend_mock.py
# http://127.0.0.1:4173/?mock=all-ready
```

This serves the production frontend with a development-only API adapter.
Scenarios: `all-ready`, `topdown-unavailable`, `front-missing`, `imu-missing`,
`zero-duration`, `queued`, `processing`, `successful-processing`,
`partial-failure`, and `long-recording`. Data, jobs and video are synthetic;
this preview does not verify ROS processing or real camera timing. The real
API never injects the adapter.

## Full local application

The existing WSL/Windows launcher remains supported:

```bash
./dev check
./dev start
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
`scripts/install-local-dev` installs the optional Windows shortcut. Both remain
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
