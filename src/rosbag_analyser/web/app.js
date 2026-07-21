"use strict";

const content = document.querySelector("#content");
const pageTitle = document.querySelector("#page-title");
const rescanButton = document.querySelector("#rescan-button");
const statusMessage = document.querySelector("#status-message");
const recordingMatch = window.location.pathname.match(/^\/recordings\/(\d+)\/?$/);
let previewPollTimer = null;
let timelineAnimation = null;
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

  const preview = node("section", null, "panel preview-panel");
  preview.id = "front-preview-panel";
  preview.append(node("h2", "Front-camera preview"));
  preview.append(node("p", "Loading preview state…", "preview-state"));
  content.append(preview);

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
      facts.append(definitionRow("Validation", "Presence only; content validation is deferred"));
    }
    card.append(facts);
    if (component.diagnostic) {
      card.append(node("p", component.diagnostic.message, "diagnostic-block"));
    }
    list.append(card);
  });
  components.append(list);
  content.append(components);
  loadFrontPreview(recording.id);
}

function stopPreviewActivity() {
  if (previewPollTimer !== null) {
    window.clearTimeout(previewPollTimer);
    previewPollTimer = null;
  }
  if (timelineAnimation !== null) {
    window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
  }
}

async function loadFrontPreview(recordingId) {
  stopPreviewActivity();
  try {
    const preview = await requestJson(`/api/recordings/${recordingId}/front-preview`);
    renderFrontPreview(recordingId, preview);
  } catch (error) {
    const panel = document.querySelector("#front-preview-panel");
    if (panel) {
      const retry = node("button", "Retry preview status");
      retry.type = "button";
      retry.addEventListener("click", () => loadFrontPreview(recordingId));
      panel.replaceChildren(
        node("h2", "Front-camera preview"),
        node("p", "status unavailable", "preview-state preview-state-failed"),
        node("p", error.message, "diagnostic-block"),
        retry,
      );
      previewPollTimer = window.setTimeout(
        () => loadFrontPreview(recordingId),
        PREVIEW_RETRY_DELAY_MS,
      );
    }
  }
}

function renderFrontPreview(recordingId, preview) {
  const panel = document.querySelector("#front-preview-panel");
  if (!panel) return;
  stopPreviewActivity();
  panel.replaceChildren(node("h2", "Front-camera preview"));
  const stateLabel = preview.state.replaceAll("_", " ");
  panel.append(node("p", stateLabel, `preview-state preview-state-${preview.state}`));

  if (preview.diagnostic) {
    panel.append(node("p", preview.diagnostic.message, "diagnostic-block"));
  }

  if (preview.state === "not_requested" || preview.state === "failed") {
    const action = node("button", preview.state === "failed" ? "Retry preview" : "Generate preview");
    action.type = "button";
    action.addEventListener("click", async () => {
      action.disabled = true;
      showStatus("Requesting front-camera preview…");
      try {
        const result = await requestJson(`/api/recordings/${recordingId}/front-preview`, { method: "POST" });
        renderFrontPreview(recordingId, result);
        showStatus(result.state === "ready" ? "Front-camera preview is ready." : "Front-camera preview requested.");
      } catch (error) {
        showStatus(error.message, "error");
        action.disabled = false;
      }
    });
    panel.append(action);
    return;
  }

  if (preview.state === "queued" || preview.state === "processing") {
    panel.append(node("p", preview.state === "queued" ? "Waiting for the serial worker." : "The serial worker is generating browser media."));
    previewPollTimer = window.setTimeout(
      () => loadFrontPreview(recordingId),
      preview.poll_after_ms || 1000,
    );
    return;
  }

  if (preview.state === "ready" && preview.artifact) {
    renderFrontTimeline(recordingId, panel, preview);
  }
}

