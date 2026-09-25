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
   pause/resume or cancel current work, reorder/cancel queued work, and retry
   failures.
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

In the React Processing view, elapsed time counts active processing time and
freezes during pause. Estimates are approximate and can be unavailable or
exceeded. Pause/cancel takes effect at a safe checkpoint. Worker restart
interrupts running work; that attempt needs explicit retry. Browser refresh
preserves the queue and completed output.

Camera and IMU coverage can differ. Views hide or clear outside measured
coverage. IMU axes are raw angular velocity (`rad/s`) and linear acceleration
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
