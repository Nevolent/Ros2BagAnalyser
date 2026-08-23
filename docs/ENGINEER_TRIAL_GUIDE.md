# ROS 2 Bag Analyser engineer trial guide

## Access

Use only the approved HTTPS URL supplied by the trial-access owner while on the
approved VPN/network. Credentials are individual; do not share them. The access
owner handles grants, expiry, replacement, and revocation. Trial users do not
receive SSH, VNC, NFS, PostgreSQL, raw port 8000, or filesystem access.

If the page or login is unavailable, report the time and whether you were on
the approved network. Do not send passwords, cookies, URLs containing secrets,
screenshots of private infrastructure details, or recording filesystem paths.

## Workflow

1. Open **Recordings** and browse the real folder tree or search the saved
   catalog. Loading the page does not scan the NAS.
2. Select readable recordings and choose **Prepare selected**. One action asks
   for the fixed front preview, top-down preview, and six-axis IMU bundle.
3. Open **Processing** to see the one running job, FIFO queue, factual elapsed
   time, approximate estimate when enough history exists, failures, and
   completed history. There is no fabricated percentage.
4. Open a ready recording in **Analyzer**. Use the shared recording clock to
   review both cameras and choose among the six raw IMU axes. Views clear or
   hide outside measured coverage.

Repeated preparation is safe: compatible ready output and active work are
reused. One serial worker means later work may wait. Queue order is stable;
refreshing or restarting the browser does not cancel it. A recording that is
damaged, missing, or otherwise unavailable creates no artificial failed job.

## Source promise

Original recordings are authoritative read-only inputs. The application does
not repair, reindex, rename, move, delete, or write files beside them. Preview
video and IMU artifacts live on separate derived storage. An operator controls
explicit rescans; ordinary engineer actions do not mount or browse NAS files
directly.

## Expected prototype limitations

- This is a limited feedback trial, not a public or high-availability service.
- It supports the three existing artifact kinds and configured ROS topics only.
- Processing is serial; there is no priority, cancellation, automatic retry,
  percentage completion, upload, annotation, or application-managed account
  system.
- Estimates are approximate and can be unavailable or exceeded.
- A source outage or low derived space can temporarily disable new preparation
  while the saved catalog and already-valid artifacts remain usable.
- Front-camera cadence follows image-header capture timing mapped to measured
  record endpoints; the browser retains the accepted 100 ms correction rule.

## Reporting feedback or a problem

Report the numeric recording ID and, when relevant, numeric job ID; what you
expected; what happened; the approximate time and timezone; browser name;
whether the issue repeats; and the visible safe error code/message. Recording
and job IDs are shown in the application and are safer than filesystem names.

Do not include source payloads, absolute paths, credentials, cookies, private
addresses, database details, or full journal output. Send the report to the
named feedback/support contact supplied with your access. For suspected source
changes, security exposure, or repeated wrong output, stop using the affected
recording and mark the report urgent.
