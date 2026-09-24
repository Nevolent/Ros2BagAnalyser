# Frontend architecture

React owns the persistent shell, hash routing, controls and local presentation
state. `main.tsx` injects `createApiWorkspace()`; only the explicit development
URL `?demo=1` injects the imported visual fixtures. The Python frontend and VM
release remain unchanged.

## Service boundary

`data/api-types.ts` describes the existing Python API contracts.
`api-mapping.ts` maps those contracts into the imported UI models; components
never recover IDs or state from table text. `api-workspace.ts` owns catalog and
processing polling, subscriptions and asynchronous commands. Route cleanup
aborts reads and stops timers. Mutation results invalidate older reads; failed
requests preserve the last good data and show an error. Mutations are never
replayed automatically. Source scanning is always explicit.

Catalog reads use `/api/v1/catalog`. Processing uses overview plus cursor-based
queued, failed and history pages. Outputs are grouped by recording; actions
expand selected rows back to backend job IDs. History contains the latest
successful jobs delivered by the API. Cumulative estimates come from overview,
with unavailable displayed for outputs outside its estimate window. Live timing
comes from stored backend milliseconds. The design's stage and reorder controls
are intentionally absent.

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

`Timeline` owns the clock, playback, channels, zoom and selection locally. Live
readout selects the last sample at or before the clock and clears outside
measured coverage. Graph reduction preserves spikes and gaps. `camera-clock.ts`
converts the same bag-relative clock to each video's coverage-relative time;
measured coverage and buffering control visibility. Effects dispose listeners,
observers, animation frames and media playback on navigation. Graph zoom changes
the visible window, not the playback clock. Demo interpolation remains confined
to the explicit visual fixtures.

## Presentation

Use the existing components and semantic tokens described in
[the design system](design-system.md). The imported layout is the reference.
`live-states.css` adds only centered text, red errors, focus treatment for
recording links and compact pagination. Recordings and Processing keep selection
and sorting locally. Failed commands do not produce optimistic success notices.
Recording diagnostics appear after the source assets, separated by a divider.

The live command-search menu lists the three implemented application pages.
The explicit visual demo retains its imported placeholder entries for comparison.
