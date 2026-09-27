# Frontend architecture

React owns the persistent shell, hash routing, controls and session presentation
state. `WorkspaceProvider` retains small UI settings across route unmounts;
media, timers and observers are still disposed when leaving a page. `main.tsx`
injects `createApiWorkspace()` by default. `?synthetic=1` selects
`synthetic-workspace.ts` in the same packaged build and Vite server; the older
`?workspace=archive` URL remains compatible. The explicit development URL
`?demo=1` selects the original visual fixtures for design comparisons.
It generates the archive in memory and runs a one-second local queue clock
across routes. Analysis keeps the visual camera and IMU fixtures but maps each
selected recording's metadata, health, output state and diagnostics. The real
API service is never used in this mode. The local synthetic launcher serves the
packaged assets on loopback and does not start backend services. Both data modes
share `main`; there is no separate Vite archive build mode.

## Service boundary

`data/api-types.ts` describes the existing Python API contracts.
`api-mapping.ts` maps those contracts into the imported UI models; components
never recover IDs or state from table text. `api-workspace.ts` owns catalog and
processing polling, subscriptions and asynchronous commands. Route cleanup
aborts reads and stops timers. Mutation results invalidate older reads; failed
requests restore optimistically dismissed jobs and show a dismissible shell error.
Initial loading is separate from background refresh of cached rows. Mutations are never
replayed automatically. Source scanning is always explicit.

Catalog reads use `/api/v1/catalog`. Processing uses overview plus cursor-based
queued, failed and history pages. Every cursor is followed automatically, with
cycle detection, deduplication and abort/version guards; a failed page preserves
the last complete snapshot. Successful siblings stay with actionable failures,
and retry expands only the failed job IDs. History sums latest successful
outputs for recordings without failures. Recording names link to Analysis.
Cumulative queue estimates come from overview. The active card shows elapsed /
estimated runtime, capped at 99%, and Estimate exceeded at the estimate boundary.
Cancellation immediately hides affected work and restores it on failure; the
backend still acknowledges controls at safe checkpoints. Pause/resume remains
an API capability, with no UI control.

The Vite server and preview proxy `/api` to `ROS_BAG_API_TARGET` (default
`http://127.0.0.1:8000`). Browser requests stay on the same origin. This also
preserves identity-bound video range delivery without adding CORS configuration.

## Analysis

`#/analysis/{id}` loads recording detail and output identities. The Analysis
navigation entry revisits the last selected recording during the session; a
fresh session asks the user to select a recording. `analysis-adapter.ts` maps
metadata, source assets, output states and diagnostics. Media URLs must exactly
match the selected recording, output kind and artifact ID.

`telemetry.ts` reuses the existing production `web/imu_graph.js` parser and
reduction helpers. It checks IMU metadata against the selected artifact, bounds
streamed JSON at 64 MiB, validates rows/coverage, retains duplicate timestamps
and per-axis nulls, and keeps large samples outside the subscribed workspace
snapshot. Repeated detail polls reuse a matching validated bundle.

`Timeline` retains clock position, channel and zoom per recording during the
session; playback and transient selection stop on unmount. With validated IMU data, the live readout selects the last sample at or before
the clock and clears outside measured coverage. Without it, the recording clock
remains usable while numeric IMU and Unix labels are hidden. Graph reduction preserves spikes and visible gaps. A finite final sample is
visually held to the recording/camera end without changing samples or readout
coverage. A memoized `Trace` isolates dense SVG elements from clock updates,
and pointer movement schedules at most one seek update per animation frame.
`camera-clock.ts` converts the same bag-relative clock to each video's
coverage-relative time. Measured coverage and initial buffering control
visibility; decoded frames remain visible during later seeks. Effects dispose
listeners, observers, animation frames and media playback on navigation. Graph zoom changes
the visible window, not the playback clock. Demo interpolation remains confined
to the explicit visual fixtures.

## Presentation

Use the existing components and semantic tokens described in
[the design system](design-system.md). The imported layout is the reference.
`live-states.css` owns muted loading/empty states, red errors and link focus.
`ScrollArea` shares compact overlay scrollbars across tables, folders and details,
with native horizontal overflow and keyboard scrolling. Presentation settings
survive page switches; modal dialogs close before asynchronous commands finish.
Optional absence appears in asset rows; actual diagnostics remain after source
assets, separated by a divider.

The live command-search menu lists the three implemented application pages.
The explicit visual demo retains its imported placeholder entries for comparison.
