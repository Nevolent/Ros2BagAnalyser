# Usage

## Review a recording

1. In **Recordings**, browse folders or search the saved catalog.
   **Thumbnail** opens by default and adds a camera image, the full
   AI description and a **Bunker** tag when identified. Descriptions use one line
   with ellipsis when space is limited; only cut-off text offers a hover/focus popup
   to read it in full. Clicking the image, title, description, tag or space between
   them opens Analysis. **Compact** offers the dense list. The view choice persists
   during navigation; opening or refreshing the page starts in Thumbnail.
   Hover anywhere on a row to immediately show the next image, then cycle every
   750 ms through up to six frames. Leaving restores the middle frame. Phones
   and reduced motion keep the image still; keyboard focus also activates desktop previews.
   The search clear icon stays visible at the right end of the field.
   Opening or refreshing the page silently discovers new readable bags. Known
   recordings stay unchanged; for source changes, moved/removed bags or a complete
   inspection, use the bottom-left **Full rescan** icon, shown only in Recordings.
   Scanning continues after closing the tab; refreshed pages and other browsers
   show the same spinning icon and cannot start another scan. Hover or keyboard
   focus shows **Scanning archive**. Unchanged databases reuse saved timestamp
   checks while full rescan refreshes source health and processing targets.
   The server checks for new bags every 15 seconds, even without an open browser.
   A new folder must stay unchanged for 30 seconds and pass readable-bag checks
   before it enters Processing. The source files stay in their original folder.
   Front video runs first, followed by up to six thumbnails, AI using those same
   images, then other available previews and telemetry. Without a usable front
   video, another supported camera or companion video can provide even one thumbnail.
   Full rescan fills missing, failed or outdated available outputs for all recordings.
   Valid compatible output and active work are reused. A processing
   policy change regenerates only its affected outputs and dependent output. Thumbnail placeholders
   use muted text for No Thumbnail, Queued or Processing. Thumbnail failures
   show No Thumbnail; their diagnostics appear in Analysis. Failed or cancelled
   thumbnails can be retried in Processing or through Prepare Selected.
   A recording with no usable camera or video frame shows No Thumbnail and does not offer
   an identical retry; changed camera inputs need Full rescan first.
2. Select recordings and choose **Prepare Selected**, then confirm. This prepares
   available thumbnails, camera previews, AI descriptions, IMU and wheel encoder data, reusing compatible output.
   **Go to Processing** is selected by default; clear it to stay in Recordings.
   Filter **Partially prepared**, select all, then prepare to fill missing or outdated
   outputs without regenerating compatible previews or telemetry.
3. In **Processing**, follow the queue, cancel or reorder waiting work, and
   retry failures. **Move to top** promotes all selected recordings together, preserving
   their order. Hover or focus Outputs to see the queued or completed outputs;
   History runtime lists each output's duration; Size lists each output's file size.
   These hover regions fill the cells, including above and below the numbers.
   One output runs at a time.
4. Open a recording in **Analysis**. Play, pause or seek on the shared timeline;
   choose **Angular velocity**, **Linear acceleration** or **Encoders** in the graph
   menu. Combine X/Y/Z axes or FL/FR/ML/MR/RL/RR wheels with the adjacent checkboxes,
   and zoom the graph. Encoders share one RPM axis.

Fixed readout baselines sit 2.5 pixels above the playhead marker and show only selected axes or wheels.
Numbers, axis/wheel labels and units share a baseline; equally spaced labels keep their positions across signs and digit counts.
Labels, traces and values share their colors, with the number before its axis/wheel label.
Hover over the encoder readouts or wheel checkboxes, or focus them with Tab for a wheel abbreviation
guide that follows the pointer; Escape dismisses it.
The vertical scale fits the selected data in the visible time window with a small
margin and five evenly spaced ticks. All selected axes or wheels share the same scale; overlapping traces
use modest transparency. Brief extreme encoder spikes appear
as translucent red bands across the graph, narrowing to lines when zoomed out;
hover or focus a band to inspect the original value, or click it (Enter with keyboard
focus) to seek to the event. Playback keeps its current state; Space plays or pauses.
These suspected glitches are excluded from the scale and show a warning in the
readout. Sustained changes remain plotted. The five dotted lines stay in place.
With every checkbox cleared, the dotted grid and timeline remain without values.
Unprepared telemetry uses the same grid, with a centered status message and a
small break in the dotted line behind the text.

