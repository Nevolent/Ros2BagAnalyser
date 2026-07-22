"use strict";

const content = document.querySelector("#content");
const pageTitle = document.querySelector("#page-title");
const rescanButton = document.querySelector("#rescan-button");
const statusMessage = document.querySelector("#status-message");
const recordingMatch = window.location.pathname.match(/^\/recordings\/(\d+)\/?$/);
const previewPollTimers = { front: null, topdown: null };
let timelineAnimation = null;
let reviewController = null;
const PREVIEW_RETRY_DELAY_MS = 2000;
const VIDEO_DRIFT_TOLERANCE_SECONDS = 0.1;

rescanButton.hidden = Boolean(recordingMatch);

const roleLabels = {
  metadata: "ROS metadata",
  ros_database: "ROS database",
  topdown_video: "Top-down video",
  topdown_timestamps: "Top-down timestamps",
};

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) {
    element.textContent = text;
  }
  if (className) {
    element.className = className;
  }
  return element;
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || {};
    throw new Error(detail.message || "The request could not be completed.");
  }
  return body;
}

function showStatus(message, kind = "") {
  statusMessage.textContent = message;
  statusMessage.className = `status-message ${kind}`.trim();
}

function setPageTitle(title) {
  pageTitle.textContent = title;
  document.title = `${title} — ROS 2 Bag Analyser`;
}

function renderRecordingShell(title) {
  setPageTitle(title);
  rescanButton.hidden = true;
  content.replaceChildren();
  const back = node("a", "← Back to archive", "back-link");
  back.href = "/";
  content.append(back);
}

function healthBadge(value) {
  const badge = node("span", value.replaceAll("_", " "), `badge badge-${value}`);
  badge.setAttribute("aria-label", `ROS health: ${value.replaceAll("_", " ")}`);
  return badge;
}

function formatStartTime(value) {
  if (value === null) return "Unavailable";
  const milliseconds = Number(BigInt(value) / 1_000_000n);
  return new Date(milliseconds).toISOString();
}

function formatDuration(value) {
  if (value === null) return "Unavailable";
  const milliseconds = Number(BigInt(value) / 1_000_000n);
  const totalSeconds = milliseconds / 1000;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds - minutes * 60;
  return minutes ? `${minutes}m ${seconds.toFixed(3)}s` : `${seconds.toFixed(3)}s`;
}

function formatBytes(value) {
  if (value === null) return "Unavailable";
  const bytes = Number(BigInt(value));
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let amount = bytes;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  return `${amount.toFixed(unit === 0 ? 0 : 2)} ${units[unit]}`;
}

function formatElapsed(seconds) {
  const bounded = Math.max(0, seconds);
  const minutes = Math.floor(bounded / 60);
  const remainder = bounded - minutes * 60;
  return `${minutes}:${remainder.toFixed(3).padStart(6, "0")}`;
}

function formatSignedElapsed(seconds) {
  return `${seconds < 0 ? "−" : ""}${formatElapsed(Math.abs(seconds))}`;
}