function renderFrontTimeline(recordingId, panel, preview) {
  const durationSeconds = Number(BigInt(preview.global_duration_ns)) / 1e9;
  const coverageStart = Number(BigInt(preview.artifact.coverage_start_ns)) / 1e9;
  const coverageEnd = Number(BigInt(preview.artifact.coverage_end_ns)) / 1e9;
  const player = node("div", null, "preview-player");
  const video = node("video");
  video.preload = "metadata";
  video.playsInline = true;
  video.muted = true;
  video.setAttribute("aria-label", "Front-camera preview");
  video.src = preview.artifact.media_url;
  const coverageMessage = node("p", "Outside front-camera coverage", "coverage-message");
  coverageMessage.hidden = true;
  player.append(video, coverageMessage);

  const controls = node("div", null, "timeline-controls");
  const playButton = node("button", "Play");
  playButton.type = "button";
  const slider = node("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(durationSeconds);
  slider.step = "0.001";
  slider.value = "0";
  slider.setAttribute("aria-label", "Global recording time");
  const timeLabel = node("output", `${formatElapsed(0)} / ${formatElapsed(durationSeconds)}`, "timeline-time");
  const mediaRetry = node("button", "Reload preview");
  mediaRetry.type = "button";
  mediaRetry.hidden = true;
  mediaRetry.addEventListener("click", () => loadFrontPreview(recordingId));
  controls.append(playButton, slider, timeLabel, mediaRetry);

  const coverage = node(
    "p",
    `Measured front coverage ${formatSignedElapsed(coverageStart)}–${formatSignedElapsed(coverageEnd)} · ROS record timestamps`,
    "coverage-summary",
  );
  panel.append(player, controls, coverage);

  const clock = {
    globalTime: 0,
    playing: false,
    anchorGlobal: 0,
    anchorPerformance: 0,
    mediaFailed: false,
  };

  function applyGlobalTime(value) {
    clock.globalTime = Math.min(Math.max(value, 0), durationSeconds);
    slider.value = String(clock.globalTime);
    timeLabel.value = `${formatElapsed(clock.globalTime)} / ${formatElapsed(durationSeconds)}`;
    timeLabel.textContent = timeLabel.value;
    if (clock.mediaFailed) {
      video.pause();
      video.hidden = true;
      coverageMessage.hidden = false;
      return;
    }
    const insideCoverage = clock.globalTime >= coverageStart && clock.globalTime <= coverageEnd;
    if (!insideCoverage) {
      video.pause();
      video.hidden = true;
      coverageMessage.hidden = false;
      return;
    }
    coverageMessage.hidden = true;
    video.hidden = false;
    const desiredMediaTime = clock.globalTime - coverageStart;
    if (
      Number.isFinite(video.duration)
      && Math.abs(video.currentTime - desiredMediaTime) > VIDEO_DRIFT_TOLERANCE_SECONDS
    ) {
      video.currentTime = Math.min(desiredMediaTime, video.duration);
    }
    if (clock.playing && video.paused) {
      video.play().catch(() => {
        clock.playing = false;
        playButton.textContent = "Play";
      });
    } else if (!clock.playing && !video.paused) {
      video.pause();
    }
  }

  function showMediaFailure() {
    clock.mediaFailed = true;
    clock.playing = false;
    playButton.textContent = "Play";
    playButton.disabled = true;
    slider.disabled = true;
    mediaRetry.hidden = false;
    if (timelineAnimation !== null) {
      window.cancelAnimationFrame(timelineAnimation);
      timelineAnimation = null;
    }
    video.pause();
    video.hidden = true;
    coverageMessage.textContent = "Preview media is unavailable.";
    coverageMessage.hidden = false;
    const state = panel.querySelector(".preview-state");
    if (state) {
      state.textContent = "media unavailable";
      state.className = "preview-state preview-state-failed";
    }
  }

  function tick(now) {
    if (!clock.playing) return;
    const elapsed = (now - clock.anchorPerformance) / 1000;
    const next = Math.min(durationSeconds, clock.anchorGlobal + elapsed);
    const reachedEnd = next >= durationSeconds;
    if (reachedEnd) clock.playing = false;
    applyGlobalTime(next);
    if (reachedEnd) {
      playButton.textContent = "Play";
      timelineAnimation = null;
      return;
    }
    timelineAnimation = window.requestAnimationFrame(tick);
  }

  playButton.addEventListener("click", () => {
    if (clock.playing) {
      clock.playing = false;
      playButton.textContent = "Play";
      if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
      timelineAnimation = null;
      applyGlobalTime(clock.globalTime);
      return;
    }
    if (clock.globalTime >= durationSeconds) applyGlobalTime(0);
    clock.playing = true;
    clock.anchorGlobal = clock.globalTime;
    clock.anchorPerformance = performance.now();
    playButton.textContent = "Pause";
    applyGlobalTime(clock.globalTime);
    timelineAnimation = window.requestAnimationFrame(tick);
  });

  slider.addEventListener("input", () => {
    applyGlobalTime(Number(slider.value));
    if (clock.playing) {
      clock.anchorGlobal = clock.globalTime;
      clock.anchorPerformance = performance.now();
    }
  });

  video.addEventListener("loadedmetadata", () => applyGlobalTime(clock.globalTime));
  video.addEventListener("error", showMediaFailure);
  applyGlobalTime(0);
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
