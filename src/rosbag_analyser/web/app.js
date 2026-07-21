"use strict";

const content = document.querySelector("#content");
const pageTitle = document.querySelector("#page-title");
const rescanButton = document.querySelector("#rescan-button");
const statusMessage = document.querySelector("#status-message");
const recordingMatch = window.location.pathname.match(/^\/recordings\/(\d+)\/?$/);

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