Timeline positions and gap diagnostics use **Unix timestamps**, with milliseconds,
not elapsed recording seconds. Unix time means seconds since the Unix epoch;
durations and navigation steps still use seconds. Missing time origins show **—**.
Timestamp pauses break the plotted trace and clear values until samples resume.

Space plays or pauses; arrow keys seek one second, or ten seconds with Shift.
Clicking an axis or wheel checkbox keeps its selection when Space subsequently pauses playback.
Hold Shift and drag on the graph to zoom in; hover or focus **?** for this hint.
The arrows between the timestamps move the visible window earlier or later by
20% of its width, without seeking. Zoom in for smaller steps.
**Front** uses only the main eligible colour camera. Clearly front-named streams
come first; otherwise message count and topic name choose a stable default.
Ceiling, top, rear and downward views are excluded from front inputs.
Playback stops when leaving Analysis. Filters, panel settings and the last
analysis position persist while switching pages during the browser session.

## Status and failures

| Status | Meaning |
| --- | --- |
| Readable / Damaged | Source health; inspect the diagnostic for details |
| Review | Timestamp gaps or zero metadata duration need inspection |
| Not planned | No analysis output is ready and no analysis output is active or failed |
| Queued / Processing | Analysis work is waiting or running |
| Ready | Front preview, AI description and all other available analysis outputs are validated, with no active or failed analysis output |
| Partially prepared | Some analysis outputs are ready; others need preparation, including changed processing or newly supported sensors |
| Failed | Any analysis output failed, including AI; or front input is unavailable and no analysis output is ready |
| Worker offline | Saved jobs are waiting for the worker |

Hover or focus a red status for its diagnostic, or **Ready** / **Partially prepared**
for a fixed-order list with prepared outputs in green and available pending outputs in grey.
Failed recordings retain ready output and show failed-output diagnostics below that list.
Unavailable inputs are omitted. Thumbnails do not affect Analysis status or appear in
its hover list or diagnostics. Thumbnail diagnostics appear in Analysis under Recording errors.
Analysis has Details and Topics
views. Details shows the short AI description after the source components, with a
**Bunker** tag only when the model identifies all required visual cues. Diagnostics
appear below the description. The description uses
sampled frames and may miss events between them. Timestamp gaps appear in the
graph and in Review health diagnostics; gaps alone do not prove data loss.
**Full rescan** refreshes this information.

The processing percentage compares elapsed time with an estimate, capped at
99%. **Estimate exceeded** means processing has taken longer than predicted.
Estimates need at least two recent compatible successes with comparable input
sizes; otherwise the estimate is unavailable. AI estimates use a fixed image-set
work unit rather than the whole bag's size.
Cancellation takes effect at a safe checkpoint. Browser refresh preserves jobs;
a worker restart interrupts running work, which requires Retry, Prepare Selected or Full rescan. Camera loading
retries automatically, then offers a **Retry** button if needed.

## Supported data

The application reads uncompressed, single-file ROS 2 SQLite recordings.
Front previews discover raw `sensor_msgs/msg/Image` streams by type and support
`rgb8`, `bgr8`, `rgba8` and `bgra8`, without requiring a configured topic name.
Named camera streams also support `mono8`/`mono16`. KuupKulgur's
`front_camera/actually_raw_image` `UInt16MultiArray` is shown as grayscale when its
height/width layout is valid, using ROS recording timestamps. Sixteen-bit intensity
uses a fixed full-range conversion; no per-frame brightness adjustment is applied.
Ouster LiDAR measurement images remain excluded.
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
