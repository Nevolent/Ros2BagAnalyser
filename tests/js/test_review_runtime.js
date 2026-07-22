"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  toggle(name, force) {
    if (force) this.values.add(name);
    else this.values.delete(name);
  }
}

class FakeCanvasContext {
  constructor() {
    this.operations = [];
  }

  record(name, ...values) {
    this.operations.push([name, ...values]);
  }

  setTransform(...values) { this.record("setTransform", ...values); }
  clearRect(...values) { this.record("clearRect", ...values); }
  strokeRect(...values) { this.record("strokeRect", ...values); }
  beginPath() { this.record("beginPath"); }
  moveTo(...values) { this.record("moveTo", ...values); }
  lineTo(...values) { this.record("lineTo", ...values); }
  stroke() { this.record("stroke"); }
  save() { this.record("save"); }
  rect(...values) { this.record("rect", ...values); }
  clip() { this.record("clip"); }
  restore() { this.record("restore"); }
  arc(...values) { this.record("arc", ...values); }
  fill() { this.record("fill"); }
  fillText(...values) { this.record("fillText", ...values); }
}

class FakeElement {
  constructor(tagName, ownerDocument, { fragment = false } = {}) {
    this.tagName = tagName;
    this.ownerDocument = ownerDocument;
    this.fragment = fragment;
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.attributes = new Map();
    this.classList = new FakeClassList();
    this.style = {};
    this.className = "";
    this.id = "";
    this.textContent = "";
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.width = 0;
    this.height = 0;
    this.rectWidth = 220;
    if (tagName === "canvas") this.context = new FakeCanvasContext();
    if (tagName === "video") {
      this.currentTime = 0;
      this.duration = 10;
      this.readyState = 1;
      this.paused = true;
    }
  }

  append(...items) {
    items.forEach((item) => {
      if (item.fragment) {
        [...item.children].forEach((child) => this.append(child));
        item.children = [];
        return;
      }
      item.remove();
      item.parentNode = this;
      this.children.push(item);
    });
  }

