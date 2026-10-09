# Usage

## Review a recording

1. In **Recordings**, browse folders or search the saved catalog.
2. Select recordings and choose **Prepare Selected**, then confirm. This prepares
   available camera previews, AI descriptions and IMU data, reusing compatible output.
   **Go to Processing** is selected by default; clear it to stay in Recordings.
   Filter **Partially prepared**, select all, then prepare to fill missing descriptions
   without regenerating compatible previews or telemetry.
3. In **Processing**, follow the queue, cancel or reorder waiting work, and
   retry failures. One output runs at a time.
4. Open a recording in **Analysis**. Play, pause or seek on the shared timeline;
   select an IMU axis and zoom the graph.

Space plays or pauses; arrow keys seek one second, or ten seconds with Shift.
Playback stops when leaving Analysis. Filters, panel settings and the last
analysis position persist while switching pages during the browser session.

## Status and failures

| Status | Meaning |
| --- | --- |
| Readable / Damaged | Source health; inspect the diagnostic for details |
| Review | Timestamp gaps or zero metadata duration need inspection |
| Not planned | No front preview is ready and no output is active or failed |
| Queued / Processing | Work is waiting or running |
| Ready | Front preview and AI description are validated, with no active or failed output |
| Partially prepared | Front preview is ready but its AI description is missing |
| Failed | Front input is unavailable or an output failed |
| Worker offline | Saved jobs are waiting for the worker |

Hover or focus a red status for its diagnostic. Analysis has Details and Topics
views. Details shows the short AI description after the source components, with a
**Bunker** tag only when the model identifies all required visual cues. Diagnostics
appear below the description. The description uses
sampled frames and may miss events between them. Timestamp gaps appear in the
graph and in Review health diagnostics; gaps alone do not prove data loss. An explicit rescan refreshes this information.

The processing percentage compares elapsed time with an estimate, capped at
99%. **Estimate exceeded** means processing has taken longer than predicted.
Cancellation takes effect at a safe checkpoint. Browser refresh preserves jobs;
a worker restart interrupts running work, which requires retry. Camera loading
retries automatically, then offers a **Retry** button if needed.

## Supported data

The application reads uncompressed, single-file ROS 2 SQLite recordings.
Front previews support raw ROS Image streams with `rgb8` or `bgr8` encoding;
top-down previews use companion AVI/CSV files. IMU data has six raw angular
velocity (`rad/s`) and linear acceleration (`m/s²`) axes. Multiple IMU topics
require an operator preference.

Top-down and IMU inputs are optional. Cameras and numeric IMU values clear
outside measured coverage. A final IMU value extended visually to the graph's
end is not additional recorded data.

For support, include the recording/job ID, visible error, browser, and time
with timezone. Keep recordings, private paths and credentials out of reports.
