"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

class FakeClassList {
  constructor(element) { this.element = element; }
  values() { return new Set(this.element.className.split(/\s+/).filter(Boolean)); }
  add(...names) { const values = this.values(); names.forEach((name) => values.add(name)); this.element.className = [...values].join(" "); }
  remove(...names) { const values = this.values(); names.forEach((name) => values.delete(name)); this.element.className = [...values].join(" "); }
  toggle(name, force) {
    const values = this.values();
    const enabled = force === undefined ? !values.has(name) : Boolean(force);
    if (enabled) values.add(name); else values.delete(name);
    this.element.className = [...values].join(" ");
    return enabled;
  }
  contains(name) { return this.values().has(name); }
}

class FakeCanvasContext {
  constructor() { this.operations = []; }
  record(name, ...values) { this.operations.push([name, ...values]); }
  setTransform(...values) { this.record("setTransform", ...values); }
  clearRect(...values) { this.record("clearRect", ...values); }
  beginPath() { this.record("beginPath"); }
  moveTo(...values) { this.record("moveTo", ...values); }
  lineTo(...values) { this.record("lineTo", ...values); }
  closePath() { this.record("closePath"); }
  stroke() { this.record("stroke"); }
  save() { this.record("save"); }
  rect(...values) { this.record("rect", ...values); }
  clip() { this.record("clip"); }
  restore() { this.record("restore"); }
  arc(...values) { this.record("arc", ...values); }
  fill() { this.record("fill"); }
  fillText(...values) { this.record("fillText", ...values); }
  createLinearGradient(...values) {
    this.record("createLinearGradient", ...values);
    return { addColorStop: (...stop) => this.record("addColorStop", ...stop) };
  }
}