  replaceChildren(...items) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    this.append(...items);
  }

  remove() {
    if (!this.parentNode) return;
    const index = this.parentNode.children.indexOf(this);
    if (index >= 0) this.parentNode.children.splice(index, 1);
    this.parentNode = null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(name, listener) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }

  dispatch(name) {
    (this.listeners.get(name) || []).forEach((listener) => listener({ target: this }));
  }

  matches(selector) {
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    if (selector.startsWith(".")) {
      return this.className.split(/\s+/).includes(selector.slice(1));
    }
    return this.tagName === selector;
  }

  querySelector(selector) {
    for (const child of this.children) {
      if (child.matches(selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  getBoundingClientRect() {
    return { width: this.rectWidth };
  }

  getContext(kind) {
    return kind === "2d" ? this.context : null;
  }

  play() {
    this.paused = false;
    return Promise.resolve();
  }

  pause() {
    this.paused = true;
  }
}

class FakeDocument {
  constructor() {
    this.roots = ["content", "page-title", "rescan-button", "status-message"].map(
      (id) => {
        const element = new FakeElement(id === "content" ? "main" : "div", this);
        element.id = id;
        return element;
      },
    );
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }

  createDocumentFragment() {
    return new FakeElement("fragment", this, { fragment: true });
  }

  querySelector(selector) {
    for (const root of this.roots) {
      if (root.matches(selector)) return root;
      const nested = root.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
}

class FakeResizeObserver {
  observe() {}
  disconnect() {}
}

function createHarness() {
  const document = new FakeDocument();
  let currentNow = 1_000;
  let animationFrame = null;
  let animationId = 0;
  const window = {
    location: { pathname: "/recordings/7" },
    devicePixelRatio: 1,
    ImuGraph,
    setTimeout: () => 1,
    clearTimeout: () => {},
    requestAnimationFrame: (callback) => {
      animationFrame = callback;
      animationId += 1;
      return animationId;
    },
    cancelAnimationFrame: () => { animationFrame = null; },
    runAnimationFrame: (now) => {
      const callback = animationFrame;
      animationFrame = null;
      assert.ok(callback, "an animation frame should be scheduled");
      callback(now);
    },
    setNow: (now) => { currentNow = now; },
  };
  const context = vm.createContext({
    AbortController,
    ResizeObserver: FakeResizeObserver,
    console,
    document,
    fetch: async () => { throw new Error("Unexpected fetch"); },
    performance: { now: () => currentNow },
    window,
  });
  window.document = document;
  window.window = window;

  const appPath = path.join(
    __dirname,
    "../../src/rosbag_analyser/web/app.js",
  );
  const source = fs.readFileSync(appPath, "utf8");
  const bootOffset = source.lastIndexOf("\nif (recordingMatch) {");
  assert.notEqual(bootOffset, -1);
  vm.runInContext(source.slice(0, bootOffset), context, { filename: appPath });
  return { context, document, window };
}

function addReviewPanel(document) {
  const panel = document.createElement("section");
  panel.id = "camera-review-panel";
  document.querySelector("#content").append(panel);
  return panel;
}

function player(document) {
  return {
    video: document.createElement("video"),
    coverageStart: 0,
    coverageEnd: 10,
    coverageMessage: document.createElement("p"),
    mediaRetry: document.createElement("button"),
    mediaFailed: false,
    insideCoverage: false,
    playAttempt: 0,
    playPending: false,
  };
}

function addReviewPane(document, id) {
  const pane = document.createElement("article");
  pane.id = id;
  pane.setAttribute("aria-live", "polite");
  document.querySelector("#content").append(pane);
  return pane;
}

test("page loading, empty, and failure states have truthful actions", () => {
  const { context, document } = createHarness();
  context.loading = vm.runInContext(
    'renderPageLoading("Loading the saved recording catalog…")',
    context,
  );
  assert.equal(context.loading.getAttribute("aria-busy"), "true");
  assert.equal(context.loading.querySelector("h2").textContent, "Loading");

  vm.runInContext("renderArchive([])", context);
  const empty = document.querySelector(".empty-state");
  assert.ok(empty);
  assert.equal(empty.querySelector("h2").textContent, "No recordings catalogued");

  let retries = 0;
  context.retryAction = () => { retries += 1; };
  context.failure = vm.runInContext(
    'renderPageFailure("Catalog unavailable.", "Retry loading catalog", retryAction)',
    context,
  );
  context.failure.querySelector("button").dispatch("click");
  assert.equal(retries, 1);
  assert.equal(
    context.failure.querySelector(".diagnostic-block").textContent,
    "Catalog unavailable.",
  );
});

test("preview states distinguish waiting, unavailable, failure, and ready", () => {
  const { context, document } = createHarness();
  const pane = addReviewPane(document, "front-preview-pane");

  const render = (preview) => {
    context.preview = preview;
    vm.runInContext("renderPreviewState('front', 7, preview)", context);
  };

  render({ state: "not_requested", diagnostic: null, artifact: null });
  assert.equal(pane.getAttribute("aria-busy"), "false");
  assert.equal(pane.querySelector("button").textContent, "Generate front preview");

  render({ state: "queued", diagnostic: null, artifact: null, poll_after_ms: 1000 });
  assert.equal(pane.getAttribute("aria-busy"), "true");
  assert.equal(pane.querySelector("button"), null);
  assert.equal(pane.querySelector("p").textContent, "queued");

  render({ state: "processing", diagnostic: null, artifact: null, poll_after_ms: 1000 });
  assert.equal(pane.getAttribute("aria-busy"), "true");
  assert.equal(pane.querySelector("button"), null);

  render({
    state: "unavailable",
    diagnostic: { message: "The ROS source is damaged." },
    artifact: null,
  });
  assert.equal(pane.getAttribute("aria-busy"), "false");
  assert.ok(pane.querySelector(".preview-state-unavailable"));
  assert.equal(pane.querySelector("button"), null);

  render({
    state: "failed",
    diagnostic: { message: "Preview generation failed." },
    artifact: null,
  });
  assert.ok(pane.querySelector(".preview-state-failed"));
  assert.equal(pane.querySelector("button").textContent, "Retry front preview");

  render({
    state: "ready",
    diagnostic: null,
    artifact: {
      bounds: "measured",
      coverage_start_ns: "1000000000",
      coverage_end_ns: "9000000000",
      media_url: "/api/recordings/7/front-preview/media/3",
      size_bytes: "1048576",
      timestamp_provenance: "ros_record_timestamp",
      warnings: [],
    },
  });
  const coverage = pane.querySelector(".coverage-summary");
  assert.match(coverage.textContent, /Measured front coverage/);
  assert.match(coverage.textContent, /ROS record timestamps/);
  assert.match(coverage.textContent, /1\.00 MiB/);

  const topdownPane = addReviewPane(document, "topdown-preview-pane");
  context.preview = {
    state: "ready",
    diagnostic: null,
    artifact: {
      bounds: "measured",
      coverage_start_ns: "2000000000",
      coverage_end_ns: "8000000000",
      media_url: "/api/recordings/7/topdown-preview/media/4",
      size_bytes: "2048",
      timestamp_provenance: "csv_unix_timestamp",
      warnings: [],
    },
  };
  vm.runInContext("renderPreviewState('topdown', 7, preview)", context);
  assert.match(
    topdownPane.querySelector(".coverage-summary").textContent,
    /CSV Unix timestamps/,
  );
});

test("IMU unavailable and failed states remain separate and actionable", () => {
  const { context, document } = createHarness();
  const pane = addReviewPane(document, "imu-series-pane");

  context.series = {
    state: "unavailable",
    diagnostic: { message: "The configured IMU topic is absent." },
    artifact: null,
  };
  vm.runInContext("renderImuState(7, series)", context);
  assert.ok(pane.querySelector(".preview-state-unavailable"));
  assert.equal(pane.querySelector("button"), null);

  context.series = {
    state: "failed",
    diagnostic: { message: "IMU extraction failed." },
    artifact: null,
  };
  vm.runInContext("renderImuState(7, series)", context);
  assert.ok(pane.querySelector(".preview-state-failed"));
  assert.equal(pane.querySelector("button").textContent, "Retry IMU series");
});

test("a status-fetch failure is not presented as source unavailability", async () => {
  const { context, document } = createHarness();
  const pane = addReviewPane(document, "front-preview-pane");
  context.fetch = async () => { throw new Error("Database connection failed"); };

  await vm.runInContext("loadPreviewState('front', 7)", context);

  assert.equal(pane.querySelector(".preview-state").textContent, "status check failed");
  assert.ok(pane.querySelector(".preview-state-failed"));
  assert.equal(pane.querySelector("button").textContent, "Retry preview status");
  assert.equal(pane.getAttribute("aria-busy"), "false");
});

test("play, pause, and seek drive both cameras and IMU from one runtime clock", async () => {
  const { context, document, window } = createHarness();
  addReviewPanel(document);
  vm.runInContext("reviewController = createGlobalTimeline(7, 10)", context);
  const controller = vm.runInContext("reviewController", context);
  context.frontPlayer = player(document);
  context.topdownPlayer = player(document);
  context.telemetry = {
    samples: [
      { timeSeconds: 1, value: 1 },
      { timeSeconds: 4, value: 2 },
      { timeSeconds: 8, value: 3 },
    ],
    coverageStart: 1,
    coverageEnd: 8,
    cursor: document.createElement("div"),
    currentValue: document.createElement("output"),
    currentState: document.createElement("p"),
    plotLeft: 10,
    plotWidth: 100,
    units: "rad/s",
  };
  vm.runInContext(
    "reviewController.players.front = frontPlayer;"
      + "reviewController.players.topdown = topdownPlayer;"
      + "reviewController.telemetry = telemetry;"
      + "updateTransportAvailability();",
    context,
  );

  window.setNow(1_000);
  controller.playButton.dispatch("click");
  await Promise.resolve();
  assert.equal(controller.clock.playing, true);
  assert.equal(context.frontPlayer.video.paused, false);
  assert.equal(context.topdownPlayer.video.paused, false);

  window.runAnimationFrame(2_000);
  assert.equal(controller.clock.globalTime, 1);
  assert.equal(context.frontPlayer.video.currentTime, 1);
  assert.equal(context.topdownPlayer.video.currentTime, 1);
  assert.equal(context.telemetry.currentValue.textContent, "1.0000 rad/s");

  controller.playButton.dispatch("click");
  assert.equal(controller.clock.playing, false);
  assert.equal(context.frontPlayer.video.paused, true);
  assert.equal(context.topdownPlayer.video.paused, true);

  controller.slider.value = "6";
  controller.slider.dispatch("input");
  assert.equal(controller.clock.globalTime, 6);
  assert.equal(context.frontPlayer.video.currentTime, 6);
  assert.equal(context.topdownPlayer.video.currentTime, 6);
  assert.equal(context.telemetry.currentValue.textContent, "2.0000 rad/s");
  assert.equal(context.telemetry.cursor.style.left, "70px");

  controller.slider.value = "9";
  controller.slider.dispatch("input");
  assert.equal(context.telemetry.currentValue.textContent, "—");
  assert.equal(context.telemetry.currentState.textContent, "Outside IMU coverage");
});

test("outside coverage and one media failure leave other consumers usable", () => {
  const { context, document } = createHarness();
  addReviewPanel(document);
  addReviewPane(document, "front-preview-pane");
  addReviewPane(document, "topdown-preview-pane");
  vm.runInContext("reviewController = createGlobalTimeline(7, 10)", context);
  const controller = vm.runInContext("reviewController", context);
  context.frontPlayer = player(document);
  context.frontPlayer.coverageEnd = 4;
  context.topdownPlayer = player(document);
  context.topdownPlayer.coverageStart = 2;
  context.telemetry = {
    samples: [{ timeSeconds: 0, value: 1 }, { timeSeconds: 10, value: 2 }],
    coverageStart: 0,
    coverageEnd: 10,
    cursor: document.createElement("div"),
    currentValue: document.createElement("output"),
    currentState: document.createElement("p"),
    plotLeft: 10,
    plotWidth: 100,
    units: "rad/s",
  };
  vm.runInContext(
    "reviewController.players.front = frontPlayer;"
      + "reviewController.players.topdown = topdownPlayer;"
      + "reviewController.telemetry = telemetry;"
      + "updateTransportAvailability();"
      + "applyGlobalTime(8, true);",
    context,
  );

  assert.equal(controller.clock.globalTime, 8);
  assert.equal(context.frontPlayer.video.hidden, true);
  assert.equal(context.frontPlayer.coverageMessage.hidden, false);
  assert.equal(context.topdownPlayer.video.hidden, false);
  assert.equal(context.telemetry.currentValue.textContent, "1.0000 rad/s");

  vm.runInContext("showMediaFailure('topdown'); applyGlobalTime(3, true);", context);
  assert.equal(context.topdownPlayer.mediaFailed, true);
  assert.equal(context.frontPlayer.video.hidden, false);
  assert.equal(controller.playButton.disabled, false);
  assert.equal(context.telemetry.currentValue.textContent, "1.0000 rad/s");
});

test("narrow graph rendering keeps cursor aligned and draws singleton values", () => {
  const { context, document } = createHarness();
  addReviewPanel(document);
  vm.runInContext("reviewController = createGlobalTimeline(7, 10)", context);
  context.pane = document.createElement("article");
  document.querySelector("#content").append(context.pane);
  context.artifact = {
    display_label: "IMU angular_velocity.z (rad/s)",
    delivered_sample_count: "3",
    topic: "/sensors/imu",
    component: "angular_velocity.z",
    units: "rad/s",
    reduction_method: "none",
    size_bytes: "1024",
    timestamp_provenance: "ros_record_timestamp",
    bounds: "measured",
    minimum_value: -1,
    maximum_value: 1,
    warnings: [],
  };
  context.parsed = {
    samples: [
      { timeSeconds: 1, value: 1 },
      { timeSeconds: 2, value: null },
      { timeSeconds: 3, value: -1 },
    ],
    coverageStart: 1,
    coverageEnd: 3,
    minimumValue: -1,
    maximumValue: 1,
  };

  vm.runInContext("renderImuGraph(pane, artifact, parsed)", context);
  const telemetry = vm.runInContext("reviewController.telemetry", context);
  const arcs = telemetry.canvas.context.operations.filter(([name]) => name === "arc");
  assert.equal(arcs.length, 2);
  assert.equal(telemetry.canvas.style.width, "220px");
  assert.equal(telemetry.plotLeft, 48);
  assert.equal(telemetry.plotWidth, 160);
  assert.match(context.pane.querySelector("figcaption").textContent, /Measured IMU coverage/);
  assert.match(context.pane.querySelector("figcaption").textContent, /ROS record timestamps/);

  vm.runInContext("applyGlobalTime(10, true)", context);
  assert.equal(telemetry.cursor.style.left, "208px");
  assert.ok(parseFloat(telemetry.cursor.style.left) <= telemetry.plot.rectWidth);
});

test("a render-time failure leaves a visible diagnostic and retry", async () => {
  const { context, document } = createHarness();
  addReviewPanel(document);
  vm.runInContext("reviewController = createGlobalTimeline(7, 10)", context);
  context.pane = document.createElement("article");
  document.querySelector("#content").append(context.pane);
  context.artifact = {
    data_url: "/api/recordings/7/imu-series/data/3",
    coverage_start_ns: "1000000000",
    coverage_end_ns: "1000000000",
    delivered_sample_count: "1",
    finite_sample_count: "1",
    non_finite_sample_count: "0",
    display_label: "IMU angular_velocity.z (rad/s)",
    topic: "/sensors/imu",
    component: "angular_velocity.z",
    units: "rad/s",
    reduction_method: "none",
    size_bytes: "1024",
    timestamp_provenance: "ros_record_timestamp",
    bounds: "measured",
    minimum_value: 1,
    maximum_value: 1,
    warnings: [],
  };
  context.fetch = async () => ({
    ok: true,
    json: async () => ({ schema_version: 1, samples: [["1000000000", 1]] }),
  });
  context.ResizeObserver = class {
    constructor() { throw new Error("ResizeObserver failed"); }
  };

  await vm.runInContext("loadReadyImuGraph(7, pane, artifact)", context);

  const diagnostic = context.pane.querySelector(".diagnostic-block");
  assert.ok(diagnostic);
  assert.equal(diagnostic.textContent, "Graph data could not be loaded.");
  assert.equal(context.pane.querySelector("button").textContent, "Reload graph data");
  assert.equal(vm.runInContext("reviewController.telemetry", context), null);
  assert.equal(context.pane.getAttribute("aria-busy"), "false");
});
