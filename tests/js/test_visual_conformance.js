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

test("Recordings and Processing retain the approved reference hierarchy with the reviewed Recorded column", () => {
  const recordingsTable = index.match(/<table class="rosbag-table">[\s\S]*?<\/table>/)?.[0] || "";
  assert.match(recordingsTable, />Recorded</);
  assert.match(recordingsTable, /data-sort="name" aria-sort="none"/);
  assert.match(recordingsTable, /class="recordings-col-metadata recordings-col-recorded"/);
  assert.doesNotMatch(index.match(/<section class="table-filter-bar"[\s\S]*?<\/section>/)?.[0] || "", /<select/);
  assert.match(index, /id="analysis-filter-menu" role="listbox"/);
  assert.match(index, /<symbol id="icon-analysis-subset"[\s\S]*?M10 7h8M10 12h8M10 17h8[\s\S]*?<\/symbol>/);
  assert.doesNotMatch(index, /id="icon-analysis-partial"/);
  assert.match(styles, /\.recording-filter-menu\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?top:\s*calc\(100% \+ 5px\)/);
  assert.match(styles, /\.status-tooltip\s*\{[\s\S]*?position:\s*fixed;/);
  assert.match(styles, /#recordings-view :focus-visible\s*\{[\s\S]*?outline:\s*0;/);
  assert.match(styles, /\.prepare-selected-button__label\s*\{\s*white-space:\s*nowrap/);
  assert.match(styles, /\.folder-children::before\s*\{[\s\S]*?width:\s*\.5px !important;[\s\S]*?opacity:\s*\.72;/);
  assert.match(styles, /\.folder-parent:not\(\.is-active\):hover\s*\{\s*color:\s*var\(--text-soft\) !important/);
  assert.match(app, /const shouldShow = collapsed && currentRoute\?\.view === "recordings"/);
  assert.match(styles, /\.home-view\s*\{[\s\S]*?grid-template-columns:\s*var\(--folders-width\) minmax\(0, 1fr\)/);
  assert.match(styles, /\.home-view\.is-folders-collapsed\s*\{\s*grid-template-columns:\s*0 minmax\(0, 1fr\)/);
  assert.doesNotMatch(styles, /\.recordings-col-selection\s*\{\s*width:\s*calc\(var\(--folders-width\)/);
  assert.doesNotMatch(styles, /#recordings-view \.rosbag-table th:nth-child\(2\),[\s\S]*?padding-left:\s*6px/);
  assert.match(styles, /\.rosbag-table th:nth-child\(n \+ 2\) \.table-sort::after\s*\{[\s\S]*?position:\s*static !important;[\s\S]*?margin-left:\s*5px !important;/);
  assert.match(app, /setFolderPanel\(true,\s*\{\s*returnFocus:\s*false\s*\}\);/);
  assert.doesNotMatch(app, /localStorage\.getItem\("tectrace-folders"\)/);
  assert.match(styles, /--recorded-column-width:\s*var\(--metadata-column-width\);/);
  assert.match(styles, /\.rosbag-table th:nth-child\(4\),[\s\S]*?\.rosbag-table td:nth-child\(4\)\s*\{\s*text-align:\s*left;/);
  assert.match(styles, /\.table-status--ready,[\s\S]*?\.table-status--partial\s*\{\s*color:\s*var\(--status-success\);/);
  assert.match(index, /id="clear-filter-menu" hidden>Clear filters/);
  assert.ok(index.indexOf('id="current-job-host"') < index.indexOf('class="processing-tabs status-strip"'));
  assert.match(index, /id="processing-search" type="search" hidden/);
  assert.match(index, /id="processing-error-recovery"/);
  assert.match(app, /animateAuthoritativeQueueOrder/);
  assert.match(app, /syncProcessingTabIndicator/);
  assert.match(styles, /\.processing-tabs button\[aria-selected="true"\]::after/);
  assert.match(app, /Nothing is processing currently/);
  assert.match(app, /formatHistoryCompletion/);
});

test("effective visual tokens and graph renderer match the neutral reference treatment", () => {
  assert.match(styles, /--rail-width:\s*56px/);
  assert.match(styles, /--folders-width:\s*228px/);
  assert.match(styles, /--accent:\s*#f4f4f5/);
  assert.match(styles, /--chart-accent:\s*#f4f4f5/);
  assert.match(styles, /\.rosbag-table\s*\{\s*min-width:\s*760px/);
  assert.match(styles, /#analyzer-view \.imu-cursor\s*\{\s*top:\s*30px;\s*bottom:\s*30px/);
  assert.doesNotMatch(app, /#a7cefb|rgba\(167,\s*206,\s*251/);
  assert.match(app, /const bottom = 30/);
  assert.match(app, /Math\.max\(full \* 0\.04, 0\.001\)/);
  assert.match(app, /zoomGraph\(0\.625\)/);
  assert.match(app, /zoomGraph\(1\.6\)/);
  assert.match(app, /rgba\(244, 244, 245, 0\.22\)/);
  assert.match(styles, /\.chart-zoom-glyph\s*\{[^}]*width:\s*10px;[^}]*height:\s*10px;[^}]*\}/);
  assert.doesNotMatch(styles, /\.chart-zoom-glyph\s*\{[^}]*border:/);
  assert.match(styles, /#analyzer-view \.metadata-section:last-of-type\s*\{\s*border-bottom:\s*0;/);
  assert.match(app, /OUTPUT_FORMAT_LABELS/);
  assert.doesNotMatch(app, /artifact\.mime_type\} · coverage/);
});

test("reference motion and accessibility affordances are present with reduced-motion fallbacks", () => {
  assert.match(app, /duration: open \? 150 : 100/);
  assert.match(app, /duration: 260/);
  assert.doesNotMatch(app, /inverseTransform[\s\S]*?translate3d[\s\S]*?scale/);
  assert.match(app, /runPhase\(detailsPanel, "height"[\s\S]*?runPhase\(telemetryPanel, "width"/);
  assert.match(app, /runPhase\(telemetryPanel, "width"[\s\S]*?runPhase\(detailsPanel, "height"/);
  assert.match(app, /RECORDING_DETAILS_RESIZE_DURATION = 360/);
  assert.match(app, /RECORDING_DETAILS_GRAPH_DURATION = 520/);
  assert.match(styles, /is-recording-details-transition #recording-details-panel\s*\{\s*will-change:\s*height/);
  assert.match(styles, /is-recording-details-transition #imu-series-pane\s*\{\s*will-change:\s*width/);
  assert.match(app, /duration: 280/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(index, /id="imu-selection-start"/);
  assert.match(index, /id="imu-cursor-marker"/);
  assert.match(index, /class="chart-help-tooltip"/);
});
