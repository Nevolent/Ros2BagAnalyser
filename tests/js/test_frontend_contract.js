"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "../..");
const read = (name) => fs.readFileSync(path.join(root, name), "utf8");
const index = read("src/rosbag_analyser/web/index.html");
const styles = read("src/rosbag_analyser/web/styles.css");
const app = read("src/rosbag_analyser/web/app.js");

test("served shell exposes three tools and defined SVG icons", () => {
  const symbols = new Set([...index.matchAll(/<symbol id="([^"]+)"/g)].map((match) => match[1]));
  const references = [...index.matchAll(/<use href="#([^"]+)"/g)].map((match) => match[1]);
  assert.ok(references.length > 0);
  for (const id of references) assert.ok(symbols.has(id), `Missing icon: ${id}`);
  assert.match(index, /class="workspace-view-stack" id="workspace-view-stack"/);
  assert.equal((index.match(/class="tool-button/g) || []).length, 3);
  assert.doesNotMatch(index, />\s*(Experiments|Files)\s*</);
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

test("motion and accessibility affordances are present with reduced-motion fallbacks", () => {
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