function dataKey(name) {
  return name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
}

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toLowerCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.attributes = new Map();
    this.className = "";
    this.classList = new FakeClassList(this);
    this.style = {};
    this.dataset = {};
    this.id = "";
    this._textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.indeterminate = false;
    this.tabIndex = -1;
    this.href = "";
    this.src = "";
    this.title = "";
    this.onclick = null;
    this.rectWidth = 500;
    this.rectHeight = 248;
    this.rectLeft = 0;
    this.capturedPointerId = null;
    if (this.tagName === "canvas") this.context = new FakeCanvasContext();
    if (this.tagName === "video") {
      this._currentTime = 0;
      this.currentTimeAssignments = [];
      this.holdCurrentTimeAssignments = false;
      this.duration = 20;
      this.readyState = 1;
      this.paused = true;
      this.seeking = false;
    }
  }

  get currentTime() { return this._currentTime ?? 0; }
  set currentTime(value) {
    const numeric = Number(value);
    if (this.tagName === "video" && this.currentTimeAssignments) this.currentTimeAssignments.push(numeric);
    if (this.tagName !== "video" || !this.holdCurrentTimeAssignments) this._currentTime = numeric;
  }

  get textContent() { return this._textContent + this.children.map((child) => child.textContent).join(""); }
  set textContent(value) { this._textContent = String(value); this.children.forEach((child) => { child.parentNode = null; }); this.children = []; }

  append(...items) {
    items.forEach((item) => {
      if (item === null || item === undefined) return;
      item.remove();
      item.parentNode = this;
      this.children.push(item);
    });
  }
  replaceChildren(...items) { this.children.forEach((child) => { child.parentNode = null; }); this.children = []; this._textContent = ""; this.append(...items); }
  remove() {
    if (!this.parentNode) return;
    const index = this.parentNode.children.indexOf(this);
    if (index >= 0) this.parentNode.children.splice(index, 1);
    this.parentNode = null;
  }
  setAttribute(name, value) {
    const text = String(value);
    this.attributes.set(name, text);
    if (name === "id") this.id = text;
    if (name === "class") this.className = text;
    if (name.startsWith("data-")) this.dataset[dataKey(name)] = text;
  }
  getAttribute(name) {
    if (name.startsWith("data-") && dataKey(name) in this.dataset) return String(this.dataset[dataKey(name)]);
    return this.attributes.get(name) ?? null;
  }
  removeAttribute(name) { this.attributes.delete(name); if (name === "src") this.src = ""; }
  toggleAttribute(name, force) { if (force) this.setAttribute(name, ""); else this.removeAttribute(name); }
  addEventListener(name, listener) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }
  dispatch(name, overrides = {}) {
    const event = {
      target: this,
      currentTarget: this,
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      stopPropagation() {},
      ...overrides,
    };
    (this.listeners.get(name) || []).forEach((listener) => listener(event));
    if (name === "click" && this.onclick) this.onclick(event);
    return event;
  }
  matches(selector) {
    return selector.split(",").some((part) => {
      let candidate = part.trim();
      const enabledOnly = candidate.endsWith(":not(:disabled)");
      if (enabledOnly) candidate = candidate.slice(0, -":not(:disabled)".length);
      if (enabledOnly && this.disabled) return false;
      if (candidate.startsWith("#")) return this.id === candidate.slice(1);
      if (candidate.startsWith(".")) return this.classList.contains(candidate.slice(1));
      const attribute = candidate.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);
      if (attribute) {
        const actual = this.getAttribute(attribute[1]);
        return attribute[2] === undefined ? actual !== null : actual === attribute[2];
      }
      return this.tagName === candidate.toLowerCase();
    });
  }
  querySelector(selector) {
    for (const child of this.children) {
      if (child.matches(selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  querySelectorAll(selector) {
    const results = [];
    for (const child of this.children) {
      if (child.matches(selector)) results.push(child);
      results.push(...child.querySelectorAll(selector));
    }
    return results;
  }
  closest(selector) { let current = this; while (current) { if (current.matches(selector)) return current; current = current.parentNode; } return null; }
  contains(element) { return element === this || this.children.some((child) => child.contains(element)); }
  focus() { this.ownerDocument.activeElement = this; }
  getBoundingClientRect() { return { left: this.rectLeft, right: this.rectLeft + this.rectWidth, width: this.rectWidth, height: this.rectHeight }; }
  getContext(kind) { return kind === "2d" ? this.context : null; }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  load() {}
  setPointerCapture(pointerId) { this.capturedPointerId = pointerId; }
  hasPointerCapture(pointerId) { return this.capturedPointerId === pointerId; }
  releasePointerCapture(pointerId) { if (this.capturedPointerId === pointerId) this.capturedPointerId = null; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

class FakeDocument {
  constructor() {
    this.roots = [];
    this.listeners = new Map();
    this.activeElement = null;
    this.hidden = false;
    this.title = "";
    this.build();
  }
  element(tagName, id = "", parent = null, className = "") {
    const element = new FakeElement(tagName, this);
    element.id = id;
    element.className = className;
    if (parent) parent.append(element); else this.roots.push(element);
    return element;
  }
  build() {
    this.element("div", "live-region");
    ["recordings", "analyzer", "processing"].forEach((view) => {
      const link = this.element("a", view === "analyzer" ? "analyzer-nav" : "");
      link.dataset.nav = view;
      link.dataset.route = "";
      link.href = view === "recordings" ? "/" : `/${view}`;
    });
    const recordings = this.element("main", "recordings-view", null, "home-view");
    recordings.dataset.viewPanel = "recordings";
    this.element("aside", "folder-panel", recordings);
    this.element("nav", "folder-tree", recordings);
    this.element("input", "folder-search", recordings);
    this.element("button", "collapse-folders", recordings);
    this.element("button", "expand-folders", recordings);
    this.element("div", "recordings-page", recordings, "recordings-page");
    ["last-scanned", "recording-loading", "recording-empty", "recording-filter-empty", "recording-failure", "recording-failure-text", "page-buttons", "page-status", "selected-count"].forEach((id) => this.element("div", id, recordings));
    ["rescan-archive", "recording-retry", "prepare-selected", "previous-page", "next-page", "clear-filters"].forEach((id) => this.element("button", id, recordings));
    this.element("tbody", "recording-rows", recordings);
    ["recording-search", "analysis-filter", "health-filter", "select-all-recordings"].forEach((id) => this.element("input", id, recordings));
    ["recordings", "ready", "processing", "queued", "failed", "damaged"].forEach((key) => this.element("strong", `summary-${key}`, recordings));
    ["name", "recorded", "duration", "size", "health", "analysis"].forEach((key) => { const button = this.element("button", "", recordings, "table-sort"); button.dataset.sort = key; });
    ["ready", "processing", "queued", "failed", "not_planned"].forEach((key) => { const button = this.element("button", "", recordings); button.dataset.summaryAnalysis = key; });
    const damaged = this.element("button", "", recordings); damaged.dataset.summaryHealth = "damaged";

    const processing = this.element("main", "processing-view");
    processing.dataset.viewPanel = "processing";
    ["processing-notice", "processing-last-update", "current-job-host", "queue-empty", "queue-description", "failures-empty", "history-empty", "history-description"].forEach((id) => this.element("div", id, processing));
    ["refresh-processing", "live-toggle", "history-more"].forEach((id) => this.element("button", id, processing));
    this.element("span", "live-toggle-label", processing);
    this.element("input", "processing-search", processing);
    ["processing-queue-count", "processing-failed-count", "processing-history-count"].forEach((id) => this.element("strong", id, processing));
    ["queue", "failed", "history"].forEach((key) => { const button = this.element("button", "", processing); button.dataset.jobFilter = key; });
    this.element("section", "processing-queue-panel", processing);
    this.element("section", "processing-failures-panel", processing);
    this.element("section", "processing-history-panel", processing);
    this.element("tbody", "queue-rows", processing);
    this.element("tbody", "failure-rows", processing);
    this.element("tbody", "history-rows", processing);
    const dialog = this.element("dialog", "processing-error-dialog", processing);
    ["processing-error-title", "processing-error-copy", "processing-error-meta"].forEach((id) => this.element("div", id, dialog));
    ["close-processing-error", "dismiss-processing-error"].forEach((id) => this.element("button", id, dialog));

    const analyzer = this.element("main", "analyzer-view");
    analyzer.dataset.viewPanel = "analyzer";
    ["detail-name", "detail-recorded", "detail-duration", "detail-size", "detail-storage", "detail-messages", "detail-topics", "detail-health", "detail-error", "component-count", "component-rows", "output-rows", "analyzer-action"].forEach((id) => this.element("div", id, analyzer));
    this.buildPreview("front", analyzer);
    this.buildPreview("topdown", analyzer);
    const imuPane = this.element("section", "imu-series-pane", analyzer);
    ["imu-state-badge", "imu-message", "imu-message-title", "imu-status", "imu-graph", "imu-summary", "imu-current-value", "imu-current-state", "imu-warnings", "selected-sensor-label"].forEach((id) => this.element("div", id, imuPane));
    this.element("button", "imu-state-action", imuPane);
    const picker = this.element("div", "", imuPane, "sensor-picker");
    this.element("button", "sensor-picker-trigger", picker);
    this.element("div", "sensor-picker-menu", picker);
    const plot = this.element("div", "imu-plot", imuPane);
    this.element("canvas", "imu-canvas", plot);
    this.element("span", "imu-cursor", plot);
    this.element("button", "timeline-play", analyzer);
    this.element("input", "global-time-slider", analyzer);
    this.element("span", "timeline-current", analyzer);
    this.element("span", "timeline-total", analyzer);
  }
  buildPreview(prefix, parent) {
    const pane = this.element("section", `${prefix}-preview-pane`, parent);
    ["state-badge", "message", "message-title", "status", "coverage"].forEach((suffix) => this.element("div", `${prefix}-${suffix}`, pane));
    this.element("video", `${prefix}-video`, pane);
    this.element("button", `${prefix}-state-action`, pane);
    this.element("button", `${prefix}-media-retry`, pane);
  }
  createElement(tagName) { return new FakeElement(tagName, this); }
  createElementNS(_namespace, tagName) { return this.createElement(tagName); }
  querySelector(selector) {
    for (const root of this.roots) {
      if (root.matches(selector)) return root;
      const nested = root.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
  querySelectorAll(selector) {
    const results = [];
    for (const root of this.roots) {
      if (root.matches(selector)) results.push(root);
      results.push(...root.querySelectorAll(selector));
    }
    return results;
  }
  addEventListener(name, listener) { const listeners = this.listeners.get(name) || []; listeners.push(listener); this.listeners.set(name, listeners); }
  dispatch(name, overrides = {}) { (this.listeners.get(name) || []).forEach((listener) => listener({ target: this, ...overrides })); }
}

const imuDefinitions = [
  ["angular_velocity_x", "angular_velocity.x", "IMU angular_velocity.x (rad/s)", "rad/s"],
  ["angular_velocity_y", "angular_velocity.y", "IMU angular_velocity.y (rad/s)", "rad/s"],
  ["angular_velocity_z", "angular_velocity.z", "IMU angular_velocity.z (rad/s)", "rad/s"],
  ["linear_acceleration_x", "linear_acceleration.x", "IMU linear_acceleration.x (m/s²)", "m/s²"],
  ["linear_acceleration_y", "linear_acceleration.y", "IMU linear_acceleration.y (m/s²)", "m/s²"],
  ["linear_acceleration_z", "linear_acceleration.z", "IMU linear_acceleration.z (m/s²)", "m/s²"],
];

function outputFacts(state = "not_requested") {
  return ["front_preview", "topdown_preview", "imu_series"].map((kind) => ({ kind, state, diagnostic: null }));
}

function catalogFixture(overrides = {}) {
  return {
    scan: { generation: 4, completed_at: "2026-08-04T12:00:00Z", duration_ms: 42, counts: { recordings: 2, readable: 1, damaged: 1, missing: 0, unsupported: 0, uninspectable: 0 } },
    summary: { recordings: 2, ready: 0, processing: 0, queued: 0, failed: 0, damaged: 1 },
    folders: [
      { path: "site", parent_path: "", name: "Site <north>", direct_recording_count: 0, descendant_recording_count: 2 },
      { path: "site/day", parent_path: "site", name: "day & night", direct_recording_count: 2, descendant_recording_count: 2 },
    ],
    recordings: [
      { id: 7, name: "run <script>alert(1)</script>", folder_path: "site/day", start_time_ns: "1700000000000000000", duration_ns: "10000000000", total_source_size_bytes: "1048576", storage_format: "sqlite3", topic_count: 4, ros_health: "readable", presentation_health: "readable", diagnostic: null, analysis_state: "not_planned", outputs: outputFacts() },
      { id: 8, name: "damaged", folder_path: "site/day", start_time_ns: null, duration_ns: null, total_source_size_bytes: "100", storage_format: "sqlite3", topic_count: null, ros_health: "metadata_invalid", presentation_health: "damaged", diagnostic: { code: "damaged", message: "Damaged & retained" }, analysis_state: "not_planned", outputs: outputFacts("unavailable") },
    ],
    ...overrides,
  };
}

function imuFixture(rows) {
  const series = imuDefinitions.map(([id, component, displayLabel, units], index) => {
    const values = rows.map((row) => row[index + 1]);
    const finite = values.filter((value) => value !== null);
    return { id, component, display_label: displayLabel, units, column_index: index + 1, finite_sample_count: String(finite.length), non_finite_sample_count: String(values.length - finite.length), minimum_value: finite.length ? Math.min(...finite) : null, maximum_value: finite.length ? Math.max(...finite) : null, available: finite.length > 0 };
  });
  return {
    state: "ready",
    artifact: { id: 103, data_url: "/api/recordings/7/imu-series/data/103", coverage_start_ns: rows[0][0], coverage_end_ns: rows.at(-1)[0], delivered_sample_count: String(rows.length), default_series_id: "angular_velocity_z", timestamp_provenance: "ros_record_timestamp", series },
    payload: { schema_version: 2, samples: rows },
  };
}

function detailFixture() {
  const artifact = (id, kind, mime) => ({ id, mime_type: mime, size_bytes: "1024", coverage_start_ns: "1000000000", coverage_end_ns: "9000000000", timestamp_provenance: kind === "topdown_preview" ? "csv_unix_timestamp" : kind === "front_preview" ? "ros_image_header_affine_to_record_span" : "ros_record_timestamp", url: `/api/recordings/7/${kind.replaceAll("_", "-")}/${kind === "imu_series" ? "data" : "media"}/${id}` });
  return {
    id: 7, name: "real <recording>", folder_path: "site/day", start_time_ns: "1700000000000000000", duration_ns: "10000000000", total_source_size_bytes: "1048576", storage_format: "sqlite3", metadata_version: 5, message_count: "42", topic_count: 4, ros_health: "readable_with_warnings", presentation_health: "readable", source_present: true, diagnostic: null, analysis_state: "ready",
    components: [{ role: "metadata", condition: "readable", file_name: "metadata <safe>.yaml", size_bytes: "500", mtime_ns: "1", diagnostic: null }],
    outputs: [
      { kind: "front_preview", state: "ready", diagnostic: null, job_id: 1, artifact: artifact(101, "front_preview", "video/mp4") },
      { kind: "topdown_preview", state: "ready", diagnostic: null, job_id: 2, artifact: artifact(102, "topdown_preview", "video/mp4") },
      { kind: "imu_series", state: "ready", diagnostic: null, job_id: 3, artifact: artifact(103, "imu_series", "application/json") },
    ],
  };
}

function overviewFixture(overrides = {}) {
  const current = { id: 31, recording_id: 7, recording_name: "run <safe>", kind: "front_preview", state: "running", queued_at: "2026-08-04T12:00:00Z", started_at: "2026-08-04T12:00:02Z", finished_at: null, queued_age_ms: 4000, elapsed_ms: 2000, runtime_ms: null, diagnostic: null, output_size_bytes: null, queue_position: null, estimate: { status: "available", estimated_total_ms: 5000, remaining_ms: 3000, method: "median_rate_v1", sample_count: 3 } };
  const queued = { ...current, id: 32, state: "queued", started_at: null, elapsed_ms: null, queue_position: 7, estimate: null };
  return { server_time: "2026-08-04T12:00:04Z", worker_online: true, running_count: 1, queued_count: 1, failed_count: 1, succeeded_count: 2, current, queue: [queued], recommended_poll_interval_ms: 1500, ...overrides };
}

function makeResponse(body, status = 200) { return { ok: status >= 200 && status < 300, status, async json() { return body; } }; }

function createHarness(pathname = "/", responder = async (url) => {
  if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
  if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
  throw new Error(`Unexpected request ${url}`);
}) {
  const document = new FakeDocument();
  const calls = [];
  let now = 1000;
  let frameId = 0;
  let timerId = 0;
  const frames = new Map();
  const timers = new Map();
  const windowListeners = new Map();
  const window = {
    document,
    location: { pathname, origin: "http://testserver" },
    history: {
      pushState(_state, _title, target) { window.location.pathname = target; },
      replaceState(_state, _title, target) { window.location.pathname = target; },
    },
    devicePixelRatio: 1,
    ImuGraph,
    requestAnimationFrame(callback) { frameId += 1; frames.set(frameId, callback); return frameId; },
    cancelAnimationFrame(id) { frames.delete(id); },
    setTimeout(callback, delay) { timerId += 1; timers.set(timerId, { callback, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
    addEventListener(name, listener) { const listeners = windowListeners.get(name) || []; listeners.push(listener); windowListeners.set(name, listeners); },
    dispatch(name) { (windowListeners.get(name) || []).forEach((listener) => listener({ target: window })); },
  };
  const storage = new Map();
  class FakeResizeObserver { constructor(callback) { this.callback = callback; } observe() {} disconnect() {} }
  const context = vm.createContext({
    AbortController, BigInt, Date, Math, Number, URL, URLSearchParams,
    ResizeObserver: FakeResizeObserver,
    console, document, localStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    fetch: async (url, options = {}) => { calls.push({ url: String(url), options }); return responder(String(url), options, calls); },
    performance: { now: () => now }, window,
  });
  window.window = window;
  const appPath = path.join(__dirname, "../../src/rosbag_analyser/web/app.js");
  vm.runInContext(fs.readFileSync(appPath, "utf8"), context, { filename: appPath });
  return { context, document, window, calls, frames, timers, setNow(value) { now = value; } };
}

async function flush() { await new Promise((resolve) => setImmediate(resolve)); await new Promise((resolve) => setImmediate(resolve)); }

test("startup reads the saved catalog once and renders hostile values as text", async () => {
  const harness = createHarness();
  await flush();
  assert.deepEqual(harness.calls.map((call) => [call.options.method || "GET", call.url]), [["GET", "/api/v1/catalog"]]);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 2);
  assert.equal(harness.document.querySelector("#recording-rows").children[0].querySelector("a").textContent, "run <script>alert(1)</script>");
  assert.equal(harness.document.querySelector("#summary-damaged").textContent, "1");
  assert.match(harness.document.querySelector("#folder-tree").children.at(-1).children[0].querySelector(".folder-label").textContent, /Site <north>/);
  assert.equal(harness.calls.some((call) => call.url.includes("rescan") || call.url.includes("prepare")), false);
  assert.equal(vm.runInContext("recordingDisplayName('2025_11_04_figure8')", harness.context), "Figure 8");
  assert.equal(vm.runInContext("recordingDisplayName('unexpected_name')", harness.context), "unexpected_name");
});

test("recording rows show a readable dated name above the full source name and split recorded time", async () => {
  const recording = {
    ...catalogFixture().recordings[0],
    name: "2025_11_04_figure8",
    start_time_ns: "1762257600000000000",
  };
  const harness = createHarness("/", async () => makeResponse(catalogFixture({
    recordings: [recording],
    summary: { recordings: 1, ready: 0, processing: 0, queued: 0, failed: 0, damaged: 0 },
  })));
  await flush();
  const row = harness.document.querySelector("#recording-rows").children[0];
  assert.equal(row.querySelector(".recording-link").textContent, "Figure 8");
  assert.equal(row.querySelector(".cell-sublabel").textContent, "2025_11_04_figure8");
  assert.equal(row.querySelector(".date-cell").querySelector("time").children.length, 2);
});

test("folder selection, filtering, pagination, and visible selection use stable numeric IDs", async () => {
  const many = Array.from({ length: 21 }, (_, index) => ({ ...catalogFixture().recordings[0], id: index + 1, name: `run-${index + 1}` }));
  const catalog = catalogFixture({ recordings: many, summary: { recordings: 21, ready: 0, processing: 0, queued: 0, failed: 0, damaged: 0 } });
  const harness = createHarness("/", async () => makeResponse(catalog));
  await flush();
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 20);
  harness.document.querySelector("#select-all-recordings").checked = true;
  harness.document.querySelector("#select-all-recordings").dispatch("change");
  assert.equal(harness.document.querySelector("#selected-count").textContent, "20");
  vm.runInContext("catalogState.page = 2; renderRecordingTable()", harness.context);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 1);
  assert.equal(harness.document.querySelector("#selected-count").textContent, "20");
  vm.runInContext("selectFolder('site')", harness.context);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 20);
  harness.document.querySelector("#folder-search").value = "missing";
  harness.document.querySelector("#folder-search").dispatch("input");
  assert.match(harness.document.querySelector("#folder-tree").children.at(-1).textContent, /No folders found/);
});

test("failed explicit rescan retains rows, folder choice, and selection", async () => {
  let scans = 0;
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    if (url === "/api/v1/catalog/rescan") { scans += 1; throw new Error("private archive detail"); }
    throw new Error(url);
  });
  await flush();
  vm.runInContext("selectFolder('site/day')", harness.context);
  const checkbox = harness.document.querySelector("#recording-rows").children[0].querySelector(".row-select");
  checkbox.checked = true;
  checkbox.dispatch("change");
  await vm.runInContext("rescanCatalog()", harness.context);
  assert.equal(scans, 1);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 2);
  assert.equal(harness.document.querySelector("#selected-count").textContent, "1");
  assert.equal(harness.document.querySelector("#catalog-notice"), null);
});

test("Prepare selected freezes one ordered request, blocks duplicates, and opens Processing for active work", async () => {
  let resolvePrepare;
  const pending = new Promise((resolve) => { resolvePrepare = resolve; });
  const harness = createHarness("/", async (url, options) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    if (url === "/api/v1/recordings/prepare") { await pending; return makeResponse({ recordings: [{ recording_id: 7, outcome: "accepted", analysis_state: "queued", outputs: [{ kind: "front_preview", outcome: "queued", state: "queued", diagnostic: null }, { kind: "topdown_preview", outcome: "ready_reused", state: "ready", diagnostic: null }, { kind: "imu_series", outcome: "active_reused", state: "queued", diagnostic: null }] }] }, 202); }
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    throw new Error(`${options.method || "GET"} ${url}`);
  });
  await flush();
  const checkbox = harness.document.querySelector("#recording-rows").children[0].querySelector(".row-select");
  checkbox.checked = true;
  checkbox.dispatch("change");
  const first = vm.runInContext("prepareSelected()", harness.context);
  const duplicate = vm.runInContext("prepareSelected()", harness.context);
  await flush();
  assert.equal(harness.calls.filter((call) => call.url === "/api/v1/recordings/prepare").length, 1);
  assert.deepEqual(JSON.parse(harness.calls.find((call) => call.url === "/api/v1/recordings/prepare").options.body), { recording_ids: [7] });
  resolvePrepare();
  await Promise.all([first, duplicate]);
  await flush();
  assert.equal(harness.window.location.pathname, "/processing");
  assert.equal(harness.document.querySelector("#selected-count").textContent, "0");
});

test("all-ready preparation stays on Recordings and reports reuse", async () => {
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    if (url === "/api/v1/recordings/prepare") return makeResponse({ recordings: [{ recording_id: 7, outcome: "accepted", analysis_state: "ready", outputs: ["front_preview", "topdown_preview", "imu_series"].map((kind) => ({ kind, outcome: "ready_reused", state: "ready", diagnostic: null })) }] });
    throw new Error(url);
  });
  await flush();
  const checkbox = harness.document.querySelector("#recording-rows").children[0].querySelector(".row-select");
  checkbox.checked = true;
  checkbox.dispatch("change");
  await vm.runInContext("prepareSelected()", harness.context);
  assert.equal(harness.window.location.pathname, "/");
  assert.equal(harness.document.querySelector("#catalog-notice"), null);
});

