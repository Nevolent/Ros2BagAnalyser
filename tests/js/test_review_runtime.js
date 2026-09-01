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
  getBoundingClientRect() { return { top: 0, bottom: this.rectHeight, left: this.rectLeft, right: this.rectLeft + this.rectWidth, width: this.rectWidth, height: this.rectHeight }; }
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
    const sidebar = this.element("aside", "", null, "sidebar");
    const revealSlot = this.element("div", "folder-reveal-slot", sidebar);
    this.element("button", "expand-folders", revealSlot);
    const toolList = this.element("nav", "", sidebar, "tool-list");
    this.element("span", "", toolList, "tool-list-indicator");
    ["recordings", "analyzer", "processing"].forEach((view) => {
      const link = this.element("a", view === "analyzer" ? "analyzer-nav" : view === "recordings" ? "archive-view-button" : "", toolList, "tool-button");
      link.dataset.nav = view;
      link.dataset.view = view === "recordings" ? "archive" : view === "processing" ? "progression" : "analyzer";
      link.dataset.route = "";
      link.href = view === "recordings" ? "/" : `/${view}`;
    });
    const recordings = this.element("main", "recordings-view", null, "home-view");
    recordings.dataset.viewPanel = "recordings";
    this.element("aside", "folder-panel", recordings);
    this.element("nav", "folder-tree", recordings);
    this.element("input", "folder-search", recordings);
    this.element("button", "collapse-folders", recordings);
    this.element("div", "recordings-page", recordings, "recordings-page");
    this.element("section", "", recordings, "table-filter-bar");
    ["last-scanned", "recording-loading", "recording-empty", "recording-filter-empty", "recording-failure", "recording-failure-text", "page-buttons", "page-status", "selected-count", "selection-context"].forEach((id) => this.element("div", id, recordings));
    ["rescan-archive", "recording-retry", "prepare-selected", "previous-page", "next-page", "clear-filters", "clear-filter-menu"].forEach((id) => this.element("button", id, recordings));
    this.element("tbody", "recording-rows", recordings);
    ["recording-search", "select-all-recordings"].forEach((id) => this.element("input", id, recordings));
    const buildFilter = (key, values) => {
      const control = this.element("div", "", recordings, "recording-filter");
      control.dataset.catalogFilter = key;
      const input = this.element("input", `${key}-filter`, control);
      input.value = "all";
      const trigger = this.element("button", `${key}-filter-trigger`, control, "recording-filter-trigger");
      trigger.setAttribute("aria-expanded", "false");
      this.element("span", `${key}-filter-value`, trigger, "recording-filter-value").textContent = "All";
      const menu = this.element("div", `${key}-filter-menu`, control, "recording-filter-menu");
      menu.hidden = true;
      values.forEach(([value, label], index) => {
        const option = this.element("button", "", menu);
        option.dataset.filterValue = value;
        option.setAttribute("aria-selected", String(index === 0));
        option.textContent = label;
      });
    };
    buildFilter("health", [["all", "All"], ["readable", "Readable"], ["damaged", "Damaged"]]);
    buildFilter("analysis", [["all", "All"], ["ready", "Ready"], ["processing", "Processing"], ["queued", "Queued"], ["not_planned", "Not planned"], ["failed", "Failed"]]);
    ["recordings", "ready", "processing", "queued", "failed", "damaged"].forEach((key) => this.element("strong", `summary-${key}`, recordings));
    ["name", "recorded", "duration", "size", "health", "analysis"].forEach((key) => { const button = this.element("button", "", recordings, "table-sort"); button.dataset.sort = key; });
    ["ready", "processing", "queued", "failed", "not_planned"].forEach((key) => { const button = this.element("button", "", recordings); button.dataset.summaryAnalysis = key; });
    const damaged = this.element("button", "", recordings); damaged.dataset.summaryHealth = "damaged";

    const prepareDialog = this.element("dialog", "prepare-dialog");
    const prepareForm = this.element("form", "prepare-form", prepareDialog);
    this.element("p", "prepare-selection-summary", prepareForm);
    this.element("div", "prepare-recordings", prepareForm);
    this.element("p", "prepare-impact", prepareForm);
    ["front_preview", "topdown_preview", "imu_series"].forEach((kind) => {
      const input = this.element("input", "", prepareForm);
      input.setAttribute("name", "output_kind");
      input.value = kind;
      input.checked = true;
    });
    this.element("button", "cancel-prepare", prepareForm);
    this.element("button", "confirm-prepare", prepareForm);

    const cancelDialog = this.element("dialog", "cancel-job-dialog");
    this.element("h2", "cancel-job-title", cancelDialog);
    this.element("p", "cancel-job-copy", cancelDialog);
    this.element("button", "keep-processing", cancelDialog);
    this.element("button", "confirm-job-cancel", cancelDialog);

    const toast = this.element("aside", "operation-toast");
    this.element("strong", "operation-toast-title", toast);
    this.element("span", "operation-toast-copy", toast);
    this.element("button", "view-processing-toast", toast);
    this.element("button", "dismiss-toast", toast);

    const processing = this.element("main", "processing-view");
    processing.dataset.viewPanel = "processing";
    ["processing-notice", "processing-last-update", "current-job-host", "queue-empty", "queue-description", "failures-empty", "history-empty", "history-description"].forEach((id) => this.element("div", id, processing));
    ["refresh-processing", "live-toggle", "history-more", "move-selected-queue-up", "move-selected-queue-down", "cancel-selected-queue", "retry-selected-failures"].forEach((id) => {
      const button = this.element("button", id, processing);
      if (["move-selected-queue-up", "move-selected-queue-down", "cancel-selected-queue", "retry-selected-failures"].includes(id)) this.element("span", "", button);
    });
    this.element("span", "live-toggle-label", processing);
    this.element("input", "processing-search", processing);
    ["processing-queue-count", "processing-failed-count", "processing-history-count"].forEach((id) => this.element("strong", id, processing));
    ["queue", "failed", "history"].forEach((key) => { const button = this.element("button", "", processing); button.dataset.jobFilter = key; });
    this.element("i", "", processing, "processing-tab-indicator");
    this.element("section", "processing-queue-panel", processing);
    this.element("section", "processing-failures-panel", processing);
    this.element("section", "processing-history-panel", processing);
    this.element("tbody", "queue-rows", processing);
    this.element("tbody", "failure-rows", processing);
    this.element("tbody", "history-rows", processing);
    ["queue-selection-actions", "queue-selection-footer", "queue-selected-count", "failure-selection-actions", "failure-selection-footer", "failure-selected-count"].forEach((id) => this.element("div", id, processing));
    this.element("input", "select-all-queued", processing);
    this.element("input", "select-all-failures", processing);
    const dialog = this.element("dialog", "processing-error-dialog", processing);
    ["processing-error-title", "processing-error-copy", "processing-error-meta", "processing-error-recovery"].forEach((id) => this.element("div", id, dialog));
    ["close-processing-error", "dismiss-processing-error", "copy-processing-error", "open-processing-recording", "retry-processing-error"].forEach((id) => this.element("button", id, dialog));

    const analyzer = this.element("main", "analyzer-view");
    analyzer.dataset.viewPanel = "analyzer";
    this.element("aside", "recording-details-panel", analyzer);
    ["detail-name", "detail-recorded", "detail-duration", "detail-size", "detail-storage", "detail-messages", "detail-topics", "detail-health", "detail-error", "component-count", "component-rows", "output-rows", "analyzer-action"].forEach((id) => this.element("div", id, analyzer));
    this.buildPreview("front", analyzer);
    this.buildPreview("topdown", analyzer);
    const imuPane = this.element("section", "imu-series-pane", analyzer);
    ["imu-state-badge", "imu-message", "imu-message-title", "imu-status", "imu-graph", "imu-summary", "imu-current-value", "imu-current-time", "imu-current-state", "imu-warnings", "selected-sensor-label"].forEach((id) => this.element("div", id, imuPane));
    this.element("button", "imu-state-action", imuPane);
    const picker = this.element("div", "", imuPane, "sensor-picker");
    this.element("button", "sensor-picker-trigger", picker);
    this.element("div", "sensor-picker-menu", picker);
    const plot = this.element("div", "imu-plot", imuPane);
    this.element("canvas", "imu-canvas", plot);
    const cursor = this.element("span", "imu-cursor", plot);
    this.element("span", "imu-cursor-marker", cursor);
    const selection = this.element("span", "imu-selection", plot);
    this.element("span", "imu-selection-start", selection);
    this.element("span", "imu-selection-end", selection);
    ["chart-reset", "chart-zoom-out", "chart-zoom-in", "collapse-recording-details"].forEach((id) => this.element("button", id, analyzer));
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
  const current = { id: 31, recording_id: 7, recording_name: "run <safe>", kind: "front_preview", state: "running", control_state: "none", execution_phase: "processing", allowed_controls: ["pause", "cancel"], queued_at: "2026-08-04T12:00:00Z", started_at: "2026-08-04T12:00:02Z", finished_at: null, queued_age_ms: 4000, elapsed_ms: 2000, active_elapsed_ms: 2000, paused_elapsed_ms: 0, runtime_ms: null, diagnostic: null, output_size_bytes: null, queue_position: null, estimate: { status: "available", estimated_total_ms: 5000, remaining_ms: 3000, method: "median_rate_v1", sample_count: 3 } };
  const queued = { ...current, id: 32, state: "queued", control_state: "none", execution_phase: "queued", allowed_controls: ["move_earlier", "move_later", "cancel"], started_at: null, elapsed_ms: null, active_elapsed_ms: null, queue_position: 7, estimate: null, queue_estimate: { status: "available", ready_in_ms: 8000, sample_count: 5 } };
  return { server_time: "2026-08-04T12:00:04Z", worker_online: true, running_count: 1, queued_count: 1, failed_count: 1, succeeded_count: 2, canceled_count: 0, current, queue: [queued], recommended_poll_interval_ms: 1500, ...overrides };
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
  const rowLinks = harness.document.querySelector("#recording-rows").children.map((row) => row.querySelector("a"));
  assert.equal(rowLinks.some((link) => link.textContent === "run <script>alert(1)</script>"), true);
  assert.match(harness.document.querySelector("#folder-tree").children.at(-1).children[0].querySelector(".folder-label").textContent, /Site <north>/);
  assert.equal(harness.document.querySelectorAll(".folder-item--sample").length, 0);
  assert.equal(harness.calls.some((call) => call.url.includes("rescan") || call.url.includes("prepare")), false);
});

