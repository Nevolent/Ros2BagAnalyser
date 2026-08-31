# Frontend mock mode

Mock mode runs the production frontend files in
`src/rosbag_analyser/web/` directly. It does not start the FastAPI service,
ROS, PostgreSQL, a worker, a NAS mount, or a VM.

From a checkout on your MacBook:

```bash
python3 tools/serve_frontend_mock.py
```

Then open:

```text
http://127.0.0.1:4173/?mock=all-ready
```

Use the **Mock scenario** control in the lower-right corner to switch state, or
change the `mock` query parameter and reload. The available values are:

- `all-ready`
- `topdown-unavailable`
- `front-missing`
- `imu-missing`
- `zero-duration`
- `queued`
- `processing`
- `successful-processing`
- `partial-failure`
- `long-recording`

The local server injects the mock adapter only into its development response;
the adapter replaces only browser requests under `/api/` when that parameter
is present. It uses the production V1 catalog, preparation,
processing, recording-detail, and IMU endpoint shapes. Preparing an unprepared
mock recording creates queued jobs; repeated Processing refreshes advance the
single simulated worker through queued, running, and succeeded states. Pause,
resume, cancel, and failed-job retry update that in-memory mock state.

The local server supplies a tiny generic video so ready camera panes exercise
the normal browser media URL path. It is not recording data and does not model
camera frames, timing, byte-range edge cases, or ROS processing. The IMU
response contains a small valid schema-version-2 six-axis payload so graph
interactions can be exercised.

To use the real server again, run the normal application/deployment workflow.
It serves the unchanged `index.html`, `app.js`, `styles.css`, and
`imu_graph.js`; no mock adapter is loaded and the frontend requests the real
same-origin API.