test("Processing preserves FIFO positions, server estimates, offline state, and bounded polling", async () => {
  const harness = createHarness("/processing", async (url) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    throw new Error(url);
  });
  await flush();
  const queueRow = harness.document.querySelector("#queue-rows").children[0];
  assert.equal(queueRow.children[0].textContent, "7");
  assert.match(harness.document.querySelector("#current-job-host").textContent, /Approximately/);
  assert.equal(vm.runInContext("estimateText({status: 'unavailable', sample_count: 0})", harness.context), "Not enough history");
  assert.equal(vm.runInContext("estimateText({status: 'exceeded'})", harness.context), "Estimate exceeded");
  assert.equal([...harness.timers.values()][0].delay, 1500);
  harness.document.hidden = true;
  harness.document.dispatch("visibilitychange");
  assert.equal(harness.timers.size, 0);
  vm.runInContext("processingState.overview.worker_online = false; renderProcessingOverview(); showNotice(processingElements.notice, 'Worker offline.', 'warning')", harness.context);
  assert.match(harness.document.querySelector("#processing-notice").textContent, /offline/);
});

test("failure detail is safe, restores focus, retry is idempotent, and history cursors deduplicate", async () => {
  const failed = { ...overviewFixture().current, id: 44, state: "failed", finished_at: "2026-08-04T12:01:00Z", runtime_ms: 9000, diagnostic: { code: "safe_code", message: "Failed <without markup>" } };
  let historyPage = 0;
  const harness = createHarness("/processing", async (url, options) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    if (url.startsWith("/api/v1/processing/jobs?view=failed")) return makeResponse({ items: [failed], next_cursor: null });
    if (url === "/api/v1/processing/jobs/44/retry") return makeResponse({ outcome: "active_reused", state: "queued", recording_id: 7, kind: "front_preview", job_id: 45, artifact_id: null, diagnostic: null }, 202);
    if (url.startsWith("/api/v1/processing/jobs?view=history")) {
      historyPage += 1;
      return makeResponse(historyPage === 1 ? { items: [{ ...failed, id: 50, state: "succeeded", diagnostic: null, output_size_bytes: "2048" }], next_cursor: "next" } : { items: [{ ...failed, id: 50, state: "succeeded", diagnostic: null, output_size_bytes: "2048" }, { ...failed, id: 51, state: "succeeded", diagnostic: null, output_size_bytes: "4096" }], next_cursor: null });
    }
    throw new Error(`${options.method || "GET"} ${url}`);
  });
  await flush();
  const tabs = harness.document.querySelectorAll("[data-job-filter]");
  tabs[0].dispatch("keydown", { key: "ArrowRight" });
  await flush();
  assert.equal(harness.document.activeElement, tabs[1]);
  assert.equal(tabs[1].getAttribute("aria-selected"), "true");
  const failureRow = harness.document.querySelector("#failure-rows").children[0];
  const details = failureRow.children.at(-1).querySelectorAll("button")[1];
  details.dispatch("click");
  assert.equal(harness.document.querySelector("#processing-error-dialog").open, true);
  assert.equal(harness.document.querySelector("#processing-error-copy").textContent, "Failed <without markup>");
  harness.document.querySelector("#processing-error-dialog").dispatch("cancel");
  assert.equal(harness.document.activeElement, details);
  const retry = failureRow.children.at(-1).querySelectorAll("button")[0];
  retry.dispatch("click");
  await flush();
  assert.equal(harness.calls.filter((call) => call.url.endsWith("/retry")).length, 1);
  await vm.runInContext("setProcessingTab('history')", harness.context);
  await flush();
  await vm.runInContext("loadProcessingPage('history', {append: true})", harness.context);
  assert.equal(harness.document.querySelector("#history-rows").children.length, 2);
});

