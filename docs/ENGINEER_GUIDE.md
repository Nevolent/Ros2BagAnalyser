# Engineer guide

Open the application using the address and access method supplied by your
operator. You do not need ROS commands or direct NAS access.

## Review a recording

1. In **Recordings**, browse folders or search the saved catalog. Loading the
   page does not scan the NAS.
2. Select readable recordings and choose **Prepare selected**. Choose front,
   top-down, IMU, or a combination. Compatible ready output and active work are
   reused.
3. Follow work in **Processing**. One output runs at a time. Available controls
   cancel current work, reorder/cancel queued work, and retry failures. A recording
   with failed outputs stays together in Failures, including its successful outputs.
   Recording names in every processing table open Analysis.
4. Open a recording in **Analyzer** to review its available outputs. Play, pause or seek on the shared
   timeline; select an IMU axis and zoom the graph to inspect a section.

The catalog shows Ready when any available output is prepared and no output has
failed or remains active. A failed output makes the recording Failed. Missing
source companions do not prevent available outputs from being prepared.
Available cameras can still be reviewed with a recording timeline when IMU is
unavailable.

## States

| State | Meaning |
| --- | --- |
| Readable / Damaged | Source health; inspect the diagnostic for the exact reason |
| Not planned | No output is prepared or active |
| Queued / Processing | Work is waiting or active |
| Ready | At least one current output has been validated |
| Failed | An attempted output failed; inspect the message and retry if appropriate |
| Worker offline | Saved work waits for the worker to return |

Processing loads all queue, failure and history rows automatically. The active
card appears only while a job is active. Its percentage compares elapsed time
with the estimated runtime, caps at 99%, and changes to Estimate exceeded when
the estimate runs out. It is a time estimate, not measured completion.
Cancel takes effect at a safe checkpoint; the UI dismisses the job immediately
and restores it with an error if the request fails. Worker restart
interrupts running work; that attempt needs explicit retry. Browser refresh
preserves the queue and completed output.

Folders start expanded. Folder choices, filters, sorting, selections, scrolling,
panel settings and the last Analysis recording/channel/zoom/position survive
switching pages during the browser session. Playback stops when leaving Analysis.
Confirmation dialogs close immediately; background request failures appear in
a dismissible message.

Camera and IMU coverage can differ. Cameras and numeric IMU values hide or clear
outside measured coverage. The graph holds the final finite value visually to
the timeline end; this extension is not additional IMU data. IMU axes are raw angular velocity (`rad/s`) and linear acceleration
(`m/s²`), not interpreted rover motion.

## Current limits and support

The service processes configured ROS Image and Imu topics in supported
uncompressed, single-file ROS 2 SQLite recordings. It is not a general bag
converter or arbitrary-topic viewer. Original recordings remain unchanged;
previews and telemetry live in separate storage.

Report recording/job ID, expected and actual behavior, time and timezone,
browser and visible error code. Avoid including recordings, credentials,
private paths or raw server logs. The operator handles access, rescans,
storage and service recovery.
