# Usage

## Review a recording

1. In **Recordings**, browse folders or search the saved catalog.
   Opening or refreshing the page silently discovers new readable bags. Known
   recordings stay unchanged; for source changes, moved/removed bags or a complete
   inspection, use the bottom-left **Settings** icon and **Do a full rescan**.
   Discovery queues thumbnails for new bags; full rescan also queues unattempted
   recordings. These checks do not prepare full videos, descriptions or telemetry.
2. Select recordings and choose **Prepare Selected**, then confirm. This prepares
   available thumbnails, camera previews, AI descriptions, IMU and wheel encoder data, reusing compatible output.
   **Go to Processing** is selected by default; clear it to stay in Recordings.
   Filter **Partially prepared**, select all, then prepare to fill missing or outdated
   outputs without regenerating compatible previews or telemetry.
3. In **Processing**, follow the queue, cancel or reorder waiting work, and
   retry failures. One output runs at a time.
4. Open a recording in **Analysis**. Play, pause or seek on the shared timeline;
   choose **Angular velocity**, **Linear acceleration** or **Encoders** in the graph
   menu. Combine X/Y/Z axes or FL/FR/ML/MR/RL/RR wheels with the adjacent checkboxes,
   and zoom the graph. Encoders share one RPM axis.

Fixed readouts above the graph show only selected axes or wheels; labels, traces and values share
their colors, with the number before its axis/wheel label. The vertical scale fits
the selected data in the visible time window. Angular velocity and RPM center on
zero; a single acceleration axis centers on its first visible value, while
combined acceleration axes fit their shared range. Brief extreme spikes appear
as translucent red bands across the graph, narrowing to lines when zoomed out;
hover or focus a band to inspect the original value.
These suspected glitches are excluded from the scale and show a warning in the
readout. Sustained changes remain plotted. The five dotted lines stay in place.
With every checkbox cleared, the dotted grid and timeline remain without values.
Unprepared telemetry uses the same grid, with a centered status message and a
small break in the dotted line behind the text.

Space plays or pauses; arrow keys seek one second, or ten seconds with Shift.
Hold Shift and drag on the graph to zoom in; hover or focus **?** for this hint.
When multiple colour-camera previews are prepared, use the dropdown beside
**Front** to switch streams without moving the shared timeline. A clearly
front-named stream is selected first; otherwise the busiest stream wins, with
topic name breaking ties.
Playback stops when leaving Analysis. Filters, panel settings and the last
analysis position persist while switching pages during the browser session.

## Status and failures

| Status | Meaning |
| --- | --- |
| Readable / Damaged | Source health; inspect the diagnostic for details |
| Review | Timestamp gaps or zero metadata duration need inspection |
| Not planned | No output is ready and no output is active or failed |
| Queued / Processing | Work is waiting or running |
| Ready | Front preview, AI description and all other available outputs are validated, with no active or failed output |
| Partially prepared | Some outputs are ready; others need preparation, including changed processing or newly supported sensors |
| Failed | Front input is unavailable or an output failed |
| Worker offline | Saved jobs are waiting for the worker |

Hover or focus a red status for its diagnostic, or **Partially prepared** for a
list of prepared outputs in green and available pending outputs in grey.
Unavailable inputs are omitted. Analysis has Details and Topics
views. Details shows the short AI description after the source components, with a
**Bunker** tag only when the model identifies all required visual cues. Diagnostics
appear below the description. The description uses
sampled frames and may miss events between them. Timestamp gaps appear in the
graph and in Review health diagnostics; gaps alone do not prove data loss.
**Settings → Do a full rescan** refreshes this information.

The processing percentage compares elapsed time with an estimate, capped at
99%. **Estimate exceeded** means processing has taken longer than predicted.
Cancellation takes effect at a safe checkpoint. Browser refresh preserves jobs;
a worker restart interrupts running work, which requires retry. Camera loading
retries automatically, then offers a **Retry** button if needed.

## Supported data

The application reads uncompressed, single-file ROS 2 SQLite recordings.
Front previews discover raw `sensor_msgs/msg/Image` streams by type and support
`rgb8`, `bgr8`, `rgba8` and `bgra8`, without requiring a configured topic name.
Monochrome streams such as `mono8`/`mono16`, including Ouster LiDAR measurement
images, are excluded without camera-failure diagnostics.
Top-down previews use companion AVI/CSV files. IMU data has six raw angular
velocity (`rad/s`) and linear acceleration (`m/s²`) axes. Multiple IMU topics
require an operator preference. Encoders support the custom KuupKulgur
`EncodersStamped` message, with six RPM values ordered front left/right (FL/FR),
middle left/right (ML/MR), rear left/right (RL/RR). Recorded values are preserved;
matching wheel values can overlap.

Top-down, IMU and encoder inputs are optional. Cameras and numeric telemetry values clear
outside measured coverage. IMU and encoder traces stop at their measured endpoints.

For support, include the recording/job ID, visible error, browser, and time
with timezone. Keep recordings, private paths and credentials out of reports.