test("direct Analyzer route binds identity URLs, precise health, six IMU channels, gaps, coverage, and independent failure", async () => {
  const rows = [["1000000000", 1, 2, 3, 4, 5, 6], ["2000000000", 2, 3, null, 5, 6, 7], ["9000000000", 3, 4, 5, 6, 7, 8]];
  const imu = imuFixture(rows);
  const harness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") return makeResponse(detailFixture());
    if (url === "/api/recordings/7/imu-series") return makeResponse({ state: "ready", diagnostic: null, artifact: imu.artifact });
    if (url === imu.artifact.data_url) return makeResponse(imu.payload);
    throw new Error(url);
  });
  await flush();
  assert.equal(harness.document.querySelector("#detail-name").textContent, "real <recording>");
  assert.equal(harness.document.querySelector("#detail-health").textContent, "Readable with warnings");
  assert.equal(harness.document.querySelector("#detail-health").querySelector(".metadata-status--good") !== null, true);
  assert.equal(harness.document.querySelector("#detail-storage").textContent, "sqlite3");
  assert.equal(harness.document.querySelector("#front-video").src, "/api/recordings/7/front-preview/media/101");
  assert.equal(harness.document.querySelector("#topdown-video").src, "/api/recordings/7/topdown-preview/media/102");
  assert.equal(harness.document.querySelector("#front-summary"), null);
  assert.equal(harness.document.querySelector("#front-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#imu-state-badge").hidden, true);
  assert.doesNotMatch(harness.document.querySelector("#imu-summary").textContent, /coverage|samples|timestamps/i);
  assert.equal(harness.document.querySelector("#imu-canvas").context.operations.some(([operation]) => operation === "createLinearGradient"), true);
  assert.equal(harness.document.querySelector("#sensor-picker-menu").querySelectorAll("[data-sensor]").length, 6);
  assert.match(harness.document.querySelector("#imu-warnings").children[0].textContent, /1 sample gap/);
  vm.runInContext("applyGlobalTime(0, true)", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, true);
  vm.runInContext("applyGlobalTime(5, true)", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, false);
  assert.equal(harness.document.querySelector("#front-video").currentTime, 4);
  vm.runInContext("applyGlobalTime(1, true)", harness.context);
  assert.equal(harness.document.querySelector("#imu-current-state").textContent, "");
  vm.runInContext("showMediaFailure('front')", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-video").hidden, false);
  assert.equal(vm.runInContext("window.ImuGraph.sampleAtOrBefore(reviewController.telemetry.samples, 2).value", harness.context), null);
});