test("recording rows show the exact source name and the truthful Recorded column", async () => {
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
  assert.equal(row.querySelector(".recording-link").textContent, "2025_11_04_figure8");
  assert.equal(row.querySelector(".cell-sublabel"), null);
  assert.equal(row.children.length, 7);
  assert.equal(row.querySelector(".date-cell").querySelector("time").children.length, 2);
  assert.match(row.querySelector(".recording-link").getAttribute("aria-label"), /^2025_11_04_figure8\. Recorded /);
});

test("zero-duration readable recordings are qualified instead of shown as fully healthy", async () => {
  const recording = {
    ...catalogFixture().recordings[0],
    duration_ns: "0",
    message_count: "1",
  };
  const harness = createHarness("/", async () => makeResponse(catalogFixture({
    recordings: [recording],
    summary: { recordings: 1, ready: 0, processing: 0, queued: 0, failed: 0, damaged: 0 },
  })));
  await flush();
  const health = harness.document.querySelector("#recording-rows").querySelector(".status-indicator");
  assert.equal(health.getAttribute("aria-label"), "Review");
  assert.equal(health.classList.contains("table-health--warning"), true);
  assert.match(health.querySelector(".status-tooltip").textContent, /did not count messages or verify their timestamp span/);
});

test("recording status tooltips always open to the left without changing table layout", async () => {
  const harness = createHarness();
  harness.window.innerWidth = 1200;
  harness.window.innerHeight = 800;
  await flush();
  const indicator = harness.document.querySelector("#recording-rows").querySelector(".status-indicator");
  const tooltip = indicator.querySelector(".status-tooltip");
  indicator.rectLeft = 800;
  indicator.rectWidth = 30;
  indicator.rectHeight = 30;
  tooltip.rectWidth = 240;
  tooltip.rectHeight = 100;
  indicator.dispatch("pointerenter");
  assert.equal(tooltip.style.left, "550px");
  assert.ok(Number.parseFloat(tooltip.style.left) + tooltip.rectWidth < indicator.rectLeft);
});

