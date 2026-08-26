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
  assert.match(styles, /\.recording-filter-menu\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?top:\s*calc\(100% \+ 6.25px\)/);
  assert.match(styles, /\.status-tooltip\s*\{[\s\S]*?position:\s*fixed;/);
  assert.match(styles, /#recordings-view :focus-visible\s*\{[\s\S]*?outline:\s*0;/);
  assert.match(styles, /\.prepare-selected-button__label\s*\{\s*white-space:\s*nowrap/);
  assert.match(styles, /\.folder-children::before\s*\{[\s\S]*?width:\s*0\.625px !important;[\s\S]*?opacity:\s*\.72;/);
  assert.match(styles, /\.folder-parent:not\(\.is-active\):hover\s*\{\s*color:\s*var\(--text-soft\) !important/);
  assert.match(app, /const shouldShow = collapsed && currentRoute\?\.view === "recordings"/);
  assert.match(styles, /\.home-view\s*\{[\s\S]*?grid-template-columns:\s*var\(--folders-width\) minmax\(0, 1fr\)/);
  assert.match(styles, /\.home-view\.is-folders-collapsed\s*\{\s*grid-template-columns:\s*0 minmax\(0, 1fr\)/);
  assert.doesNotMatch(styles, /\.recordings-col-selection\s*\{\s*width:\s*calc\(var\(--folders-width\)/);
  assert.match(styles, /#recordings-view \.rosbag-table th:nth-child\(2\),[\s\S]*?padding-left:\s*12.5px !important/);
  assert.match(styles, /--metadata-column-width:\s*clamp\(120px,\s*8\.75vw,\s*157.5px\)/);
  assert.match(styles, /#recordings-view \.recording-link:hover\s*\{\s*color:\s*var\(--text-soft\);/);
  assert.match(styles, /\.folder-item,[\s\S]*?\.folder-parent\s*\{\s*height:\s*30px;/);
  assert.match(styles, /#recordings-view \.recording-link,[\s\S]*?font-weight:\s*520;/);
  assert.match(styles, /\.recordings-header \.recordings-clear-filters,[\s\S]*?color:\s*var\(--status-danger\);/);
  assert.doesNotMatch(app, /SAMPLE_EMPTY_FOLDERS|Example folder [ABC]|__sample_empty__/);
  assert.match(styles, /\.rosbag-table th:nth-child\(n \+ 2\) \.table-sort::after\s*\{[\s\S]*?position:\s*static !important;[\s\S]*?margin-left:\s*6.25px !important;/);
  assert.match(app, /setFolderPanel\(true,\s*\{\s*returnFocus:\s*false\s*\}\);/);
  assert.doesNotMatch(app, /localStorage\.getItem\("tectrace-folders"\)/);
  assert.match(styles, /--recorded-column-width:\s*calc\(var\(--metadata-column-width\) \+ 37.5px\);/);
  assert.match(styles, /#recordings-view \.rosbag-table \.recordings-col-selection\s*\{\s*width:\s*45px;/);
  assert.match(styles, /#recordings-view \.rosbag-table th:nth-child\(n \+ 2\),[\s\S]*?width:\s*auto;/);
  assert.match(styles, /#recordings-view \.recording-link,[\s\S]*?color:\s*var\(--text\);/);
  assert.match(styles, /#recordings-view \.rosbag-table th:nth-child\(n \+ 3\),[\s\S]*?text-align:\s*left;/);
  assert.match(styles, /#recordings-view \.rosbag-table th:nth-child\(n \+ 3\) \.table-sort\s*\{[\s\S]*?width:\s*max-content !important;[\s\S]*?justify-content:\s*flex-start !important;/);
  assert.match(styles, /#recordings-view \.rosbag-table th:nth-child\(n \+ 3\) \.table-sort::after\s*\{[\s\S]*?position:\s*static !important;[\s\S]*?margin-left:\s*5px !important;/);
  assert.match(styles, /\.sidebar\s*\{[\s\S]*?--sidebar-button-size:\s*45px;/);
  assert.match(styles, /\.sidebar \.tool-button,[\s\S]*?width:\s*var\(--sidebar-button-size\);/);
  assert.match(styles, /\.sidebar \.expand-folders\s*\{\s*margin:\s*0;/);
  assert.match(styles, /#recordings-view \.folder-search,[\s\S]*?border-color:\s*var\(--line-subtle\)/);
  assert.match(styles, /#recordings-view \.rosbag-table \.table-health--readable\s*\{\s*color:\s*#82ee9b;/);
  assert.match(styles, /#recordings-view \.rosbag-table \.table-health--unreadable\s*\{\s*color:\s*#ff8b82;/);
  assert.match(styles, /\.table-status--ready,[\s\S]*?\.table-status--partial\s*\{\s*color:\s*var\(--status-success\);/);
  assert.match(index, /class="clear-filter-button recordings-clear-filters" type="button" id="clear-filter-menu" hidden/);
  assert.ok(index.indexOf('id="prepare-selected"') < index.indexOf('class="panel home-table-panel"'));
  assert.match(index, /class="selection-context" id="selection-context" hidden>[\s\S]*id="selected-count"/);
  assert.match(app, /classList\.toggle\("has-selection", catalogState\.selectedIds\.size > 0\)/);
  assert.match(styles, /#recordings-view \.folder-item,[\s\S]*?height:\s*27.5px;[\s\S]*?margin-block:\s*1.25px;[\s\S]*?border-radius:\s*7.5px;/);
  assert.match(styles, /#recordings-view \.folder-search,[\s\S]*?border-color:\s*#303234;/);
  assert.match(styles, /#recordings-view \.folder-search input\s*\{\s*color:\s*var\(--text-soft\);/);
  assert.match(styles, /#recordings-view \.rosbag-table \.date-cell time\s*\{\s*align-items:\s*flex-start;/);
  assert.match(styles, /#recordings-view \.table-footer\s*\{\s*margin-top:\s*-6.25px;/);
  assert.match(styles, /\.recording-filter:hover,[\s\S]*?\.recording-filter:focus-within\s*\{[\s\S]*?background:\s*var\(--folder-hover\);/);
  assert.match(styles, /\.prepare-dialog::backdrop\s*\{[\s\S]*?background:\s*rgba\(20, 20, 20, \.78\);/);
  assert.match(styles, /\.prepare-dialog fieldset label\s*\{[\s\S]*?grid-template-columns:\s*17.5px minmax\(0, 1fr\);[\s\S]*?gap:\s*16.25px;/);
  assert.match(styles, /\.prepare-dialog fieldset input\s*\{[\s\S]*?width:\s*17.5px;[\s\S]*?height:\s*17.5px;/);
  assert.match(app, /const left = Math\.max\(edge, anchor\.left - width - gap\);/);
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
  assert.match(styles, /--interface-scale:\s*1\.25;/);
  assert.match(app, /const INTERFACE_SCALE = 1\.25;/);
  assert.doesNotMatch(styles, /(?:^|[;{]\s*)zoom\s*:/m);
  const scaledBreakpoints = new Set([
    525, 750, 875, 876.25, 900, 1025, 1123.75, 1125, 1225, 1312.5, 1313.75, 2250,
  ]);
  const renderedBreakpoints = [...styles.matchAll(/@media[^{\n]*/g)]
    .flatMap((query) => [...query[0].matchAll(/(?:min|max)-width:\s*([\d.]+)px/g)])
    .map((match) => Number(match[1]));
  assert.ok(renderedBreakpoints.length > 0);
  assert.ok(renderedBreakpoints.every((breakpoint) => scaledBreakpoints.has(breakpoint)));
  assert.match(styles, /--rail-width:\s*70px/);
  assert.match(styles, /@media \(min-width:\s*1313\.75px\)[\s\S]*?--folders-width:\s*315px/);
  assert.match(styles, /@media \(max-width:\s*1312\.5px\)[\s\S]*?--folders-width:\s*300px/);
  assert.match(styles, /--accent:\s*#f4f4f5/);
  assert.match(styles, /--chart-accent:\s*#f4f4f5/);
  assert.match(styles, /\.rosbag-table\s*\{\s*min-width:\s*950px/);
  assert.match(styles, /#analyzer-view \.imu-cursor\s*\{\s*top:\s*37.5px;\s*bottom:\s*37.5px/);
  assert.doesNotMatch(app, /#a7cefb|rgba\(167,\s*206,\s*251/);
  assert.match(app, /const bottom = interfacePixels\(30\)/);
  assert.match(app, /Math\.max\(full \* 0\.04, 0\.001\)/);
  assert.match(app, /zoomGraph\(0\.625\)/);
  assert.match(app, /zoomGraph\(1\.6\)/);
  assert.match(app, /rgba\(244, 244, 245, 0\.22\)/);
  assert.match(styles, /\.chart-zoom-glyph\s*\{[^}]*width:\s*12.5px;[^}]*height:\s*12.5px;[^}]*\}/);
  assert.doesNotMatch(styles, /\.chart-zoom-glyph\s*\{[^}]*border:/);
  assert.match(styles, /#analyzer-view \.metadata-section:last-of-type\s*\{\s*border-bottom:\s*0;/);
  assert.match(index, /<div id="analyzer-action" class="analyzer-action" hidden><\/div>/);
  assert.match(styles, /\.analyzer-action:not\(\[hidden\]\)\s*\{\s*border-top:\s*1.25px solid var\(--line\);/);
  assert.match(app, /OUTPUT_FORMAT_LABELS/);
  assert.doesNotMatch(app, /artifact\.mime_type\} · coverage/);
  assert.match(styles, /\.processing-tabs button::after\s*\{\s*content:\s*none;/);
  assert.match(styles, /\.processing-tab-indicator\s*\{\s*display:\s*block;/);
  assert.match(styles, /\.status-strip-indicator\s*\{[\s\S]*?width:\s*0;[\s\S]*?height:\s*2.5px;[\s\S]*?transform:\s*translate3d/);
  assert.match(styles, /\.processing-content > \.processing-tabs\s*\{[\s\S]*?position:\s*relative;/);
  assert.match(styles, /\.processing-tabs button,[\s\S]*?\.processing-tabs button\.is-active\s*\{[\s\S]*?font-weight:\s*450;/);
  assert.match(styles, /\.processing-tab-indicator\s*\{[\s\S]*?height:\s*1.25px;[\s\S]*?width 520ms cubic-bezier\(\.22, 1, \.36, 1\),[\s\S]*?transform 520ms cubic-bezier\(\.22, 1, \.36, 1\);/);
  assert.doesNotMatch(app, /PROCESSING_DEMO_|visual demo data|demo job/);
  assert.match(styles, /\.processing-tabs strong,\s*\.processing-tabs button\.is-active strong\s*\{[\s\S]*?width:\s*auto;[\s\S]*?min-width:\s*27.5px;[\s\S]*?padding:\s*2.5px 7.5px;[\s\S]*?background:\s*var\(--control\);/);
  assert.match(styles, /\.processing-tabs button,[\s\S]*?\.processing-tabs button\.is-active\s*\{\s*gap:\s*6.25px;/);
  assert.match(styles, /\.processing-tabs button > span\s*\{\s*min-width:\s*0;/);
  assert.match(styles, /\.processing-tab-indicator\s*\{[\s\S]*?bottom:\s*6.25px;/);
  assert.match(styles, /\.queue-table\s*\{\s*table-layout:\s*fixed;/);
  assert.match(styles, /\.queue-table \.selection-column,\s*\.failure-table \.selection-column\s*\{[\s\S]*?width:\s*45px;[\s\S]*?padding:\s*0 0 0 15px !important;/);
  assert.match(styles, /\.queue-table th:nth-child\(2\)\s*\{\s*width:\s*auto;/);
  assert.match(styles, /\.queue-table th:nth-child\(3\),\s*\.queue-table th:nth-child\(4\),\s*\.queue-table th:nth-child\(5\)\s*\{\s*width:\s*18%;/);
  assert.match(styles, /\.queue-controls \.queue-cancel\s*\{[\s\S]*?min-width:\s*76.25px;[\s\S]*?gap:\s*6.25px;/);
  assert.match(styles, /\.failure-table th:nth-child\(2\)\s*\{\s*width:\s*44%;/);
  assert.match(styles, /\.history-table th:nth-child\(2\),\s*\.history-table th:nth-child\(3\),\s*\.history-table th:nth-child\(4\)\s*\{\s*width:\s*20%;/);
  assert.match(styles, /@media \(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.processing-tab-indicator\s*\{\s*transition-duration:\s*\.01ms;/);
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

test("the final Recordings polish owns the requested alignment and popup geometry", () => {
  const polish = styles.slice(styles.lastIndexOf("/* Recordings-page visual polish. */"));
  assert.match(polish, /\.sidebar\.has-folder-slot \.tool-list\s*\{[\s\S]*?calc\(var\(--sidebar-button-size\) \+ var\(--sidebar-button-gap\)\)/);
  assert.match(polish, /\.sidebar \.tool-list,[\s\S]*?margin-top:\s*10px;/);
  assert.match(polish, /#recordings-view \.rosbag-table th:nth-child\(n \+ 3\),[\s\S]*?text-align:\s*left;/);
  assert.match(polish, /\.table-sort\s*\{[\s\S]*?width:\s*max-content !important;[\s\S]*?justify-content:\s*flex-start !important;/);
  assert.match(polish, /\.table-sort::after\s*\{[\s\S]*?position:\s*static !important;[\s\S]*?margin-left:\s*5px !important;/);
  assert.match(polish, /#recordings-view \.status-tooltip\s*\{[\s\S]*?position:\s*fixed;[\s\S]*?pointer-events:\s*none;/);
  assert.match(polish, /#recordings-view \.table-footer\s*\{\s*margin-top:\s*-6.25px;/);
  assert.match(polish, /\.recording-filter:hover,[\s\S]*?\.recording-filter:focus-within\s*\{[\s\S]*?background:\s*var\(--folder-hover\);/);
  assert.match(polish, /\.prepare-dialog::backdrop\s*\{[\s\S]*?background:\s*rgba\(20, 20, 20, \.78\);/);
  assert.doesNotMatch(polish, /backdrop-filter:/);
  assert.match(polish, /\.prepare-dialog fieldset label\s*\{[\s\S]*?grid-template-columns:\s*17.5px minmax\(0, 1fr\);[\s\S]*?gap:\s*16.25px;/);
  assert.match(polish, /\.prepare-dialog fieldset input\s*\{[\s\S]*?width:\s*17.5px;[\s\S]*?height:\s*17.5px;/);
  assert.match(app, /const left = Math\.max\(edge, anchor\.left - width - gap\);/);
  assert.doesNotMatch(app, /roomOnRight/);
});
