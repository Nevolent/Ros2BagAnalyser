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

Prepare and retry requests keep an empty queue in “Loading queue…” through the
request and its refresh, including page changes. They invalidate the previous
Processing read so a later visit waits for fresh data. Cached rows remain visible;
queue counts come only from server results. Reused output and failed requests
clear the pending state.

Catalog reads use `/api/v1/catalog`. Processing uses overview plus cursor-based
queued, failed and history pages. Every cursor is followed automatically, with
cycle detection, deduplication and abort/version guards; a failed page preserves
the last complete snapshot. Successful siblings stay with actionable failures,
and retry expands only the failed job IDs. History sums latest successful
outputs for recordings without failures. Recording names link to Analysis.
Cumulative queue estimates come from overview. The active card uses the overview’s recording progress: a stable run identity,
combined active elapsed time and combined frozen estimates across camera/IMU jobs.
It remains visible through worker handoffs. Progress is capped at 99% and shows
Estimate exceeded at the estimate boundary.
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
uses metadata Unix time (relative seconds if unavailable), with a neutral zero
baseline and no numeric IMU readout or empty channel picker. Optional IMU absence
with a ready camera does not show a load error; actual diagnostics remain in details.
Graph reduction preserves spikes and visible gaps. A finite final sample is
visually held to the recording/camera end without changing samples or readout
coverage. A memoized `Trace` avoids rebuilding dense SVG geometry. Its static
SVG has a separate composited layer from the solid HTML cursor and selection overlay, so
clock/readout updates also avoid rasterizing the masked trace again. During
scrubbing the cursor follows the pointer immediately, while camera seeks and
readouts stay frame-coalesced. The value and unit readout on the right rests just
above the dotted grid line and lifts four pixels when the playhead approaches.
During playback the cursor moves by fractional CSS transforms each frame,
independent of React readouts updated
at up to 20 Hz. Space and arrows control playback across Analysis, except
inside text entry, dialogs and widgets with their own keyboard behavior.
`camera-clock.ts` converts the same bag-relative clock to each video's
coverage-relative time. Measured coverage and initial buffering control
visibility; decoded frames remain visible during later seeks. Seeks drain only the
latest requested position, with a brief grace period before automatic drift correction
so slow decoders can resume playback. Explicit seeks bypass that grace period.
A watchdog detects eight seconds without media progress, even while paused;
stalls and camera load failures share three bounded retries before a manual Retry
control and diagnostic appear. Recovery clears that camera’s error; timers are
disposed on reload and navigation. Unchanged camera status does not mutate the DOM.
Effects dispose
listeners, observers, animation frames and media playback on navigation. Graph zoom changes
the visible window, not the playback clock. Demo interpolation remains confined
to the explicit visual fixtures.

## Presentation

Use the existing components and semantic tokens described in
[the design system](design-system.md). The imported layout is the reference.
`live-states.css` owns muted loading/empty states, red errors and link focus.
`ScrollArea` shares compact overlay scrollbars across tables, folders and details,
with native horizontal overflow and keyboard scrolling. Thumbs appear on hover,
focus or scrolling and sit in the panel edge padding without narrowing content.
Scroll limits disable bounce and scroll chaining. Presentation settings
survive page switches; modal dialogs close before asynchronous commands finish.
Optional absence appears in asset rows; actual diagnostics remain after source
assets, separated by a divider.

Red Health and Analysis statuses in Recordings expose catalog/output diagnostics
in a popup to their left on hover or keyboard focus. Escape, table scrolling and
navigation dismiss it. Missing diagnostics are stated explicitly.

The live command-search menu lists the three implemented application pages.
The explicit visual demo retains its imported placeholder entries for comparison.