test("recording filters use attached custom menus and update the catalog state", async () => {
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    throw new Error(url);
  });
  await flush();
  const trigger = harness.document.querySelector("#analysis-filter-trigger");
  trigger.dispatch("click");
  assert.equal(trigger.getAttribute("aria-expanded"), "true");
  assert.equal(harness.document.querySelector("#analysis-filter-menu").hidden, false);
  const ready = harness.document.querySelector('#analysis-filter-menu').querySelector('[data-filter-value="ready"]');
  ready.dispatch("click");
  assert.equal(harness.document.querySelector("#analysis-filter").value, "ready");
  assert.equal(harness.document.querySelector("#analysis-filter-value").textContent, "Ready");
  assert.equal(trigger.getAttribute("aria-expanded"), "false");
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
  assert.equal(harness.document.querySelector(".table-filter-bar").classList.contains("has-selection"), true);
  assert.equal(harness.document.querySelector("#prepare-selected").getAttribute("aria-hidden"), "false");
  vm.runInContext("catalogState.page = 2; renderRecordingTable()", harness.context);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 1);
  assert.equal(harness.document.querySelector("#selected-count").textContent, "20");
  vm.runInContext("selectFolder('site')", harness.context);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 20);
  harness.document.querySelector("#folder-search").value = "missing";
  harness.document.querySelector("#folder-search").dispatch("input");
  assert.match(harness.document.querySelector("#folder-tree").children.at(-1).textContent, /No folders found/);
});

test("collapsed folder shortcut follows the active Recordings route", async () => {
  const harness = createHarness();
  await flush();
  vm.runInContext("updateFolderPanelState(false)", harness.context);
  const slot = harness.document.querySelector("#folder-reveal-slot");
  const sidebar = harness.document.querySelector(".sidebar");
  assert.equal(slot.classList.contains("is-visible"), true);
  assert.equal(sidebar.classList.contains("has-folder-slot"), true);
  vm.runInContext("navigate('/processing')", harness.context);
  await flush();
  assert.equal(slot.classList.contains("is-visible"), false);
  assert.equal(slot.classList.contains("is-reserved"), false);
  assert.equal(sidebar.classList.contains("has-folder-slot"), false);
  assert.equal(harness.document.querySelector("#expand-folders").tabIndex, -1);
  vm.runInContext("navigate('/')", harness.context);
  await flush();
  assert.equal(slot.classList.contains("is-visible"), true);
  assert.equal(slot.classList.contains("is-reserved"), true);
  assert.equal(sidebar.classList.contains("has-folder-slot"), true);
});

test("successful explicit rescan reloads and reports the saved catalog", async () => {
  let catalogLoads = 0;
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") {
      catalogLoads += 1;
      return makeResponse(catalogFixture());
    }
    if (url === "/api/v1/catalog/rescan") return makeResponse({
      scan: { generation: 44, completed_at: "2026-08-26T21:30:20Z", duration_ms: 300, counts: { recordings: 6, readable: 5, damaged: 1, missing: 0, unsupported: 0, uninspectable: 0 } },
      diagnostics: [],
    });
    throw new Error(url);
  });
  await flush();
  await vm.runInContext("rescanCatalog()", harness.context);
  assert.equal(catalogLoads, 2);
  assert.match(harness.document.querySelector("#last-scanned").textContent, /Last scanned/);
  assert.equal(harness.document.querySelector("#rescan-archive").disabled, false);
});

test("failed explicit rescan retains rows, folder choice, selection, and safe reason", async () => {
  let scans = 0;
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    if (url === "/api/v1/catalog/rescan") { scans += 1; throw new Error("private archive detail"); }
    throw new Error(url);
  });
  await flush();
  vm.runInContext("selectFolder('site/day')", harness.context);
  const checkbox = harness.document.querySelectorAll(".row-select").find((item) => item.value === "7");
  checkbox.checked = true;
  checkbox.dispatch("change");
  await vm.runInContext("rescanCatalog()", harness.context);
  assert.equal(scans, 1);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 2);
  assert.equal(harness.document.querySelector("#selected-count").textContent, "1");
  assert.match(harness.document.querySelector("#last-scanned").textContent, /The server could not be reached/);
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
  const checkbox = harness.document.querySelectorAll(".row-select").find((item) => item.value === "7");
  checkbox.checked = true;
  checkbox.dispatch("change");
  const first = vm.runInContext("prepareSelected()", harness.context);
  const duplicate = vm.runInContext("prepareSelected()", harness.context);
  await flush();
  assert.equal(harness.calls.filter((call) => call.url === "/api/v1/recordings/prepare").length, 1);
  assert.deepEqual(JSON.parse(harness.calls.find((call) => call.url === "/api/v1/recordings/prepare").options.body), { recording_ids: [7], output_kinds: ["front_preview", "topdown_preview", "imu_series"] });
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
  const checkbox = harness.document.querySelectorAll(".row-select").find((item) => item.value === "7");
  checkbox.checked = true;
  checkbox.dispatch("change");
  await vm.runInContext("prepareSelected()", harness.context);
  assert.equal(harness.window.location.pathname, "/");
  assert.equal(harness.document.querySelector("#catalog-notice"), null);
});