test("video drift correction keeps one seek in flight and retries only after its timeout", async () => {
  const rows = [["1000000000", 1, 2, 3, 4, 5, 6], ["9000000000", 2, 3, 4, 5, 6, 7]];
  const imu = imuFixture(rows);
  const harness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") return makeResponse(detailFixture());
    if (url === "/api/recordings/7/imu-series") return makeResponse({ state: "ready", diagnostic: null, artifact: imu.artifact });
    if (url === imu.artifact.data_url) return makeResponse(imu.payload);
    throw new Error(url);
  });
  await flush();
  const video = harness.document.querySelector("#front-video");
  video.holdCurrentTimeAssignments = true;
  video.currentTimeAssignments.length = 0;

  vm.runInContext("applyGlobalTime(5, true)", harness.context);
  vm.runInContext("applyGlobalTime(5.4)", harness.context);
  vm.runInContext("applyGlobalTime(5.5)", harness.context);
  assert.deepEqual(video.currentTimeAssignments, [4]);

  harness.setNow(2601);
  vm.runInContext("applyGlobalTime(5.5)", harness.context);
  assert.deepEqual(video.currentTimeAssignments, [4, 4.5]);

  video._currentTime = 4.5;
  video.dispatch("seeked");
  vm.runInContext("applyGlobalTime(5.55)", harness.context);
  assert.equal(video.currentTimeAssignments.length, 2);
  vm.runInContext("applyGlobalTime(5.7)", harness.context);
  assert.deepEqual(video.currentTimeAssignments, [4, 4.5, 4.7]);
});

