# JetBrains frontend workspace

This is the retained frontend design/workflow reference: Recordings,
Processing and Analyzer, with a local synthetic API. The deployed application
serves `src/rosbag_analyser/web/`; FastAPI does not load this folder.

## Preview

From the repository root:

```bash
python3 jetbrains/serve.py
# http://127.0.0.1:4174/
```

Requires Python 3 and FFmpeg, without additional Python packages. The server
binds to loopback; `--port` selects another port. First startup generates two
short test-pattern clips in ignored `.fixtures/`. It never reads recordings or
connects to the VM, PostgreSQL or a ROS worker.

All data is synthetic. State is shared by local tabs and survives navigation;
server restart or scenario change resets it. Settings offers `mixed`, `empty`,
`offline`, `scan-error`, `api-error` and `slow` scenarios. Try selection,
preparation, queue controls, Analyzer playback and error recovery.

## Integration

`common.js` uses same-origin requests matching the application APIs. HTML/CSS/JS
are the design assets. `serve.py`, `synthetic.py`, `experiment.js`, fixtures
and QA output are preview tooling and must not enter the served app. Only the
local server injects experiment controls.

Adapt `analyzer.html?id=…` links to the real application's `/recordings/{id}`
routing during integration. Preserve identity-bound URLs, decimal nanoseconds,
the shared clock and coverage. This renderer caps IMU input at 200,000 samples;
measure larger-recording behavior before adopting it for real data.

## Checks

From this directory:

```bash
python3 -m unittest -v test_synthetic
node --test timeline.test.cjs
```

With the local server running, check HTTP output against application schemas:

```bash
../.venv/bin/python -m unittest -v test_contracts
```

`browser-check.cjs` uses a separate Chrome debugging session on localhost 9223
and Node's built-in WebSocket support. It resets synthetic state and saves
screenshots/reports to ignored `.qa/`. Synthetic checks do not establish
real-recording correctness or deployment readiness.