test("preparation dialog submits only the frozen non-empty output subset", async () => {
  let resolvePrepare;
  const pending = new Promise((resolve) => { resolvePrepare = resolve; });
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalogFixture());
    if (url === "/api/v1/recordings/prepare") {
      await pending;
      return makeResponse({ recordings: [{ recording_id: 7, outcome: "accepted", analysis_state: "queued", outputs: ["front_preview", "imu_series"].map((kind) => ({ kind, outcome: "queued", state: "queued", diagnostic: null })) }] }, 202);
    }
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    throw new Error(url);
  });
  await flush();
  const checkbox = harness.document.querySelectorAll(".row-select").find((item) => item.value === "7");
  checkbox.checked = true;
  checkbox.dispatch("change");
  harness.document.querySelector("#prepare-selected").dispatch("click");
  assert.equal(harness.document.querySelector("#prepare-dialog").open, true);
  const outputChoices = harness.document.querySelector("#prepare-form").querySelectorAll('[name="output_kind"]');
  outputChoices[1].checked = false;
  outputChoices[1].dispatch("change");
  const submission = vm.runInContext("prepareSelected()", harness.context);
  await flush();
  const request = harness.calls.find((call) => call.url === "/api/v1/recordings/prepare");
  assert.deepEqual(JSON.parse(request.options.body), { recording_ids: [7], output_kinds: ["front_preview", "imu_series"] });
  outputChoices[2].checked = false;
  outputChoices[2].dispatch("change");
  assert.deepEqual(JSON.parse(request.options.body), { recording_ids: [7], output_kinds: ["front_preview", "imu_series"] });
  resolvePrepare();
  await submission;
  await flush();
  assert.equal(harness.window.location.pathname, "/processing");
});

test("Processing preserves authoritative queue positions, server estimates, offline state, and bounded polling", async () => {
  const harness = createHarness("/processing", async (url) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    throw new Error(url);
  });
  await flush();
  const queueRow = harness.document.querySelector("#queue-rows").children[0];
  assert.match(queueRow.children[3].textContent, /#7/);
  assert.match(queueRow.children[4].textContent, /≈ 0:08/);
  assert.match(harness.document.querySelector("#current-job-host").textContent, /Likely duration≈ 0:03/);
  assert.equal(vm.runInContext("estimateText({status: 'unavailable', sample_count: 0})", harness.context), "Not enough history");
  assert.equal(vm.runInContext("estimateText({status: 'exceeded'})", harness.context), "Estimate exceeded");
  assert.equal([...harness.timers.values()][0].delay, 1500);
  harness.document.hidden = true;
  harness.document.dispatch("visibilitychange");
  assert.equal(harness.timers.size, 0);
  vm.runInContext("processingState.overview.worker_online = false; renderProcessingOverview(); showNotice(processingElements.notice, 'Worker offline.', 'warning')", harness.context);
  assert.match(harness.document.querySelector("#processing-notice").textContent, /offline/);
});

test("Processing shows truthful empty current and queue states while idle", async () => {
  const harness = createHarness("/processing", async (url) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture({
      current: null,
      running_count: 0,
      queued_count: 0,
      queue: [],
    }));
    throw new Error(url);
  });
  await flush();
  const host = harness.document.querySelector("#current-job-host");
  assert.equal(host.hidden, false);
  assert.equal(host.querySelector(".current-job--empty") !== null, true);
  assert.match(host.textContent, /Nothing is processing currently/);
  assert.match(host.textContent, /The queue is empty/);
  assert.equal(host.querySelector('[role="progressbar"]'), null);
  assert.equal(harness.document.querySelector("#queue-rows").children.length, 0);
  assert.equal(harness.document.querySelector("#queue-empty").hidden, false);
  assert.equal(harness.document.querySelector("#processing-queue-count").textContent, "0");
  assert.equal(harness.document.querySelector("#processing-failed-count").textContent, "1");
  assert.equal(harness.document.querySelector("#processing-history-count").textContent, "2");
});

test("Processing controls use authoritative mutations, selection actions, and cancellation confirmation", async () => {
  const harness = createHarness("/processing", async (url, options) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture());
    if (url === "/api/v1/processing/jobs/31/pause") return makeResponse({ job_id: 31, outcome: "requested", job: null, server_time: "2026-08-04T12:00:05Z" });
    if (url === "/api/v1/processing/jobs/reorder") return makeResponse({ items: [{ job_id: 32, outcome: "reordered", job: null }], server_time: "2026-08-04T12:00:05Z" });
    if (url === "/api/v1/processing/jobs/32/cancel") return makeResponse({ job_id: 32, outcome: "canceled", job: null, server_time: "2026-08-04T12:00:05Z" });
    throw new Error(`${options.method || "GET"} ${url}`);
  });
  await flush();
  const pause = harness.document.querySelector("#current-job-host").querySelectorAll("button").find((button) => button.textContent === "Pause");
  pause.dispatch("click");
  await flush();
  assert.equal(harness.calls.filter((call) => call.url.endsWith("/31/pause") && call.options.method === "POST").length, 1);

  const queueCheckbox = harness.document.querySelector(".queue-row-select");
  queueCheckbox.checked = true;
  queueCheckbox.dispatch("change");
  assert.equal(harness.document.querySelector("#queue-selection-actions").hidden, false);
  harness.document.querySelector("#move-selected-queue-up").dispatch("click");
  await flush();
  const reorder = harness.calls.find((call) => call.url.endsWith("/reorder"));
  assert.deepEqual(JSON.parse(reorder.options.body), { job_ids: [32], direction: "earlier" });

  harness.document.querySelector(".queue-cancel").dispatch("click");
  assert.equal(harness.document.querySelector("#cancel-job-dialog").open, true);
  assert.equal(harness.calls.some((call) => call.url.endsWith("/32/cancel")), false);
  harness.document.querySelector("#confirm-job-cancel").dispatch("click");
  await flush();
  assert.equal(harness.calls.filter((call) => call.url.endsWith("/32/cancel") && call.options.method === "POST").length, 1);
  assert.equal(harness.document.querySelector("#queue-rows").children.length, 0);
  assert.equal(harness.document.querySelector("#processing-queue-count").textContent, "0");
});