test("buffering suppresses automatic correction and canplay performs one catch-up seek", async () => {
  const rows = [["1000000000", 1, 2, 3, 4, 5, 6], ["9000000000", 2, 3, 4, 5, 6, 7]];
  const imu = imuFixture(rows);
  const harness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") return makeResponse(detailFixture());
    if (url === "/api/recordings/7/imu-series") return makeResponse({ state: "ready", diagnostic: null, artifact: imu.artifact });
    if (url === imu.artifact.data_url) return makeResponse(imu.payload);
    throw new Error(url);
  });
  await flush();
  const video = harness.document.querySelector("#front-video");
  video.holdCurrentTimeAssignments = true;
  video.currentTimeAssignments.length = 0;

  vm.runInContext("applyGlobalTime(5, true)", harness.context);
  video.dispatch("waiting");
  harness.setNow(3000);
  vm.runInContext("applyGlobalTime(6)", harness.context);
  assert.deepEqual(video.currentTimeAssignments, [4]);

  video.dispatch("canplay");
  assert.deepEqual(video.currentTimeAssignments, [4, 5]);
});

test("invalid artifact identity is never attached and incomplete Analyzer links to workflow", async () => {
  const detail = detailFixture();
  detail.analysis_state = "processing";
  detail.outputs[0].artifact.url = "/private/source/video.mp4";
  detail.outputs[1] = { kind: "topdown_preview", state: "queued", diagnostic: null, job_id: 2, artifact: null };
  detail.outputs[2] = { kind: "imu_series", state: "failed", diagnostic: { code: "failed", message: "Try current workflow" }, job_id: 3, artifact: null };
  const harness = createHarness("/recordings/7", async () => makeResponse(detail));
  await flush();
  assert.equal(harness.document.querySelector("#front-video").src, "");
  assert.match(harness.document.querySelector("#front-status").textContent, /invalid/);
  assert.equal(harness.document.querySelector("#analyzer-action").querySelector("a").href, "/processing");
  assert.equal(harness.calls.length, 1);
});

