"use strict";

// Development-only API adapter. It is inert unless the URL contains ?mock=…
// and deliberately lives outside the production application runtime.
(() => {
  const parameter = new URL(window.location.href).searchParams.get("mock");
  if (!parameter) return;

  const kinds = ["front_preview", "topdown_preview", "imu_series"];
  const scenarios = {
    "all-ready": { label: "Front + top-down + IMU available", states: ["ready", "ready", "ready"] },
    "topdown-unavailable": { label: "Front + IMU, top-down unavailable", states: ["ready", "unavailable", "ready"] },
    "front-missing": { label: "Front unavailable", states: ["unavailable", "ready", "ready"] },
    "imu-missing": { label: "IMU unavailable", states: ["ready", "ready", "unavailable"] },
    "zero-duration": { label: "Zero-duration review state", states: ["ready", "ready", "ready"], durationNs: "0" },
    queued: { label: "Queued processing", states: ["queued", "queued", "queued"], queued: true },
    processing: { label: "Active processing with progress", states: ["processing", "queued", "queued"], processing: true },
    "successful-processing": { label: "Successful processing", states: ["ready", "ready", "ready"], history: true },
    "partial-failure": { label: "One output failed", states: ["ready", "failed", "ready"] },
    "long-recording": { label: "Long / large recording", states: ["ready", "ready", "ready"], durationNs: "1472000000000", sizeBytes: "14889779200" },
  };
  const scenarioName = Object.hasOwn(scenarios, parameter) ? parameter : "all-ready";
  const scenario = scenarios[scenarioName];
  const now = () => new Date().toISOString();
  let nextJobId = 400;
  let nextArtifactId = 700;
  const outputDiagnostic = (kind, state) => state === "unavailable"
    ? { code: `${kind}_unavailable`, message: "This mock recording cannot provide the selected output." }
    : state === "failed"
      ? { code: `${kind}_failed`, message: "The mock worker stopped this output after a simulated validation failure." }
      : null;
  const artifact = (recordingId, kind) => {
    const id = nextArtifactId + recordingId * 10 + kinds.indexOf(kind);
    const route = kind.replaceAll("_", "-");
    const type = kind === "imu_series" ? "data" : "media";
    return {
      id,
      mime_type: kind === "imu_series" ? "application/json" : "video/mp4",
      size_bytes: kind === "imu_series" ? "4096" : "2157",
      coverage_start_ns: "0",
      coverage_end_ns: "12000000000",
      timestamp_provenance: kind === "front_preview"
        ? "ros_image_header_affine_to_record_span"
        : kind === "topdown_preview" ? "csv_unix_timestamp" : "ros_record_timestamp",
      url: `/api/recordings/${recordingId}/${route}/${type}/${id}`,
    };
  };
  const analysisState = (outputs) => {
    const states = outputs.map((output) => output.state);
    if (states.includes("processing")) return "processing";
    if (states.includes("queued")) return "queued";
    if (states.includes("failed")) return "failed";
    return states.every((state) => state === "ready") ? "ready" : "not_planned";
  };
  const buildRecording = (id, name, states, options = {}) => {
    const outputs = kinds.map((kind, index) => ({
      kind,
      state: states[index],
      diagnostic: outputDiagnostic(kind, states[index]),
      job_id: null,
      artifact: states[index] === "ready" ? artifact(id, kind) : null,
    }));
    return {
      id,
      name,
      folder_path: options.folder || "demo/field-tests",
      start_time_ns: "1772312400000000000",
      duration_ns: options.durationNs || "12000000000",
      total_source_size_bytes: options.sizeBytes || "482344960",
      storage_format: "sqlite3",
      metadata_version: 5,
      message_count: options.durationNs === "0" ? "1" : "2486",
      topic_count: 12,
      ros_health: "readable",
      presentation_health: "readable",
      source_present: true,
      diagnostic: null,
      outputs,
      components: [
        { role: "metadata", condition: "readable", file_name: "metadata.yaml", size_bytes: "3821", mtime_ns: "1772312400000000000", diagnostic: null },
        { role: "rosbag", condition: "readable", file_name: "data_0.db3", size_bytes: options.sizeBytes || "482344960", mtime_ns: "1772312410000000000", diagnostic: null },
      ],
    };
  };
  const primary = buildRecording(101, "mock_field_run_01", scenario.states, scenario);
  const draft = buildRecording(102, "mock_unprepared_run", ["not_requested", "not_requested", "not_requested"], { folder: "demo/inbox", durationNs: "48000000000" });
  const recordings = [primary, draft];
  const jobs = [];
  const history = [];
  const failed = [];
  const elapsed = () => Date.now() - state.lastTransition;
  const state = { lastTransition: Date.now(), paused: false };

  const job = (recording, kind, status = "queued") => ({
    id: nextJobId++,
    recording_id: recording.id,
    recording_name: recording.name,
    kind,
    state: status,
    queued_at: now(),
    started_at: status === "running" ? now() : null,
    finished_at: null,
    queued_age_ms: 0,
    elapsed_ms: status === "running" ? 0 : null,
    active_elapsed_ms: status === "running" ? 0 : null,
    paused_ms: 0,
    runtime_ms: null,
    diagnostic: null,
    output_size_bytes: null,
    queue_position: status === "queued" ? jobs.filter((item) => item.state === "queued").length + 1 : null,
    estimate: status === "running" ? { status: "available", estimated_total_ms: 6000, remaining_ms: 6000, method: "mock_demo", sample_count: 4 } : null,
    queue_estimate: status === "queued" ? { status: "available", ready_in_ms: 6000, method: "mock_demo", sample_count: 4 } : null,
    control_state: "none",
    execution_phase: status === "running" ? "processing" : null,
    control_revision: 1,
    allowed_controls: status === "running" ? ["pause", "cancel"] : ["move_earlier", "move_later", "cancel"],
  });
  const addInitialJobs = () => {
    primary.outputs.forEach((output) => {
      if (output.state === "queued" || output.state === "processing") {
        const item = job(primary, output.kind, output.state === "processing" ? "running" : "queued");
        output.job_id = item.id;
        jobs.push(item);
      }
      if (output.state === "failed") {
        const item = job(primary, output.kind, "failed");
        item.finished_at = now();
        item.runtime_ms = 4132;
        item.diagnostic = output.diagnostic;
        item.allowed_controls = [];
        output.job_id = item.id;
        failed.push(item);
      }
    });
    if (scenario.history) {
      primary.outputs.forEach((output) => {
        const item = job(primary, output.kind, "succeeded");
        item.finished_at = now();
        item.runtime_ms = 3200;
        item.output_size_bytes = output.artifact?.size_bytes || "0";
        item.allowed_controls = [];
        history.push(item);
      });
    }
  };
  addInitialJobs();

  const updateOutput = (recordingId, kind, newState, jobId = null) => {
    const output = recordings.find((recording) => recording.id === recordingId)?.outputs.find((item) => item.kind === kind);
    if (!output) return;
    output.state = newState;
    output.diagnostic = outputDiagnostic(kind, newState);
    output.job_id = jobId;
    output.artifact = newState === "ready" ? artifact(recordingId, kind) : null;
  };
  const refreshQueue = () => {
    let position = 1;
    jobs.filter((item) => item.state === "queued").forEach((item) => {
      item.queue_position = position++;
      item.queue_estimate = { status: "available", ready_in_ms: position * 6000, method: "mock_demo", sample_count: 4 };
    });
  };
  const advance = () => {
    if (state.paused) return;
    const running = jobs.find((item) => item.state === "running");
    if (!running) {
      const next = jobs.find((item) => item.state === "queued");
      if (next && elapsed() >= 1200) {
        next.state = "running";
        next.started_at = now();
        next.elapsed_ms = 0;
        next.active_elapsed_ms = 0;
        next.queue_position = null;
        next.queue_estimate = null;
        next.estimate = { status: "available", estimated_total_ms: 6000, remaining_ms: 6000, method: "mock_demo", sample_count: 4 };
        next.execution_phase = "processing";
        next.allowed_controls = ["pause", "cancel"];
        updateOutput(next.recording_id, next.kind, "processing", next.id);
        state.lastTransition = Date.now();
      }
      refreshQueue();
      return;
    }
    const milliseconds = elapsed();
    running.elapsed_ms = milliseconds;
    running.active_elapsed_ms = milliseconds;
    running.estimate.remaining_ms = Math.max(0, 6000 - milliseconds);
    if (milliseconds >= 6000) {
      running.state = "succeeded";
      running.finished_at = now();
      running.runtime_ms = milliseconds;
      running.output_size_bytes = artifact(running.recording_id, running.kind).size_bytes;
      running.allowed_controls = [];
      running.execution_phase = null;
      updateOutput(running.recording_id, running.kind, "ready", running.id);
      history.unshift(running);
      state.lastTransition = Date.now();
    }
    refreshQueue();
  };
  const catalogDocument = () => {
    advance();
    const rows = recordings.map((recording) => ({
      id: recording.id, name: recording.name, folder_path: recording.folder_path,
      start_time_ns: recording.start_time_ns, duration_ns: recording.duration_ns,
      total_source_size_bytes: recording.total_source_size_bytes, storage_format: recording.storage_format,
      topic_count: recording.topic_count, ros_health: recording.ros_health,
      presentation_health: recording.presentation_health, diagnostic: recording.diagnostic,
      analysis_state: analysisState(recording.outputs), outputs: recording.outputs.map(({ job_id, artifact: readyArtifact, ...output }) => output),
    }));
    const counts = rows.reduce((summary, recording) => {
      summary[recording.analysis_state] = (summary[recording.analysis_state] || 0) + 1;
      return summary;
    }, {});
    return {
      scan: { generation: 1, completed_at: now(), duration_ms: 17, counts: { recordings: rows.length, readable: rows.length, damaged: 0, missing: 0, unsupported: 0, uninspectable: 0 } },
      summary: { recordings: rows.length, ready: counts.ready || 0, processing: counts.processing || 0, queued: counts.queued || 0, failed: counts.failed || 0, damaged: 0 },
      folders: [
        { path: "demo", parent_path: "", name: "demo", direct_recording_count: 0, descendant_recording_count: rows.length },
        { path: "demo/field-tests", parent_path: "demo", name: "field-tests", direct_recording_count: 1, descendant_recording_count: 1 },
        { path: "demo/inbox", parent_path: "demo", name: "inbox", direct_recording_count: 1, descendant_recording_count: 1 },
      ],
      recordings: rows,
    };
  };
  const overview = () => {
    advance();
    const current = jobs.find((item) => item.state === "running") || null;
    const queue = jobs.filter((item) => item.state === "queued");
    return {
      server_time: now(), worker_online: true, running_count: current ? 1 : 0, queued_count: queue.length,
      failed_count: failed.length, succeeded_count: history.length, canceled_count: jobs.filter((item) => item.state === "canceled").length,
      current, queue, recommended_poll_interval_ms: 900,
    };
  };
  const imuPayload = (recording) => {
    const samples = Array.from({ length: 25 }, (_, index) => {
      const time = String(Math.round((Number(recording.duration_ns) || 12e9) * index / 24));
      return [time, Math.sin(index / 3), Math.cos(index / 4), Math.sin(index / 5), 9.81 + Math.cos(index / 3), Math.sin(index / 4) * 0.5, Math.cos(index / 5) * 0.25];
    });
    const definitions = [
      ["angular_velocity_x", "angular_velocity.x", "IMU angular_velocity.x (rad/s)", "rad/s"],
      ["angular_velocity_y", "angular_velocity.y", "IMU angular_velocity.y (rad/s)", "rad/s"],
      ["angular_velocity_z", "angular_velocity.z", "IMU angular_velocity.z (rad/s)", "rad/s"],
      ["linear_acceleration_x", "linear_acceleration.x", "IMU linear_acceleration.x (m/s²)", "m/s²"],
      ["linear_acceleration_y", "linear_acceleration.y", "IMU linear_acceleration.y (m/s²)", "m/s²"],
      ["linear_acceleration_z", "linear_acceleration.z", "IMU linear_acceleration.z (m/s²)", "m/s²"],
    ];
    const series = definitions.map(([id, component, display_label, units], index) => {
      const values = samples.map((sample) => sample[index + 1]);
      return { id, component, display_label, units, column_index: index + 1, finite_sample_count: String(values.length), non_finite_sample_count: "0", minimum_value: Math.min(...values), maximum_value: Math.max(...values), available: true };
    });
    const output = recording.outputs.find((item) => item.kind === "imu_series");
    return {
      state: "ready", global_duration_ns: recording.duration_ns, diagnostic: null, poll_after_ms: null,
      artifact: { mime_type: "application/json", size_bytes: "4096", coverage_start_ns: samples[0][0], coverage_end_ns: samples.at(-1)[0], timestamp_provenance: "ros_record_timestamp", bounds: "measured", topic: "/sensors/imu", default_series_id: "angular_velocity_z", source_sample_count: String(samples.length), delivered_sample_count: String(samples.length), duplicate_timestamp_count: "0", series, reduction_method: "none", warnings: [], data_url: output.artifact.url },
      payload: { schema_version: 2, samples },
    };
  };
  const response = (body, status = 200) => ({
    ok: status >= 200 && status < 300, status,
    async json() { return body; },
  });
  const apiError = (message, status = 404) => response({ detail: { code: "mock_not_found", message } }, status);
  const parseBody = (options) => {
    try { return typeof options?.body === "string" ? JSON.parse(options.body) : {}; } catch { return {}; }
  };
  const controlResponse = (item, outcome = "updated") => ({ requested_job_id: item.id, outcome, job: item, server_time: now() });
  const mockFetch = async (input, options = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, window.location.origin);
    if (!url.pathname.startsWith("/api/")) return window.__rosbagOriginalFetch(input, options);
    const method = (options.method || "GET").toUpperCase();
    if (url.pathname === "/api/v1/catalog" && method === "GET") return response(catalogDocument());
    if (url.pathname === "/api/v1/catalog/rescan" && method === "POST") return response({ scan: catalogDocument().scan, diagnostics: [] });
    if (url.pathname === "/api/v1/recordings/prepare" && method === "POST") {
      const body = parseBody(options);
      const results = (body.recording_ids || []).map((id) => {
        const recording = recordings.find((item) => item.id === id);
        if (!recording) return { recording_id: id, outcome: "not_found", analysis_state: "not_planned", outputs: (body.output_kinds || []).map((kind) => ({ kind, outcome: "not_found", state: "not_requested", diagnostic: null, artifact_id: null, job_id: null })) };
        const outputs = (body.output_kinds || []).map((kind) => {
          const output = recording.outputs.find((item) => item.kind === kind);
          if (output.state === "unavailable") return { kind, outcome: "unavailable", state: output.state, diagnostic: output.diagnostic, artifact_id: null, job_id: null };
          if (output.state === "ready") return { kind, outcome: "ready_reused", state: output.state, diagnostic: null, artifact_id: output.artifact.id, job_id: output.job_id };
          if (!["queued", "processing"].includes(output.state)) {
            const item = job(recording, kind);
            jobs.push(item);
            updateOutput(recording.id, kind, "queued", item.id);
            state.lastTransition = Date.now();
          }
          const updated = recording.outputs.find((item) => item.kind === kind);
          return { kind, outcome: updated.state === "processing" ? "active_reused" : "queued", state: updated.state, diagnostic: null, artifact_id: null, job_id: updated.job_id };
        });
        refreshQueue();
        return { recording_id: id, outcome: "resolved", analysis_state: analysisState(recording.outputs), outputs };
      });
      return response({ recordings: results }, results.some((item) => item.outputs.some((output) => ["queued", "active_reused"].includes(output.outcome))) ? 202 : 200);
    }
    if (url.pathname === "/api/v1/processing/overview") return response(overview());
    if (url.pathname === "/api/v1/processing/jobs") {
      advance();
      const view = url.searchParams.get("view");
      const items = view === "queued" ? jobs.filter((item) => item.state === "queued")
        : view === "failed" ? failed : view === "history" ? history : jobs.filter((item) => item.state === "canceled");
      return response({ items, next_cursor: null });
    }
    const control = url.pathname.match(/^\/api\/v1\/processing\/jobs\/(\d+)\/(pause|resume|cancel|retry)$/);
    if (control && method === "POST") {
      const item = [...jobs, ...failed].find((candidate) => candidate.id === Number(control[1]));
      if (!item) return apiError("The requested mock job was not found.");
      if (control[2] === "pause") { state.paused = true; item.control_state = "paused"; item.allowed_controls = ["resume", "cancel"]; }
      if (control[2] === "resume") { state.paused = false; state.lastTransition = Date.now(); item.control_state = "none"; item.allowed_controls = ["pause", "cancel"]; }
      if (control[2] === "cancel") { item.state = "canceled"; item.finished_at = now(); item.allowed_controls = []; updateOutput(item.recording_id, item.kind, "not_requested", null); refreshQueue(); }
      if (control[2] === "retry") { const retried = job(recordings.find((recording) => recording.id === item.recording_id), item.kind); jobs.push(retried); updateOutput(item.recording_id, item.kind, "queued", retried.id); return response({ outcome: "retry_queued", state: "queued", recording_id: item.recording_id, kind: item.kind, job_id: retried.id, artifact_id: null, diagnostic: null }, 202); }
      return response(controlResponse(item));
    }
    if (url.pathname === "/api/v1/processing/jobs/reorder" && method === "POST") return response({ items: [], server_time: now() });
    if (url.pathname === "/api/v1/processing/jobs/cancel" && method === "POST") {
      const items = parseBody(options).job_ids || [];
      return response({ items: items.map((id) => {
        const item = jobs.find((candidate) => candidate.id === id);
        if (!item) return { requested_job_id: id, outcome: "not_found", job: null, server_time: now() };
        item.state = "canceled"; item.finished_at = now(); item.allowed_controls = [];
        updateOutput(item.recording_id, item.kind, "not_requested", null);
        return controlResponse(item);
      }), server_time: now() });
    }
    if (url.pathname === "/api/v1/processing/jobs/retry" && method === "POST") return response({ items: [], server_time: now() });
    const detail = url.pathname.match(/^\/api\/v1\/recordings\/(\d+)$/);
    if (detail && method === "GET") {
      advance();
      const recording = recordings.find((item) => item.id === Number(detail[1]));
      if (!recording) return apiError("The requested mock recording was not found.");
      return response({ ...recording, analysis_state: analysisState(recording.outputs) });
    }
    const imu = url.pathname.match(/^\/api\/recordings\/(\d+)\/imu-series(?:\/data\/(\d+))?$/);
    if (imu && method === "GET") {
      advance();
      const recording = recordings.find((item) => item.id === Number(imu[1]));
      if (!recording) return apiError("The requested mock recording was not found.");
      const output = recording.outputs.find((item) => item.kind === "imu_series");
      if (imu[2]) {
        if (output.state !== "ready" || String(output.artifact.id) !== imu[2]) return apiError("The mock IMU artifact is not ready.");
        return response(imuPayload(recording).payload);
      }
      if (output.state !== "ready") return response({ state: output.state, global_duration_ns: recording.duration_ns, diagnostic: output.diagnostic, artifact: null, poll_after_ms: ["queued", "processing"].includes(output.state) ? 1000 : null });
      const document = imuPayload(recording);
      return response({ state: document.state, global_duration_ns: document.global_duration_ns, diagnostic: null, artifact: document.artifact, poll_after_ms: null });
    }
    return apiError("This mock endpoint is not implemented.");
  };

  window.__rosbagOriginalFetch = window.fetch.bind(window);
  window.fetch = mockFetch;
  window.__rosbagMock = { scenario: scenarioName, scenarioNames: Object.keys(scenarios), reset() { window.location.reload(); } };
  const addSwitcher = () => {
    const host = document.createElement("label");
    host.textContent = "Mock scenario ";
    host.setAttribute("aria-label", "Mock API scenario");
    host.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:9999;padding:8px 10px;border:1px solid #64748b;border-radius:8px;background:#0f172a;color:#f8fafc;font:12px system-ui,sans-serif;box-shadow:0 3px 12px #0008";
    const select = document.createElement("select");
    select.style.cssText = "margin-left:6px;padding:3px;background:#1e293b;color:inherit;border:1px solid #64748b;border-radius:4px";
    Object.entries(scenarios).forEach(([name, item]) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = item.label;
      option.selected = name === scenarioName;
      select.append(option);
    });
    select.addEventListener("change", () => {
      const next = new URL(window.location.href);
      next.searchParams.set("mock", select.value);
      window.location.assign(next);
    });
    host.append(select);
    document.body.append(host);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addSwitcher, { once: true });
  else addSwitcher();
})();