test("empty Processing pages render truthful empty failures and history", async () => {
  const harness = createHarness("/processing", async (url) => {
    if (url === "/api/v1/processing/overview") return makeResponse(overviewFixture({ current: null, running_count: 0, queued_count: 0, failed_count: 0, succeeded_count: 0, queue: [] }));
    if (url.startsWith("/api/v1/processing/jobs?view=failed")) return makeResponse({ items: [], next_cursor: null });
    if (url.startsWith("/api/v1/processing/jobs?view=history")) return makeResponse({ items: [], next_cursor: null });
    throw new Error(url);
  });
  await flush();
  await vm.runInContext("setProcessingTab('failed')", harness.context);
  await flush();
  assert.equal(harness.document.querySelector("#failure-rows").children.length, 0);
  assert.equal(harness.document.querySelector("#failures-empty").hidden, false);
  await vm.runInContext("setProcessingTab('history')", harness.context);
  await flush();
  assert.equal(harness.document.querySelector("#history-rows").children.length, 0);
  assert.equal(harness.document.querySelector("#history-empty").hidden, false);
  assert.equal(harness.document.querySelector("#history-description").textContent, "Showing 0 completed jobs");
});

test("Recordings distinguish a partially prepared output set", async () => {
  const partial = catalogFixture();
  partial.recordings[0].outputs[0] = { ...partial.recordings[0].outputs[0], state: "ready" };
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(partial);
    throw new Error(url);
  });
  await flush();
  const indicator = harness.document.querySelector(".table-status--partial");
  assert.equal(indicator.getAttribute("aria-label"), "Partially prepared");
  assert.match(indicator.querySelector("use").getAttribute("href"), /icon-analysis-subset/);
});

test("Analysis status omits an absent optional top-down companion", async () => {
  const catalog = catalogFixture();
  catalog.recordings[0].analysis_state = "ready";
  catalog.recordings[0].outputs = [
    { kind: "front_preview", state: "ready", diagnostic: null },
    { kind: "topdown_preview", state: "unavailable", diagnostic: { code: "topdown_video_unavailable", message: "The top-down video companion is unavailable." } },
    { kind: "imu_series", state: "ready", diagnostic: null },
  ];
  const harness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") return makeResponse(catalog);
    throw new Error(url);
  });
  await flush();

  const tooltip = harness.document.querySelector(".table-status--ready").querySelector(".status-tooltip");
  assert.match(tooltip.textContent, /Front: Ready/);
  assert.match(tooltip.textContent, /IMU: Ready/);
  assert.doesNotMatch(tooltip.textContent, /Top-down/);
});

