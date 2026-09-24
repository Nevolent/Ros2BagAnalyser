# Architecture and backend integration

React owns the shell, pages, controls and local UI state. `main.tsx` constructs one `WorkspaceService` and injects it through `WorkspaceProvider`. The shell remains mounted while hash routes switch feature pages. Existing `#/recordings`, `#/analysis` and `#/processing` links work; legacy entry aliases are preserved.

## Data boundary

`data/types.ts` defines the current UI domain models. `data/workspace-service.ts` is a small local contract with a snapshot, subscriptions and commands. `data/demo-workspace.ts` implements that contract with immutable snapshots and fixtures. Components subscribe through `useWorkspace()` and call commands through `useWorkspaceService()`.

- Recording and job data belong to the service.
- Search text, folder selection, checked rows, open dialogs and active tabs belong to the relevant React feature.
- Layout measurements and focus management use scoped DOM refs.
- No component reads table text to recover domain data.

The service is an integration seam, not a proposed HTTP API schema. When your backend is ready, implement an adapter that maps its responses into these models and publishes updated snapshots. Replace the injected service in `main.tsx`. Extend the contract for asynchronous commands and loading/error states based on the actual backend. The current commands are synchronous local simulations; endpoint URLs, authentication, polling, streaming and transport choices are intentionally unspecified.

Keep archive listings and job metadata separate from large sensor payloads. Renderers should receive the needed time window or prepared data rather than putting every sensor sample into application-wide React state. Shared table sorting compares dates, durations and file sizes by their values while preserving the service order. Numeric timestamps and sizes can be added to the domain models when the backend schema is known; the current archive fixtures preserve their existing display strings.

## Analysis renderer

`AnalysisPage` receives the recording metadata, camera previews and IMU bundle through the service. `RecordingDetails` groups the metadata and asset inventory. `Timeline` is a memoized React visualization boundary: its local state owns playback, channels, zoom, range selection, menus, readouts and SVG rendering. Frame updates do not update the application-wide store, and sampled paths are memoized independently of the playback cursor.

Effects cancel animation frames, disconnect resize observers, abort document listeners and pause camera elements on unmount. The video synchronization adapter remains available when real video sources replace the still images. CSS grid and container sizing preserve both camera aspect ratios in the same layout pass as panel resizing. The graph commits ResizeObserver dimensions before paint so its viewBox stays aligned during dragging and collapse. A future LiDAR viewer can use the same playback-time boundary; no LiDAR implementation was added.

The current preview bundle has uniformly spaced samples across six IMU axes. Adapt the sampling model when real timestamped or irregular sensor data is available; it is not a production ROS format assumption.

## Preserved session behavior

Preparation updates both archive statuses and the queue in one published snapshot. Preparing the same recording again does not duplicate its queued job. Cancelling a prepared job returns its recording to `Not planned`. Retry creates work only for failed outputs. Group reordering preserves selected-job order. Reloading creates a fresh demo service.

The Processing page owns the preview timer lifecycle. Leaving the page stops the simulated elapsed timer; returning uses the retained elapsed value. Archive scan state is local to Recordings. These behaviors preserve the tailored visual demo rather than simulate a background server.

## Extending the application

Add a feature folder, compose the shared components documented in `design-system.md`, then register the route and navigation entry. Keep data acquisition behind the service or a feature-specific adapter. Use semantic color and spacing tokens instead of introducing a separate palette or copied controls.

The command search retains the existing visible demo destinations for visual compatibility. Destinations without an implemented page continue to display Recordings. This migration did not add additional product pages.
