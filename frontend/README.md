# Tectrace workspace

A visual ROS bag analysis workspace built with React, TypeScript and Vite. Recordings, Processing and Analysis preserve the tailored project's appearance and interactions. All data and processing actions are local simulations; no backend or API calls are connected.

## Development

```sh
npm install
npm run dev
```

Vite provides React Fast Refresh at http://127.0.0.1:5173. `npm run build` checks TypeScript and creates `dist`; `npm run preview` serves the production build.

## Structure

- `src/app/`: persistent application shell, navigation, command search and service provider.
- `src/components/`: shared page layout, resizable panels, buttons, tabs, tables, search fields, filters, checkboxes, dialogs, popovers and status badges.
- `src/features/recordings/`: archive filtering, folder navigation, selection, preparation and scan controls.
- `src/features/processing/`: queue actions, failure details, history and simulated progress.
- `src/features/analysis/`: cameras, recording metadata and the React timeline and recording details.
- `src/data/`: typed domain models, service contract, local implementation and sample fixtures.
- `src/styles/theme.css`: color, spacing, radius and control-size tokens.
- `src/styles/base.css`: reduced foundations inherited from the original design. This is static CSS, not a Tailwind compiler.

Read [the component and styling guide](docs/design-system.md) before adding pages, and [the architecture guide](docs/architecture.md) when connecting the backend.

## Current behavior

The archive contains 211 sample bags in 30 folders. Preparation updates a shared local queue; reordering, cancellation, retries and statuses survive navigation. Reloading resets the session. Archive scans simulate a five-second operation. Processing progress advances while that page is mounted, and supports pause, cancellation and looping.

Analysis provides six sample IMU channels, synchronized playback, seeking, channel selection, zoom and Shift-drag range selection. The Front and Top camera assets are still PNG previews. There is no ROS parser, LiDAR renderer or processing service in this repository yet.

## Validation

```sh
npm test
npm run build
npm run format:check
```

Playwright starts Vite automatically unless `PLAYWRIGHT_BASE_URL` points to an already running server. Install Chromium with `npx playwright install chromium`, or set `CHROMIUM_PATH`. Tests cover the existing flows, responsive layouts from 390 to 1920 pixels, React lifecycle cleanup, history navigation and the local service's state transitions. Test screenshots go to `test-results/`.

For visual regression checks, start the approved UI and capture a baseline **before** making changes:

```sh
npm run visual:capture
# After making changes, against the same browser and operating system:
npm run visual:compare
```

Set `PLAYWRIGHT_BASE_URL` to choose a server. The script captures 30 states across four widths and both themes, including preparation, filters, search, failures and sensor selection. It reports pixel differences at a 0.1 threshold and saves before/after/difference images under `artifacts/react-migration/`. Captures are local, ignored artifacts; do not overwrite an approved baseline to dismiss a regression. Font rasterization and composited camera captions can vary slightly between browser runs.

This standalone project was imported into the parent repository as a folder; its separate Git history is not included. Earlier design screenshots remain in `artifacts/` as historical references.