test("Analyzer shows repeated diagnostics once and hides redundant terminal badges", async () => {
  const detail = detailFixture();
  const message = "SQLite header declares a different database size.";
  detail.diagnostic = { code: "sqlite_size", message };
  detail.components[0].diagnostic = { code: "sqlite_size", message };
  detail.outputs.forEach((output) => {
    output.state = "unavailable";
    output.artifact = null;
    output.diagnostic = { code: "sqlite_size", message };
  });
  detail.analysis_state = "not_planned";
  const harness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") return makeResponse(detail);
    throw new Error(url);
  });
  await flush();
  assert.equal(harness.document.querySelector("#detail-error").textContent, message);
  assert.doesNotMatch(harness.document.querySelector("#output-rows").textContent, /SQLite header/);
  assert.doesNotMatch(harness.document.querySelector("#front-preview-pane").textContent, /SQLite header/);
  assert.doesNotMatch(harness.document.querySelector("#topdown-preview-pane").textContent, /SQLite header/);
  assert.doesNotMatch(harness.document.querySelector("#imu-series-pane").textContent, /SQLite header/);
  assert.equal(harness.document.querySelector("#front-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#imu-state-badge").hidden, true);
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
  const details = failureRow.children[2].querySelector("button");
  details.dispatch("click");
  assert.equal(harness.document.querySelector("#processing-error-dialog").open, true);
  assert.equal(harness.document.querySelector("#processing-error-copy").textContent, "Failed <without markup>");
  harness.document.querySelector("#processing-error-dialog").dispatch("cancel");
  assert.equal(harness.document.activeElement, details);
  const retry = failureRow.children.at(-1).querySelector("button");
  retry.dispatch("click");
  await flush();
  assert.equal(harness.calls.filter((call) => call.url.endsWith("/retry")).length, 1);
  await vm.runInContext("setProcessingTab('history')", harness.context);
  await flush();
  await vm.runInContext("loadProcessingPage('history', {append: true})", harness.context);
  assert.equal(harness.document.querySelector("#history-rows").children.length, 2);
  const completed = harness.document.querySelector("#history-rows").children[0].querySelector(".history-completed");
  assert.equal(completed.querySelector("time").children.length, 2);
  assert.equal(completed.querySelector("time").children[0].tagName, "strong");
  assert.equal(completed.querySelector("time").children[1].tagName, "span");
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
  const outputDetails = harness.document.querySelector("#output-rows").textContent;
  assert.match(outputDetails, /Front-camera previewMP4 · H\.264/);
  assert.match(outputDetails, /Top-down previewMP4 · H\.264/);
  assert.match(outputDetails, /IMU data bundleJSON/);
  assert.doesNotMatch(outputDetails, /coverage/i);
  assert.equal(harness.document.querySelector("#front-video").src, "/api/recordings/7/front-preview/media/101");
  assert.equal(harness.document.querySelector("#topdown-video").src, "/api/recordings/7/topdown-preview/media/102");
  assert.equal(harness.document.querySelector("#front-summary"), null);
  assert.equal(harness.document.querySelector("#front-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-state-badge").hidden, true);
  assert.equal(harness.document.querySelector("#imu-state-badge").hidden, true);
  assert.doesNotMatch(harness.document.querySelector("#imu-summary").textContent, /coverage|samples|timestamps/i);
  const graphOperations = harness.document.querySelector("#imu-canvas").context.operations;
  assert.equal(graphOperations.some(([operation]) => operation === "stroke"), true);
  assert.equal(graphOperations.filter(([operation]) => operation === "arc").length, 2);
  assert.equal(harness.document.querySelector("#sensor-picker-menu").querySelectorAll("[data-sensor]").length, 6);
  assert.match(harness.document.querySelector("#imu-warnings").children[0].textContent, /1 sample gap/);
  vm.runInContext("applyGlobalTime(0, true)", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, true);
  vm.runInContext("applyGlobalTime(5, true)", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, false);
  assert.equal(harness.document.querySelector("#front-video").currentTime, 4);
  vm.runInContext("applyGlobalTime(1, true)", harness.context);
  assert.equal(harness.document.querySelector("#imu-current-state").textContent, "");
  vm.runInContext("zoomGraph(0.5)", harness.context);
  assert.equal(vm.runInContext("reviewController.telemetry.viewEnd - reviewController.telemetry.viewStart", harness.context), 5);
  assert.equal(vm.runInContext("reviewController.clock.globalTime", harness.context), 1);
  harness.document.querySelector("#imu-plot").dispatch("pointerdown", { pointerId: 3, pointerType: "mouse", button: 0, isPrimary: true, shiftKey: true, clientX: 100 });
  harness.document.querySelector("#imu-plot").dispatch("pointerup", { pointerId: 3, pointerType: "mouse", button: 0, isPrimary: true, shiftKey: true, clientX: 350 });
  assert.equal(vm.runInContext("reviewController.telemetry.viewEnd - reviewController.telemetry.viewStart < 5", harness.context), true);
  assert.match(harness.document.querySelector("#imu-selection-start").textContent, /^170000000/);
  assert.match(harness.document.querySelector("#imu-selection-end").textContent, /^170000000/);
  harness.document.querySelector("#chart-reset").dispatch("click");
  assert.equal(vm.runInContext("reviewController.telemetry.viewEnd - reviewController.telemetry.viewStart", harness.context), 10);
  assert.equal(harness.document.querySelector("#imu-cursor-marker").hidden, false);
  harness.document.querySelector("#imu-plot").dispatch("wheel", { deltaY: 1, deltaX: 0 });
  assert.equal(vm.runInContext("reviewController.clock.globalTime > 1", harness.context), true);
  vm.runInContext("showMediaFailure('front')", harness.context);
  assert.equal(harness.document.querySelector("#front-video").hidden, true);
  assert.equal(harness.document.querySelector("#topdown-video").hidden, false);
  assert.equal(vm.runInContext("window.ImuGraph.sampleAtOrBefore(reviewController.telemetry.samples, 2).value", harness.context), null);
  const previousFrameIds = new Set(harness.frames.keys());
  vm.runInContext("setRecordingDetailsCollapsed(true, {returnFocus: false})", harness.context);
  const layoutFrameId = [...harness.frames.keys()].find((id) => !previousFrameIds.has(id));
  const layoutFrame = harness.frames.get(layoutFrameId);
  harness.frames.delete(layoutFrameId);
  layoutFrame(1000);
  assert.equal(harness.document.querySelector("#analyzer-view").classList.contains("is-details-collapsed"), true);
  assert.equal(harness.document.querySelector("#collapse-recording-details").getAttribute("aria-expanded"), "false");
});

test("recording details uses the reference's ordered height and graph-width animation", async () => {
  const harness = createHarness();
  await flush();
  const analyzer = harness.document.querySelector("#analyzer-view");
  const details = harness.document.querySelector("#recording-details-panel");
  const telemetry = harness.document.querySelector("#imu-series-pane");
  const calls = [];
  const rect = (width, height) => ({ top: 0, bottom: height, left: 0, right: width, width, height });

  details.getBoundingClientRect = () => rect(300, analyzer.classList.contains("is-details-collapsed") ? 248 : 640);
  telemetry.getBoundingClientRect = () => rect(analyzer.classList.contains("is-details-collapsed") ? 900 : 500, 300);
  const animate = (element) => (keyframes, options) => {
    calls.push({ element, keyframes, options });
    return { finished: Promise.resolve(), cancel() {} };
  };
  details.animate = animate("details");
  telemetry.animate = animate("telemetry");

  let previousFrameIds = new Set(harness.frames.keys());
  vm.runInContext("setRecordingDetailsCollapsed(true, {returnFocus: false})", harness.context);
  await flush();
  assert.deepEqual(calls.map(({ element, options }) => [element, options.duration]), [["details", 360], ["telemetry", 520]]);
  assert.equal(JSON.stringify(calls[0].keyframes), JSON.stringify([{ height: "640px" }, { height: "248px" }]));
  assert.equal(JSON.stringify(calls[1].keyframes), JSON.stringify([{ width: "500px" }, { width: "900px" }]));
  [...harness.frames.keys()].filter((id) => !previousFrameIds.has(id)).forEach((id) => {
    harness.frames.get(id)(1000);
    harness.frames.delete(id);
  });
  assert.equal(analyzer.classList.contains("is-details-collapsed"), true);
  assert.equal(details.style.height, "");
  assert.equal(telemetry.style.width, "");

  calls.length = 0;
  previousFrameIds = new Set(harness.frames.keys());
  vm.runInContext("setRecordingDetailsCollapsed(false, {returnFocus: false})", harness.context);
  await flush();
  assert.deepEqual(calls.map(({ element, options }) => [element, options.duration]), [["telemetry", 520], ["details", 360]]);
  assert.equal(JSON.stringify(calls[0].keyframes), JSON.stringify([{ width: "900px" }, { width: "500px" }]));
  assert.equal(JSON.stringify(calls[1].keyframes), JSON.stringify([{ height: "248px" }, { height: "640px" }]));
  [...harness.frames.keys()].filter((id) => !previousFrameIds.has(id)).forEach((id) => {
    harness.frames.get(id)(1000);
    harness.frames.delete(id);
  });
  assert.equal(analyzer.classList.contains("is-details-collapsed"), false);
  assert.equal(details.style.height, "");
  assert.equal(telemetry.style.width, "");
});

