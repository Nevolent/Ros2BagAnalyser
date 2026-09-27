# React frontend

This Vite, TypeScript and React application is the visual source of truth for the
replacement UI. It connects to the existing ROS 2 Bag Analyser APIs. The packaged production build is the backend's default browser UI. This folder
contains the source and separately runnable Vite development server.

## Run against the backend

Use Node 22.12+ or 24 and the existing backend started with `./dev start` from the
repository root. Then, in this folder:

```sh
npm ci
npm run dev
# http://127.0.0.1:5173
```

Vite forwards `/api` to `http://127.0.0.1:8000`, including media range requests.
The old UI remains at the backend address. To use a different backend:

```sh
ROS_BAG_API_TARGET=http://127.0.0.1:8001 npm run dev
```

`ROS_BAG_API_TARGET` is a server-side proxy setting, not a browser variable. Use
an existing authorized backend or local tunnel. Both interfaces act on the same
catalog and persistent jobs; opening a page never scans or starts processing.

For the original visual fixtures, open `http://127.0.0.1:5173/?demo=1`.
Demo mode is explicit and available only in the development server. An
unavailable API displays an error and never switches to simulated data.

For synthetic data, open `http://127.0.0.1:5173/?synthetic=1` with the same
Vite server. The packaged production build accepts the same query parameter;
from the repository root, `./dev open synthetic` serves it without backend
infrastructure and `./dev open real` starts the local API/worker. `./dev install`
creates a desktop shortcut for each mode, leaving VM SSH launchers untouched.
There is no separate playground branch or Vite build mode. Synthetic data creates
over 500 in-memory recordings across nested folders, plus 100 failures, 180
history rows and a queue. Preparation, retry and cancellation update the
local state. Each queued recording takes about 1–2 minutes; newly prepared or
retried recordings move to the front of the waiting queue. The camera images and
IMU graph are shared visual fixtures while recording details and output states
change per selection. Reloading resets the simulation. No ROS bags, derived
artifacts, backend API, or VM are accessed. The application UI has no mode label.

```sh
npm run build
npm run preview
# http://127.0.0.1:4173; forwards /api to the same backend
```

A build creates ignored `dist/`. Copy its contents to
`src/rosbag_analyser/web/react/` before committing a production UI change.
The preview server is for local evaluation.

## Behavior

- Recordings uses saved catalog data and the real folder tree. Recording names
  open `#/analysis/{id}`. Filters include Processing, Ready, Failed, and
  Review (red for readable recordings with zero-duration metadata).
- Rescan, preparation, cancellation and retry use the existing API.
  Preparation requests the three outputs where available. Missing outputs are
  skipped when another output can be prepared; scheduling failures remain visible. No stage display is exposed. Selected queue rows can be moved up or down
  through the existing reorder API. Cancelling the active recording also cancels its remaining outputs.
- Processing automatically follows every API cursor before publishing a complete
  set of queue, failure and history groups. A failed recording keeps its successful
  siblings in Failures; retry still submits only failed job IDs. Recording names
  link to Analysis. The active card is absent when idle or cancelled. Its estimated
  percentage is elapsed / estimated runtime, capped at 99%; reaching the estimate
  displays Estimate exceeded. No processing pause control is shown.
- Confirmations close before network work completes. Cancellations and retries
  dismiss affected rows immediately; failed requests restore data and show a
  dismissible error across pages. Cached tables refresh without loading overlays.
- Presentation choices persist across routes for the current browser session:
  folders, filters, selection, sorting, scrolling, panels and Analysis channel,
  zoom and time. New folders start open. Playback stops on leaving Analysis.
- Analysis uses identity-bound video and validated six-axis IMU data, one
  recording-relative clock, measured camera coverage and exact last-sample lookup.
  The finite final graph value extends visually through the timeline end; readouts
  remain empty outside measured coverage and internal null gaps remain visible.
  Pointer seeks are coalesced and the dense trace is memoized outside clock updates.
  Optional missing sources use muted asset states, without duplicate error codes.
  Actual processing, validation and media errors remain visible in Recording details.
- Tables, folders and details use `ScrollArea` for a compact scrollbar inside the
  content. Keyboard scrolling stays native; horizontal overflow keeps native bars.

## Checks

```sh
npx playwright install chromium
npm test
npm run build
npm run format:check
```

Browser tests use synthetic API responses and media. They cover real HTTP
contracts, controls, failures, navigation races, timestamp/coverage handling,
keyboard use, responsive layouts and the explicit visual demo. They do not
certify ROS processing or the live VM. `CHROMIUM_PATH` selects an installed
browser; `PLAYWRIGHT_BASE_URL` selects an existing Vite server.

Capture visual fixtures before a design change with `npm run visual:capture`,
then use `npm run visual:compare` on the same browser and operating system.
The script captures 30 states across four widths and both themes. Local
captures live under ignored `artifacts/react-migration/`; do not replace an
approved baseline to dismiss differences. New filters intentionally change the
open filter menu.

See [architecture](docs/architecture.md) and the [design system](docs/design-system.md)
for component ownership and styling rules.
