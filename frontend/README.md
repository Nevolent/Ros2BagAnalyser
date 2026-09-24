# React frontend

This Vite, TypeScript and React application is the visual source of truth for the
replacement UI. It connects to the existing ROS 2 Bag Analyser APIs. The legacy
frontend remains the backend's default; this folder is separately runnable and
is not included in the VM release yet.

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

```sh
npm run build
npm run preview
# http://127.0.0.1:4173; forwards /api to the same backend
```

A build creates ignored `dist/`; it does not change Python packaging or deploy
anything. The preview server is for local evaluation.

## Behavior

- Recordings uses saved catalog data and the real folder tree. Recording names
  open `#/analysis/{id}`. Filters include Processing, Partially prepared, and
  Review (red for readable recordings with zero-duration metadata).
- Rescan, preparation, pause/resume, cancellation and retry use the existing API.
  Preparation requests the three outputs where available. Requests wait for
  server results and preserve errors. No stage display or queue reordering is
  exposed. Cancelling the active recording also cancels its remaining outputs.
- Processing groups outputs by recording. History sums the returned latest
  successful output sizes and runtimes. Pages start with 100 backend output jobs;
  Load more follows the API cursor. Counts describe the loaded rows, so groups
  can gain outputs when more data loads. Queue estimates come from the server;
  unavailable estimates and pending controls are shown truthfully. Elapsed time
  includes pauses, as reported by the backend. The live
  progress track does not claim a percentage the backend cannot measure.
- Analysis uses identity-bound video and validated six-axis IMU data, one
  recording-relative clock, measured camera coverage, explicit signal gaps,
  last-sample lookup and bounded graph drawing. Camera-only review works.
  Loading/queued/processing states are plain text. Diagnostics and media errors
  are collected at the bottom of Recording details in the shared red.

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