test("recording details resize redraws each distinct graph size at native pixel density", async () => {
  const rows = [["1000000000", 1, 2, 3, 4, 5, 6], ["9000000000", 2, 3, 4, 5, 6, 7]];
  const imu = imuFixture(rows);
  const harness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") return makeResponse(detailFixture());
    if (url === "/api/recordings/7/imu-series") return makeResponse({ state: "ready", diagnostic: null, artifact: imu.artifact });
    if (url === imu.artifact.data_url) return makeResponse(imu.payload);
    throw new Error(url);
  });
  await flush();
  const plot = harness.document.querySelector("#imu-plot");
  const canvas = harness.document.querySelector("#imu-canvas");
  const clearCount = () => canvas.context.operations.filter(([operation]) => operation === "clearRect").length;
  const initialClearCount = clearCount();

  assert.equal(canvas.style.width, "100%");
  assert.equal(canvas.style.height, "100%");
  harness.window.devicePixelRatio = 2.5;
  for (const width of [560, 640, 720, 800, 900.4]) {
    plot.rectWidth = width;
    vm.runInContext("reviewController.telemetry.resizeObserver.callback()", harness.context);
    const frameId = [...harness.frames.keys()].at(-1);
    harness.frames.get(frameId)(1000);
    harness.frames.delete(frameId);
  }

  assert.equal(clearCount(), initialClearCount + 5);
  assert.equal(vm.runInContext("reviewController.telemetry.plotWidth", harness.context), 830.4);
  assert.equal(canvas.width, 2251);

  vm.runInContext("reviewController.telemetry.resizeObserver.callback()", harness.context);
  const duplicateFrameId = [...harness.frames.keys()].at(-1);
  harness.frames.get(duplicateFrameId)(1000);
  harness.frames.delete(duplicateFrameId);
  assert.equal(clearCount(), initialClearCount + 5);
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

test("explicit graph scrubbing coalesces decoder seeks and applies the latest target", async () => {
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
  vm.runInContext("applyGlobalTime(6, true)", harness.context);
  vm.runInContext("applyGlobalTime(7, true)", harness.context);
  assert.deepEqual(video.currentTimeAssignments, [4]);

  video._currentTime = 4;
  video.dispatch("seeked");
  assert.deepEqual(video.currentTimeAssignments, [4, 6]);
});

test("transient play rejection after scrubbing retries without hiding valid media", async () => {
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
  vm.runInContext("seekGlobalTime(5)", harness.context);
  video._currentTime = 4;
  video.dispatch("seeked");
  let attempts = 0;
  video.play = () => {
    attempts += 1;
    video.paused = true;
    return attempts === 1 ? Promise.reject(new Error("AbortError")) : Promise.resolve();
  };

  harness.document.querySelector("#timeline-play").dispatch("click");
  await flush();
  assert.equal(attempts, 1);
  assert.equal(vm.runInContext("reviewController.players.front.mediaFailed", harness.context), false);
  assert.equal(video.hidden, false);

  harness.setNow(2601);
  vm.runInContext("applyGlobalTime(reviewController.clock.globalTime)", harness.context);
  await flush();
  assert.equal(attempts, 2);
  assert.equal(vm.runInContext("reviewController.players.front.mediaFailed", harness.context), false);
});

test("a stalled play promise is invalidated and retried after the bounded timeout", async () => {
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
  vm.runInContext("seekGlobalTime(5)", harness.context);
  video._currentTime = 4;
  video.dispatch("seeked");
  let attempts = 0;
  video.play = () => {
    attempts += 1;
    video.paused = false;
    return attempts === 1 ? new Promise(() => {}) : Promise.resolve();
  };

  harness.document.querySelector("#timeline-play").dispatch("click");
  assert.equal(attempts, 1);
  harness.setNow(2601);
  vm.runInContext("applyGlobalTime(reviewController.clock.globalTime)", harness.context);
  await flush();
  assert.equal(attempts, 2);
  assert.equal(vm.runInContext("reviewController.players.front.mediaFailed", harness.context), false);
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
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 7);
  assert.equal(harness.document.querySelector("#recording-rows").children.every((row) => row.classList.contains("skeleton-table-row")), true);
  vm.runInContext("navigate('/')", harness.context);
  assert.equal(harness.timers.size, 0);
  await flush();
  assert.equal(harness.calls.filter((call) => call.url === "/api/v1/catalog").length, 2);
  assert.equal(harness.document.querySelector("#recording-rows").children.length, 2);
});