test("unavailable Analyzer panes do not repeat Back to Recordings actions", async () => {
  const detail = detailFixture();
  detail.analysis_state = "not_planned";
  detail.outputs = outputFacts("unavailable");
  const harness = createHarness("/recordings/7", async () => makeResponse(detail));
  await flush();
  assert.equal(harness.document.querySelector("#front-state-action").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-state-action").hidden, true);
  assert.equal(harness.document.querySelector("#imu-state-action").hidden, true);
  assert.equal(harness.document.querySelector("#analyzer-action").querySelector("a"), null);
});

test("route changes abort stale catalog work and clean processing timers", async () => {
  let resolveCatalog;
  const deferred = new Promise((resolve) => { resolveCatalog = resolve; });
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") { await deferred; return makeResponse(catalogFixture()); }
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    throw new Error(url);
  });
  vm.runInContext("navigate('/processing')", harness.context);
  resolveCatalog();
  await flush();
  assert.equal(harness.window.location.pathname, "/processing");
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 0);
  vm.runInContext("navigate('/')", harness.context);
  assert.equal(harness.timers.size, 0);
  await flush();
  assert.equal(harness.calls.filter((call) => call.url === "/api/v1/catalog").length, 2);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 2);
});

test("static runtime contains no mock arrays, static preview sources, fake progress interval, or unsafe markup sink", () => {
  const source = fs.readFileSync(path.join(__dirname, "../../src/rosbag_analyser/web/app.js"), "utf8");
  assert.doesNotMatch(source, /innerHTML|setInterval|mockRecordings|mockJobs|preview-(front|top)\.(png|jpg|webp)/);
  assert.match(source, /textContent/);
  assert.match(source, /AbortController/);
  assert.match(source, /routeGeneration/);
});
