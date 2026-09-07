"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "../..");
const read = (name) => fs.readFileSync(path.join(root, name), "utf8");
const digest = (name) => crypto.createHash("sha256").update(fs.readFileSync(path.join(root, name))).digest("hex");
const index = read("src/rosbag_analyser/web/index.html");
const styles = read("src/rosbag_analyser/web/styles.css");
const app = read("src/rosbag_analyser/web/app.js");
const referenceIndex = read("archive/index.html");

test("the frozen authored reference remains byte-for-byte unchanged", () => {
  assert.equal(digest("archive/index.html"), "5373286fcbb810cf57052a2e93c6d7e23fa1a888100635496ca8524e488f85c0");
  assert.equal(digest("archive/styles.css"), "01eb93298827c4eb430f8e135184ad0a70904193cafa5d6dc05946195388f3d0");
  assert.equal(digest("archive/script.js"), "a5d85e834c7bf6fa5fd8c38f3b917d451ed4857f3df50e43d8e75423427246e9");
  assert.equal(digest("archive/assets/tech-trace-icon.svg"), "b2fb92cb3af87871869f2c826d7a17e4617e9572ef82c08915c15f74d4c3646a");
});

test("served shell keeps the reference icon geometry and three approved tools", () => {
  const shapes = (document, id) => {
    const symbol = document.match(new RegExp(`<symbol id="${id}"[\\s\\S]*?<\\/symbol>`))?.[0] || "";
    return [...symbol.matchAll(/<(path|circle|rect|ellipse|line|polyline)\b[^>]*>/g)]
      .map((match) => match[0].replace(/\s*\/?>$/, ">").replace(/\s+/g, " "));
  };
  [
    "icon-status-check", "icon-status-x", "icon-status-alert", "icon-status-processing",
    "icon-analysis-processing", "icon-queue", "icon-folder", "icon-folder-open",
    "icon-database", "icon-panel-open", "icon-pause", "icon-play",
  ].forEach((id) => assert.deepEqual(shapes(index, id), shapes(referenceIndex, id), id));
  assert.match(index, /class="workspace-view-stack" id="workspace-view-stack"/);
  assert.equal((index.match(/class="tool-button/g) || []).length, 3);
  assert.doesNotMatch(index, />\s*(Experiments|Files)\s*</);
});

// The user-requested 2026-09-07 isolated frontend supersedes the previous
// 1.25-scale layout assertions. Keep its authored CSS exact; API adaptations
// are tested separately in test_review_runtime.js.
test("served styles preserve the newly supplied frontend exactly", () => {
  assert.equal(digest("src/rosbag_analyser/web/styles.css"), "3ad23d6fa836b02d1ca840859f102ff52476d0b77dd8beee791eaa85f63dde35");
});

test("ported shell exposes grouped outputs and preserves real application controls", () => {
  assert.match(index, /Current processing queue grouped by recording/);
  assert.match(index, /Current processing failures grouped by recording/);
  assert.match(index, /Completed processing history grouped by recording/);
  assert.match(index, /id="clear-selection"/);
  assert.match(index, /data-filter-value="partial"/);
  assert.match(index, /id="history-more"/);
  assert.doesNotMatch(index, /id="folder-reveal-slot"/);
  assert.match(index, />Recorded</);
  for (const kind of ["front_preview", "topdown_preview", "imu_series"]) {
    assert.ok(index.includes(`name="output_kind" value="${kind}" checked`));
  }
  assert.match(app, /groupProcessingJobs/);
  assert.match(app, /animateAuthoritativeQueueOrder/);
  assert.match(app, /syncProcessingTabIndicator/);
  assert.match(app, /const left = Math\.max\(edge, anchor\.left - width - gap\);/);
  assert.doesNotMatch(app, /PROCESSING_DEMO_|mockRecordings|mockJobs|innerHTML/);
  assert.doesNotMatch(index, /mock_api\.js|preview-front\.png|preview-top\.png/);
});

test("reference motion and accessibility affordances are present with reduced-motion fallbacks", () => {
  assert.match(app, /duration: open \? 150 : 100/);
  assert.doesNotMatch(app, /inverseTransform[\s\S]*?translate3d[\s\S]*?scale/);
  assert.match(app, /runPhase\(detailsPanel, "height"[\s\S]*?runPhase\(telemetryPanel, "width"/);
  assert.match(app, /runPhase\(telemetryPanel, "width"[\s\S]*?runPhase\(detailsPanel, "height"/);
  assert.match(app, /RECORDING_DETAILS_RESIZE_DURATION = 360/);
  assert.match(app, /RECORDING_DETAILS_GRAPH_DURATION = 520/);
  assert.match(styles, /is-recording-details-transition #recording-details-panel\s*\{\s*will-change:\s*height/);
  assert.match(styles, /is-recording-details-transition #imu-series-pane\s*\{\s*will-change:\s*width/);
  assert.match(app, /resizeImuTrace\(transitionTelemetry\);/);
  assert.match(app, /telemetry\.tracePixelRatio === ratio/);
  assert.doesNotMatch(app, /Math\.min\(window\.devicePixelRatio \|\| 1, 2\)/);
  assert.match(app, /telemetry\.canvas\.style\.width = "100%";/);
  assert.doesNotMatch(app, /toolIndicatorAnimation/);
  assert.match(styles, /\.tool-button:active,[\s\S]*?transform:\s*none !important;/);
  assert.match(styles, /\.sidebar \.tool-list-indicator\s*\{[^}]*transition:\s*none !important;/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(index, /id="imu-selection-start"/);
  assert.match(index, /id="imu-cursor-marker"/);
  assert.match(index, /class="chart-help-tooltip"/);
});

test("loading placeholders reserve real view geometry and honor reduced motion", () => {
  assert.match(index, /id="main-content" aria-busy="true"/);
  assert.match(index, /class="catalog-loading-status sr-only" id="recording-loading" role="status"/);
  assert.match(app, /function renderCatalogSkeleton\(\)/);
  assert.match(app, /function renderProcessingSkeleton\(\)/);
  assert.match(app, /function createMetadataSkeletonItems\(count\)/);
  assert.match(app, /setAttribute\("aria-busy", String\(loading\)\)/);
  assert.match(styles, /@keyframes skeleton-shimmer/);
  assert.match(styles, /\.camera-card\.is-skeleton-loading \.media-message,[\s\S]*?opacity:\s*1;/);
  assert.match(styles, /\.camera-card\.is-skeleton-loading \.camera-viewport::before,[\s\S]*?display:\s*none;\s*content:\s*none;/);
  assert.match(app, /state === "loading" \? "Loading recording details" : badge/);
  assert.match(app, /\["loading", "ready", "not_requested", "unavailable", "failed"\]\.includes\(state\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?skeleton-line[\s\S]*?animation: none !important/);
});