function renderArchive(items) {
  setPageTitle("Recording archive");
  rescanButton.hidden = false;
  content.replaceChildren();
  if (items.length === 0) {
    const empty = node("div", null, "empty-state");
    empty.append(node("h2", "No recordings catalogued"));
    empty.append(node("p", "Use Rescan archive to inspect the configured read-only source."));
    content.append(empty);
    return;
  }

  const wrapper = node("div", null, "table-wrapper");
  wrapper.tabIndex = 0;
  wrapper.setAttribute("role", "region");
  wrapper.setAttribute("aria-label", "Catalogued recordings");
  const table = node("table");
  const head = node("thead");
  const headRow = node("tr");
  ["Recording", "Start (UTC)", "Duration", "Source size", "Storage", "Topics", "ROS health"].forEach((label) => {
    headRow.append(node("th", label));
  });
  head.append(headRow);
  table.append(head);

  const body = node("tbody");
  items.forEach((recording) => {
    const row = node("tr");
    const nameCell = node("td");
    const link = node("a", recording.name);
    link.href = `/recordings/${recording.id}`;
    nameCell.append(link);
    row.append(nameCell);
    row.append(node("td", formatStartTime(recording.start_time_ns)));
    row.append(node("td", formatDuration(recording.duration_ns)));
    row.append(node("td", formatBytes(recording.total_source_size_bytes)));
    row.append(node("td", recording.storage_format || "Unavailable"));
    row.append(node("td", recording.topic_count === null ? "Unavailable" : String(recording.topic_count)));
    const healthCell = node("td");
    healthCell.append(healthBadge(recording.ros_health));
    if (recording.diagnostic) {
      healthCell.append(node("span", recording.diagnostic.message, "diagnostic-inline"));
    }
    row.append(healthCell);
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  content.append(wrapper);
}

function definitionRow(term, value) {
  const fragment = document.createDocumentFragment();
  fragment.append(node("dt", term));
  fragment.append(node("dd", value));
  return fragment;
}

function renderRecording(recording) {
  renderRecordingShell(recording.name);

  const overview = node("section", null, "panel");
  overview.append(node("h2", "Recording metadata"));
  const health = node("div", null, "health-line");
  health.append(healthBadge(recording.ros_health));
  if (recording.diagnostic) {
    health.append(node("p", recording.diagnostic.message));
  }
  overview.append(health);
  const metadata = node("dl", null, "definition-grid");
  metadata.append(definitionRow("Start (UTC)", formatStartTime(recording.start_time_ns)));
  metadata.append(definitionRow("Duration", formatDuration(recording.duration_ns)));
  metadata.append(definitionRow("Total source size", formatBytes(recording.total_source_size_bytes)));
  metadata.append(definitionRow("Storage format", recording.storage_format || "Unavailable"));
  metadata.append(definitionRow("Metadata version", recording.metadata_version === null ? "Unavailable" : String(recording.metadata_version)));
  metadata.append(definitionRow("Messages", recording.message_count === null ? "Unavailable" : BigInt(recording.message_count).toLocaleString()));
  metadata.append(definitionRow("Topics", recording.topic_count === null ? "Unavailable" : String(recording.topic_count)));
  overview.append(metadata);
  content.append(overview);

  const review = node("section", null, "panel preview-panel");
  review.id = "camera-review-panel";
  review.append(node("h2", "Synchronized camera review"));
  const cameraGrid = node("div", null, "camera-grid");
  const frontPane = node("article", null, "camera-pane");
  frontPane.id = "front-preview-pane";
  frontPane.append(node("h3", "Front camera"));
  frontPane.append(node("p", "Loading preview state…", "preview-state"));
  const topdownPane = node("article", null, "camera-pane");
  topdownPane.id = "topdown-preview-pane";
  topdownPane.append(node("h3", "Top-down camera"));
  topdownPane.append(node("p", "Loading preview state…", "preview-state"));
  cameraGrid.append(frontPane, topdownPane);
  review.append(cameraGrid);
  content.append(review);

  const components = node("section", null, "panel");
  components.append(node("h2", "Source components"));
  const list = node("div", null, "component-list");
  recording.components.forEach((component) => {
    const card = node("article", null, "component-card");
    card.append(node("h3", roleLabels[component.role] || component.role));
    card.append(node("p", component.condition.replaceAll("_", " "), `component-condition condition-${component.condition}`));
    const facts = node("dl", null, "component-facts");
    facts.append(definitionRow("File", component.file_name || "Unavailable"));
    facts.append(definitionRow("Size", formatBytes(component.size_bytes)));
    if (component.role === "topdown_video" || component.role === "topdown_timestamps") {
      facts.append(definitionRow("Validation", "Presence checked during scan; content is validated by processing"));
    }
    card.append(facts);
    if (component.diagnostic) {
      card.append(node("p", component.diagnostic.message, "diagnostic-block"));
    }
    list.append(card);
  });
  components.append(list);
  content.append(components);
  initializeCameraReview(recording);
}

const streamDefinitions = {
  front: {
    paneId: "front-preview-pane",
    title: "Front camera",
    endpoint: "front-preview",
    generateLabel: "Generate front preview",
    retryLabel: "Retry front preview",
    requestingLabel: "Requesting front-camera preview…",
    coverageLabel: "front",
    provenanceLabel: "ROS record timestamps",
  },
  topdown: {
    paneId: "topdown-preview-pane",
    title: "Top-down camera",
    endpoint: "topdown-preview",
    generateLabel: "Generate top-down preview",
    retryLabel: "Retry top-down preview",
    requestingLabel: "Requesting top-down preview…",
    coverageLabel: "top-down",
    provenanceLabel: "CSV Unix timestamps",
  },
};

function stopReviewActivity() {
  Object.keys(previewPollTimers).forEach((kind) => {
    if (previewPollTimers[kind] !== null) {
      window.clearTimeout(previewPollTimers[kind]);
      previewPollTimers[kind] = null;
    }
  });
  if (reviewController) {
    Object.values(reviewController.players).forEach((player) => pausePlayer(player));
  }
  if (timelineAnimation !== null) {
    window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
  }
  reviewController = null;
}

function initializeCameraReview(recording) {
  stopReviewActivity();
  const durationSeconds = recording.duration_ns === null
    ? 0
    : Number(BigInt(recording.duration_ns)) / 1e9;
  reviewController = createGlobalTimeline(recording.id, durationSeconds);
  loadPreviewState("front", recording.id);
  loadPreviewState("topdown", recording.id);
}

async function loadPreviewState(kind, recordingId) {
  const definition = streamDefinitions[kind];
  if (previewPollTimers[kind] !== null) {
    window.clearTimeout(previewPollTimers[kind]);
    previewPollTimers[kind] = null;
  }
  try {
    const preview = await requestJson(`/api/recordings/${recordingId}/${definition.endpoint}`);
    renderPreviewState(kind, recordingId, preview);
  } catch (error) {
    const pane = document.querySelector(`#${definition.paneId}`);
    if (pane) {
      removePlayer(kind);
      const retry = node("button", "Retry preview status");
      retry.type = "button";
      retry.addEventListener("click", () => loadPreviewState(kind, recordingId));
      pane.replaceChildren(
        node("h3", definition.title),
        node("p", "status unavailable", "preview-state preview-state-failed"),
        node("p", error.message, "diagnostic-block"),
        retry,
      );
      previewPollTimers[kind] = window.setTimeout(
        () => loadPreviewState(kind, recordingId),
        PREVIEW_RETRY_DELAY_MS,
      );
    }
  }
}

function renderPreviewState(kind, recordingId, preview) {
  const definition = streamDefinitions[kind];
  const pane = document.querySelector(`#${definition.paneId}`);
  if (!pane) return;
  removePlayer(kind);
  pane.replaceChildren(node("h3", definition.title));
  const stateLabel = preview.state.replaceAll("_", " ");
  pane.append(node("p", stateLabel, `preview-state preview-state-${preview.state}`));

  if (preview.diagnostic) {
    pane.append(node("p", preview.diagnostic.message, "diagnostic-block"));
  }

  if (preview.state === "not_requested" || preview.state === "failed") {
    const action = node(
      "button",
      preview.state === "failed" ? definition.retryLabel : definition.generateLabel,
    );
    action.type = "button";
    action.addEventListener("click", async () => {
      action.disabled = true;
      showStatus(definition.requestingLabel);
      try {
        const result = await requestJson(
          `/api/recordings/${recordingId}/${definition.endpoint}`,
          { method: "POST" },
        );
        renderPreviewState(kind, recordingId, result);
        showStatus(result.state === "ready" ? `${definition.title} preview is ready.` : `${definition.title} preview requested.`);
      } catch (error) {
        showStatus(error.message, "error");
        action.disabled = false;
      }
    });
    pane.append(action);
    return;
  }

  if (preview.state === "queued" || preview.state === "processing") {
    pane.append(node("p", preview.state === "queued" ? "Waiting for the serial worker." : "The serial worker is generating browser media."));
    previewPollTimers[kind] = window.setTimeout(
      () => loadPreviewState(kind, recordingId),
      preview.poll_after_ms || 1000,
    );
    return;
  }

  if (preview.state === "ready" && preview.artifact) {
    renderReadyPlayer(kind, recordingId, pane, preview.artifact);
  }
}

function renderReadyPlayer(kind, recordingId, pane, artifact) {
  const definition = streamDefinitions[kind];
  const coverageStart = Number(BigInt(artifact.coverage_start_ns)) / 1e9;
  const coverageEnd = Number(BigInt(artifact.coverage_end_ns)) / 1e9;
  const player = node("div", null, "preview-player");
  const video = node("video");
  video.preload = "metadata";
  video.playsInline = true;
  video.muted = true;
  video.setAttribute("aria-label", `${definition.title} preview`);
  video.src = artifact.media_url;
  const coverageMessage = node("p", `Outside ${definition.coverageLabel} coverage`, "coverage-message");
  coverageMessage.hidden = true;
  player.append(video, coverageMessage);
  const mediaRetry = node("button", "Reload preview state");
  mediaRetry.type = "button";
  mediaRetry.hidden = true;
  mediaRetry.addEventListener("click", () => loadPreviewState(kind, recordingId));

  const coverage = node(
    "p",
    `Measured ${definition.coverageLabel} coverage ${formatSignedElapsed(coverageStart)}–${formatSignedElapsed(coverageEnd)} · ${definition.provenanceLabel}`,
    "coverage-summary",
  );
  pane.append(player, mediaRetry, coverage);
  if (artifact.warnings) {
    artifact.warnings.forEach((warning) => {
      pane.append(node("p", warning.message, "coverage-warning"));
    });
  }
  if (!reviewController) return;
  reviewController.players[kind] = {
    video,
    coverageStart,
    coverageEnd,
    coverageMessage,
    mediaRetry,
    mediaFailed: false,
    insideCoverage: false,
    playAttempt: 0,
    playPending: false,
  };
  video.addEventListener("loadedmetadata", () => {
    if (reviewController?.players[kind]?.video === video) {
      applyGlobalTime(reviewController.clock.globalTime, true);
    }
  });
  video.addEventListener("error", () => {
    if (reviewController?.players[kind]?.video === video) showMediaFailure(kind);
  });
  updateTransportAvailability();
  applyGlobalTime(reviewController.clock.globalTime, true);
}

function removePlayer(kind) {
  if (!reviewController || !reviewController.players[kind]) return;
  pausePlayer(reviewController.players[kind]);
  delete reviewController.players[kind];
  updateTransportAvailability();
}

function pausePlayer(player) {
  player.playAttempt += 1;
  player.playPending = false;
  player.video.pause();
}

function createGlobalTimeline(recordingId, durationSeconds) {
  const panel = document.querySelector("#camera-review-panel");
  const controls = node("div", null, "timeline-controls");
  const playButton = node("button", "Play");
  playButton.type = "button";
  playButton.disabled = true;
  const slider = node("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(durationSeconds);
  slider.step = "0.001";
  slider.value = "0";
  slider.disabled = durationSeconds <= 0;
  slider.setAttribute("aria-label", "Global recording time");
  const timeLabel = node("output", `${formatElapsed(0)} / ${formatElapsed(durationSeconds)}`, "timeline-time");
  controls.append(playButton, slider, timeLabel);
  if (panel) panel.append(controls);

  const controller = {
    recordingId,
    durationSeconds,
    players: {},
    playButton,
    slider,
    timeLabel,
    clock: {
      globalTime: 0,
      playing: false,
      anchorGlobal: 0,
      anchorPerformance: 0,
    },
  };
  playButton.addEventListener("click", () => togglePlayback());
  slider.addEventListener("input", () => {
    applyGlobalTime(Number(slider.value), true);
    if (controller.clock.playing) {
      controller.clock.anchorGlobal = controller.clock.globalTime;
      controller.clock.anchorPerformance = performance.now();
    }
  });
  return controller;
}

function applyGlobalTime(value, forceSeek = false) {
  const controller = reviewController;
  if (!controller) return;
  const clock = controller.clock;
  clock.globalTime = Math.min(Math.max(value, 0), controller.durationSeconds);
  controller.slider.value = String(clock.globalTime);
  controller.timeLabel.value = `${formatElapsed(clock.globalTime)} / ${formatElapsed(controller.durationSeconds)}`;
  controller.timeLabel.textContent = controller.timeLabel.value;
  Object.values(controller.players).forEach((player) => {
    if (player.mediaFailed) return;
    const insideCoverage = clock.globalTime >= player.coverageStart && clock.globalTime <= player.coverageEnd;
    if (!insideCoverage) {
      if (!player.video.paused || player.playPending) pausePlayer(player);
      player.video.hidden = true;
      player.coverageMessage.hidden = false;
      player.insideCoverage = false;
      return;
    }
    const enteredCoverage = !player.insideCoverage;
    player.insideCoverage = true;
    player.coverageMessage.hidden = true;
    player.video.hidden = false;
    const desiredMediaTime = clock.globalTime - player.coverageStart;
    if (player.video.readyState >= 1 && (
      forceSeek
      || enteredCoverage
      || Math.abs(player.video.currentTime - desiredMediaTime) > VIDEO_DRIFT_TOLERANCE_SECONDS
    )) {
      player.video.currentTime = Number.isFinite(player.video.duration)
        ? Math.min(desiredMediaTime, player.video.duration)
        : desiredMediaTime;
    }
    if (clock.playing && player.video.paused && !player.playPending) {
      const playAttempt = ++player.playAttempt;
      player.playPending = true;
      player.video.play().then(() => {
        if (player.playAttempt === playAttempt) player.playPending = false;
      }).catch(() => {
        if (
          player.playAttempt !== playAttempt
          || reviewController !== controller
          || !clock.playing
          || !player.insideCoverage
        ) return;
        player.playPending = false;
        clock.playing = false;
        controller.playButton.textContent = "Play";
        applyGlobalTime(clock.globalTime);
      });
    } else if (!clock.playing && (!player.video.paused || player.playPending)) {
      pausePlayer(player);
    }
  });
}

function showMediaFailure(kind) {
  if (!reviewController || !reviewController.players[kind]) return;
  const player = reviewController.players[kind];
  player.mediaFailed = true;
  pausePlayer(player);
  player.video.hidden = true;
  player.coverageMessage.textContent = "Preview media is unavailable.";
  player.coverageMessage.hidden = false;
  player.mediaRetry.hidden = false;
  const pane = document.querySelector(`#${streamDefinitions[kind].paneId}`);
  const state = pane ? pane.querySelector(".preview-state") : null;
  if (state) {
    state.textContent = "media unavailable";
    state.className = "preview-state preview-state-failed";
  }
  updateTransportAvailability();
}

function updateTransportAvailability() {
  if (!reviewController) return;
  const usablePlayers = Object.values(reviewController.players).filter((player) => !player.mediaFailed);
  reviewController.playButton.disabled = usablePlayers.length === 0 || reviewController.durationSeconds <= 0;
  if (usablePlayers.length === 0 && reviewController.clock.playing) {
    reviewController.clock.playing = false;
    reviewController.playButton.textContent = "Play";
    if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
  }
}

function togglePlayback() {
  const controller = reviewController;
  if (!controller || controller.playButton.disabled) return;
  const clock = controller.clock;
  if (clock.playing) {
    clock.playing = false;
    controller.playButton.textContent = "Play";
    if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
    applyGlobalTime(clock.globalTime);
    return;
  }
  if (clock.globalTime >= controller.durationSeconds) applyGlobalTime(0, true);
  clock.playing = true;
  clock.anchorGlobal = clock.globalTime;
  clock.anchorPerformance = performance.now();
  controller.playButton.textContent = "Pause";
  applyGlobalTime(clock.globalTime);
  timelineAnimation = window.requestAnimationFrame(tickTimeline);
}

function tickTimeline(now) {
  const controller = reviewController;
  if (!controller || !controller.clock.playing) return;
  const clock = controller.clock;
  const elapsed = (now - clock.anchorPerformance) / 1000;
  const next = Math.min(controller.durationSeconds, clock.anchorGlobal + elapsed);
  const reachedEnd = next >= controller.durationSeconds;
  if (reachedEnd) clock.playing = false;
  applyGlobalTime(next);
  if (reachedEnd) {
    controller.playButton.textContent = "Play";
    timelineAnimation = null;
    return;
  }
  timelineAnimation = window.requestAnimationFrame(tickTimeline);
}

async function refreshArchive() {
  const result = await requestJson("/api/recordings");
  renderArchive(result.items);
  return result;
}

async function loadInitialArchive() {
  rescanButton.disabled = true;
  showStatus("Loading catalog…");
  try {
    const result = await refreshArchive();
    showStatus(`${result.items.length} recording${result.items.length === 1 ? "" : "s"} loaded.`);
  } catch (error) {
    content.replaceChildren(node("p", error.message, "diagnostic-block"));
    showStatus(error.message, "error");
  } finally {
    rescanButton.disabled = false;
  }
}

async function loadRecording(recordingId) {
  renderRecordingShell("Recording details");
  showStatus("Loading recording…");
  try {
    const recording = await requestJson(`/api/recordings/${recordingId}`);
    renderRecording(recording);
    showStatus("Recording loaded.");
  } catch (error) {
    content.append(node("p", error.message, "diagnostic-block"));
    showStatus(error.message, "error");
  }
}

rescanButton.addEventListener("click", async () => {
  rescanButton.disabled = true;
  showStatus("Scanning the configured archive read-only…");
  try {
    const result = await requestJson("/api/catalog/rescan", { method: "POST" });
    try {
      await refreshArchive();
      showStatus(`Scan complete in ${result.duration_ms} ms: ${result.recording_count} recordings, ${result.readable_count} readable, ${result.damaged_count} damaged.`);
    } catch (error) {
      showStatus(`${error.message} The scan finished, but the current table could not be refreshed.`, "error");
    }
  } catch (error) {
    showStatus(`${error.message} The current table has been kept.`, "error");
  } finally {
    rescanButton.disabled = false;
  }
});

if (recordingMatch) {
  loadRecording(recordingMatch[1]);
} else {
  loadInitialArchive();
}