test("route-sized skeletons reserve catalog, Processing, and Analyzer geometry until real responses arrive", async () => {
  let resolveCatalog;
  const catalogGate = new Promise((resolve) => { resolveCatalog = resolve; });
  const catalogHarness = createHarness("/", async (url) => {
    if (url === "/api/v1/catalog") { await catalogGate; return makeResponse(catalogFixture()); }
    throw new Error(url);
  });
  assert.equal(catalogHarness.document.querySelector("#recordings-view").classList.contains("is-skeleton-loading"), true);
  assert.equal(catalogHarness.document.querySelector("#recordings-page").getAttribute("aria-busy"), "true");
  assert.equal(catalogHarness.document.querySelector("#recording-rows").children.length, 7);
  assert.equal(catalogHarness.document.querySelector("#folder-tree").children.length, 6);
  resolveCatalog();
  await flush();
  assert.equal(catalogHarness.document.querySelector("#recordings-view").classList.contains("is-skeleton-loading"), false);
  assert.equal(catalogHarness.document.querySelector("#recording-rows").children.length, 2);

  let resolveProcessing;
  const processingGate = new Promise((resolve) => { resolveProcessing = resolve; });
  const processingHarness = createHarness("/processing", async (url) => {
    if (url === "/api/v1/processing/overview") { await processingGate; return makeResponse(overviewFixture()); }
    throw new Error(url);
  });
  assert.equal(processingHarness.document.querySelector("#processing-view").getAttribute("aria-busy"), "true");
  assert.equal(processingHarness.document.querySelector("#current-job-host").querySelector(".current-job--skeleton") !== null, true);
  assert.equal(processingHarness.document.querySelector("#queue-rows").children.length, 5);
  resolveProcessing();
  await flush();
  assert.equal(processingHarness.document.querySelector("#processing-view").getAttribute("aria-busy"), "false");
  assert.equal(processingHarness.document.querySelector("#current-job-host").querySelector(".current-job--skeleton"), null);

  const unavailableDetail = detailFixture();
  unavailableDetail.analysis_state = "not_planned";
  unavailableDetail.outputs = unavailableDetail.outputs.map((output) => ({ ...output, state: "not_requested", artifact: null }));
  let resolveDetail;
  const detailGate = new Promise((resolve) => { resolveDetail = resolve; });
  const analyzerHarness = createHarness("/recordings/7", async (url) => {
    if (url === "/api/v1/recordings/7") { await detailGate; return makeResponse(unavailableDetail); }
    throw new Error(url);
  });
  assert.equal(analyzerHarness.document.querySelector("#analyzer-view").classList.contains("is-skeleton-loading"), true);
  assert.equal(analyzerHarness.document.querySelector("#recording-details-panel").getAttribute("aria-busy"), "true");
  assert.equal(analyzerHarness.document.querySelector("#output-rows").children.length, 3);
  assert.equal(analyzerHarness.document.querySelector("#component-rows").children.length, 4);
  assert.equal(analyzerHarness.document.querySelector("#front-preview-pane").classList.contains("is-skeleton-loading"), true);
  assert.equal(analyzerHarness.document.querySelector("#imu-series-pane").classList.contains("is-skeleton-loading"), true);
  assert.equal(analyzerHarness.document.querySelector("#front-message-title").textContent, "Loading recording details");
  assert.equal(analyzerHarness.document.querySelector("#topdown-message-title").textContent, "Loading recording details");
  assert.equal(analyzerHarness.document.querySelector("#imu-message-title").textContent, "Loading recording details");
  assert.equal(analyzerHarness.document.querySelector("#front-status").textContent, "");
  assert.equal(analyzerHarness.document.querySelector("#topdown-status").textContent, "");
  assert.equal(analyzerHarness.document.querySelector("#imu-status").textContent, "");
  assert.equal(analyzerHarness.document.querySelector("#front-state-badge").hidden, true);
  assert.equal(analyzerHarness.document.querySelector("#topdown-state-badge").hidden, true);
  assert.equal(analyzerHarness.document.querySelector("#imu-state-badge").hidden, true);
  resolveDetail();
  await flush();
  assert.equal(analyzerHarness.document.querySelector("#analyzer-view").classList.contains("is-skeleton-loading"), false);
  assert.equal(analyzerHarness.document.querySelector("#output-rows").children.length, 3);
  assert.equal(analyzerHarness.document.querySelector("#output-rows").children.every((row) => !row.classList.contains("metadata-item--skeleton")), true);
});

test("initial request failures replace skeletons with truthful retryable states", async () => {
  const catalogHarness = createHarness("/", async () => { throw new Error("catalog offline"); });
  await flush();
  assert.equal(catalogHarness.document.querySelector("#recordings-view").classList.contains("is-skeleton-loading"), false);
  assert.equal(catalogHarness.document.querySelector("#recording-rows").children.length, 0);
  assert.equal(catalogHarness.document.querySelector("#recording-failure").hidden, false);

  const processingHarness = createHarness("/processing", async () => { throw new Error("processing offline"); });
  await flush();
  assert.equal(processingHarness.document.querySelector("#processing-view").classList.contains("is-skeleton-loading"), false);
  assert.match(processingHarness.document.querySelector("#current-job-host").textContent, /Processing status unavailable/);
  assert.equal(processingHarness.document.querySelector("#queue-empty").textContent, "The processing queue could not be loaded.");

  const analyzerHarness = createHarness("/recordings/7", async () => { throw new Error("detail offline"); });
  await flush();
  assert.equal(analyzerHarness.document.querySelector("#analyzer-view").classList.contains("is-skeleton-loading"), false);
  assert.equal(analyzerHarness.document.querySelector("#front-preview-pane").classList.contains("is-skeleton-loading"), false);
  assert.equal(analyzerHarness.document.querySelector("#imu-series-pane").classList.contains("is-skeleton-loading"), false);
  assert.equal(analyzerHarness.document.querySelector("#detail-error").hidden, false);
});

test("static runtime contains no mock arrays, static preview sources, fake progress interval, or unsafe markup sink", () => {
  const source = fs.readFileSync(path.join(__dirname, "../../src/rosbag_analyser/web/app.js"), "utf8");
  assert.doesNotMatch(source, /innerHTML|setInterval|mockRecordings|mockJobs|preview-(front|top)\.(png|jpg|webp)/);
  assert.match(source, /textContent/);
  assert.match(source, /AbortController/);
  assert.match(source, /routeGeneration/);
});
