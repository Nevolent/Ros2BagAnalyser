"use strict";

const byId = (id) => document.querySelector(`#${id}`);
const liveRegion = byId("live-region");
const viewPanels = [...document.querySelectorAll("[data-view-panel]")];
const navLinks = [...document.querySelectorAll("[data-nav]")];
const analyzerNav = byId("analyzer-nav");

const catalogElements = {
  folderPanel: byId("folder-panel"),
  folderTree: byId("folder-tree"),
  folderSearch: byId("folder-search"),
  collapseFolders: byId("collapse-folders"),
  expandFolders: byId("expand-folders"),
  page: document.querySelector(".recordings-page"),
  lastScanned: byId("last-scanned"),
  rescan: byId("rescan-archive"),
  rows: byId("recording-rows"),
  loading: byId("recording-loading"),
  empty: byId("recording-empty"),
  filterEmpty: byId("recording-filter-empty"),
  failure: byId("recording-failure"),
  failureText: byId("recording-failure-text"),
  retry: byId("recording-retry"),
  search: byId("recording-search"),
  analysisFilter: byId("analysis-filter"),
  healthFilter: byId("health-filter"),
  selectAll: byId("select-all-recordings"),
  selectedCount: byId("selected-count"),
  prepare: byId("prepare-selected"),
  previous: byId("previous-page"),
  next: byId("next-page"),
  pageButtons: byId("page-buttons"),
  pageStatus: byId("page-status"),
};

const processingElements = {
  notice: byId("processing-notice"),
  lastUpdate: byId("processing-last-update"),
  refresh: byId("refresh-processing"),
  liveToggle: byId("live-toggle"),
  liveLabel: byId("live-toggle-label"),
  search: byId("processing-search"),
  currentHost: byId("current-job-host"),
  queueRows: byId("queue-rows"),
  queueEmpty: byId("queue-empty"),
  queueDescription: byId("queue-description"),
  failureRows: byId("failure-rows"),
  failuresEmpty: byId("failures-empty"),
  historyRows: byId("history-rows"),
  historyEmpty: byId("history-empty"),
  historyDescription: byId("history-description"),
  historyMore: byId("history-more"),
  dialog: byId("processing-error-dialog"),
  dialogTitle: byId("processing-error-title"),
  dialogCopy: byId("processing-error-copy"),
  dialogMeta: byId("processing-error-meta"),
  dialogClose: byId("close-processing-error"),
  dialogDismiss: byId("dismiss-processing-error"),
};

const detailElements = {
  name: byId("detail-name"),
  recorded: byId("detail-recorded"),
  duration: byId("detail-duration"),
  size: byId("detail-size"),
  storage: byId("detail-storage"),
  messages: byId("detail-messages"),
  topics: byId("detail-topics"),
  health: byId("detail-health"),
  error: byId("detail-error"),
  componentCount: byId("component-count"),
  components: byId("component-rows"),
  outputs: byId("output-rows"),
  action: byId("analyzer-action"),
};

const timelineElements = {
  play: byId("timeline-play"),
  slider: byId("global-time-slider"),
  current: byId("timeline-current"),
  total: byId("timeline-total"),
};

const imuElements = {
  pane: byId("imu-series-pane"),
  badge: byId("imu-state-badge"),
  message: byId("imu-message"),
  messageTitle: byId("imu-message-title"),
  status: byId("imu-status"),
  action: byId("imu-state-action"),
  graph: byId("imu-graph"),
  plot: byId("imu-plot"),
  canvas: byId("imu-canvas"),
  cursor: byId("imu-cursor"),
  summary: byId("imu-summary"),
  currentValue: byId("imu-current-value"),
  currentState: byId("imu-current-state"),
  warnings: byId("imu-warnings"),
  picker: document.querySelector(".sensor-picker"),
  pickerTrigger: byId("sensor-picker-trigger"),
  pickerMenu: byId("sensor-picker-menu"),
  selectedLabel: byId("selected-sensor-label"),
};

const OUTPUT_ORDER = ["front_preview", "topdown_preview", "imu_series"];
const OUTPUT_LABELS = {
  front_preview: "Front-camera preview",
  topdown_preview: "Top-down preview",
  imu_series: "IMU data bundle",
};
const OUTPUT_SHORT_LABELS = {
  front_preview: "Front",
  topdown_preview: "Top-down",
  imu_series: "IMU",
};
const ROLE_LABELS = {
  metadata: "ROS metadata",
  ros_database: "ROS database",
  topdown_video: "Top-down video",
  topdown_timestamps: "Top-down timestamps",
};
const ROWS_PER_PAGE = 20;
const MINIMUM_POLL_MS = 1000;
const MAXIMUM_POLL_MS = 30000;
const VIDEO_DRIFT_TOLERANCE_SECONDS = 0.1;
const VIDEO_SEEK_RETRY_MS = 1500;
const GRAPH_SEEK_STEP_SECONDS = 0.1;
const GRAPH_SEEK_PAGE_SECONDS = 5;

let routeGeneration = 0;
let routeController = null;
let currentRoute = null;
let reviewController = null;
let timelineAnimation = null;
let imuSeekAnimation = null;
let pendingImuSeekTime = null;
let activeImuPointerId = null;

const catalogState = {
  data: null,
  loading: false,
  loadingGeneration: null,
  requestSerial: 0,
  selectedIds: new Set(),
  folderPath: "",
  folderQuery: "",
  query: "",
  analysis: "all",
  health: "all",
  sort: { key: "recorded", direction: "descending" },
  page: 1,
  collapsedFolders: new Set(),
};

const processingState = {
  overview: null,
  tab: "queue",
  autoRefresh: true,
  pollTimer: null,
  pollController: null,
  pageController: null,
  pollFailures: 0,
  requestSerial: 0,
  pages: { failed: null, history: null },
  historyIds: new Set(),
  elapsedFrame: null,
  elapsedAnchor: null,
};

class ApiError extends Error {
  constructor(message, kind, status = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function icon(name, className = "") {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  if (className) svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(namespace, "use");
  use.setAttribute("href", `#icon-${name}`);
  svg.append(use);
  return svg;
}

function announce(message) {
  liveRegion.textContent = "";
  window.requestAnimationFrame(() => { liveRegion.textContent = message; });
}

function showNotice(element, message, kind = "") {
  element.textContent = message;
  element.className = `inline-notice ${kind}`.trim();
  element.hidden = !message;
}

function safeBackendMessage(body, fallback) {
  const detail = body && typeof body === "object" ? body.detail : null;
  const message = detail && typeof detail === "object" ? detail.message : null;
  return typeof message === "string" && message.length > 0 && message.length <= 500
    ? message
    : fallback;
}

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError("The server could not be reached.", "network");
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(
      response.ok ? "The server returned an invalid response." : "The request failed.",
      "validation",
      response.status,
    );
  }
  if (!response.ok) {
    throw new ApiError(
      safeBackendMessage(body, "The request could not be completed."),
      "http",
      response.status,
    );
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new ApiError("The server returned an invalid response.", "validation");
  }
  return body;
}

function parseRoute(pathname) {
  if (pathname === "/" || pathname === "") return { view: "recordings" };
  if (pathname === "/processing" || pathname === "/processing/") {
    return { view: "processing" };
  }
  const match = pathname.match(/^\/recordings\/([1-9]\d*)\/?$/);
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isSafeInteger(id) ? { view: "analyzer", recordingId: id } : null;
}

function navigate(path, { replace = false } = {}) {
  const route = parseRoute(path);
  if (!route) return;
  if (replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  activateRoute(route);
}

function setActiveView(view) {
  viewPanels.forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== view; });
  navLinks.forEach((link) => {
    const active = link.dataset.nav === view;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  const label = view === "recordings" ? "Recordings" : view === "processing" ? "Processing" : "Analyzer";
  document.title = `${label} — Tectrace`;
}

function activateRoute(route) {
  routeGeneration += 1;
  currentRoute = route;
  if (routeController) routeController.abort();
  routeController = new AbortController();
  stopProcessingActivity();
  stopReviewActivity();
  setActiveView(route.view);
  if (route.view === "recordings") {
    if (catalogState.data) renderCatalog();
    else loadCatalog({ initial: true });
  } else if (route.view === "processing") {
    loadProcessing({ manual: true });
  } else {
    analyzerNav.href = `/recordings/${route.recordingId}`;
    analyzerNav.setAttribute("aria-disabled", "false");
    loadRecordingDetail(route.recordingId);
  }
}

function formatRecorded(value) {
  if (value === null || value === undefined) return "Unavailable";
  try {
    const milliseconds = Number(BigInt(value) / 1_000_000n);
    const date = new Date(milliseconds);
    if (Number.isNaN(date.getTime())) return "Unavailable";
    return date.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  } catch { return "Unavailable"; }
}

function recordedDateParts(value) {
  if (value === null || value === undefined) return null;
  try {
    const milliseconds = Number(BigInt(value) / 1_000_000n);
    const date = new Date(milliseconds);
    if (Number.isNaN(date.getTime())) return null;
    return {
      iso: date.toISOString(),
      date: new Intl.DateTimeFormat("en-GB", {
        day: "2-digit", month: "short", year: "numeric", timeZone: "UTC",
      }).format(date),
      time: new Intl.DateTimeFormat("en-GB", {
        hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC",
      }).format(date),
    };
  } catch { return null; }
}

function recordingDisplayName(value) {
  const name = String(value || "");
  const match = name.match(/^(\d{4})_(\d{2})_(\d{2})_(.+)$/);
  if (!match) return name;
  const [year, month, day] = match.slice(1, 4).map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return name;
  const readable = match[4]
    .replaceAll("_", " ")
    .replace(/([A-Za-z])(\d)/g, "$1 $2")
    .replace(/(\d)([A-Za-z])/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
  if (!readable) return name;
  return readable.split(" ").map((word) => word.charAt(0).toLocaleUpperCase() + word.slice(1)).join(" ");
}

function formatDurationNanoseconds(value) {
  if (value === null || value === undefined) return "Unavailable";
  try { return formatSeconds(Number(BigInt(value)) / 1e9, true); } catch { return "Unavailable"; }
}

function formatSeconds(value, precise = false) {
  const seconds = Math.max(0, Number(value) || 0);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds - hours * 3600 - minutes * 60;
  const secondsText = precise ? remainder.toFixed(3).padStart(6, "0") : String(Math.floor(remainder)).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${secondsText}`
    : `${minutes}:${secondsText}`;
}

function formatMilliseconds(value) {
  if (value === null || value === undefined) return "Unavailable";
  return formatSeconds(Number(value) / 1000, false);
}

function formatAge(value) {
  if (!(value >= 0)) return "Unavailable";
  const seconds = Math.floor(value / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m ago`;
}

function formatBytes(value) {
  if (value === null || value === undefined) return "Unavailable";
  try {
    let amount = Number(BigInt(value));
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
    return `${amount.toFixed(index === 0 ? 0 : amount >= 10 ? 1 : 2)} ${units[index]}`;
  } catch { return "Unavailable"; }
}

function formatCount(value) {
  if (value === null || value === undefined) return "Unavailable";
  try { return BigInt(value).toLocaleString(); } catch { return "Unavailable"; }
}

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Unavailable" : date.toLocaleString();
}

function humanize(value) {
  return String(value || "").replaceAll("_", " ").replace(/^\w/, (letter) => letter.toUpperCase());
}

function metadataStatus(label, className) {
  const status = node("span", null, `metadata-status ${className}`);
  const dot = node("i");
  dot.setAttribute("aria-hidden", "true");
  status.append(dot, node("b", label, "metadata-status-label"));
  return status;
}

function compareIntegerStrings(left, right) {
  try {
    const first = left === null ? -1n : BigInt(left);
    const second = right === null ? -1n : BigInt(right);
    return first < second ? -1 : first > second ? 1 : 0;
  } catch { return 0; }
}

function outputFacts(recording) {
  return new Map(recording.outputs.map((output) => [output.kind, output]));
}

function validateCatalog(document) {
  if (!document.scan || !document.summary || !Array.isArray(document.folders) || !Array.isArray(document.recordings)) {
    throw new ApiError("The saved catalog response was invalid.", "validation");
  }
  document.recordings.forEach((recording) => {
    if (!Number.isSafeInteger(recording.id) || recording.id <= 0 || typeof recording.name !== "string" || !Array.isArray(recording.outputs)) {
      throw new ApiError("The saved catalog response was invalid.", "validation");
    }
  });
  return document;
}

async function loadCatalog({ initial = false, retained = false } = {}) {
  if (catalogState.loading && catalogState.loadingGeneration === routeGeneration) return;
  const serial = ++catalogState.requestSerial;
  catalogState.loading = true;
  catalogState.loadingGeneration = routeGeneration;
  if (initial) {
    catalogElements.loading.hidden = false;
    catalogElements.failure.hidden = true;
  }
  const generation = routeGeneration;
  try {
    const document = validateCatalog(await requestJson("/api/v1/catalog", { signal: routeController?.signal }));
    if (serial !== catalogState.requestSerial || generation !== routeGeneration || currentRoute?.view !== "recordings") return;
    catalogState.data = document;
    renderCatalog();
    announce(`${document.summary.recordings} saved recordings loaded.`);
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (catalogState.data || retained) {
      renderCatalog();
    } else {
      catalogElements.loading.hidden = true;
      catalogElements.failure.hidden = false;
      catalogElements.failureText.textContent = error.message;
    }
    announce(error.message);
  } finally {
    if (serial === catalogState.requestSerial) {
      catalogState.loading = false;
      catalogState.loadingGeneration = null;
      updateSelectionState();
    }
  }
}

function renderCatalog() {
  const document = catalogState.data;
  if (!document) return;
  catalogElements.loading.hidden = true;
  catalogElements.failure.hidden = true;
  const completed = document.scan.completed_at;
  catalogElements.lastScanned.textContent = completed
    ? `Last scanned ${formatDateTime(completed)}`
    : "No successful V1 scan yet";
  ["recordings", "ready", "processing", "queued", "failed", "damaged"].forEach((key) => {
    byId(`summary-${key}`).textContent = String(document.summary[key]);
  });
  renderFolderTree();
  renderRecordingTable();
}

function folderVisiblePaths(folders, query) {
  if (!query) return new Set(folders.map((folder) => folder.path));
  const visible = new Set();
  folders.forEach((folder) => {
    const matches = folder.name.toLocaleLowerCase().includes(query) || folder.path.toLocaleLowerCase().includes(query);
    if (!matches) return;
    visible.add(folder.path);
    let parent = folder.parent_path;
    while (parent) {
      visible.add(parent);
      parent = folders.find((candidate) => candidate.path === parent)?.parent_path || "";
    }
    folders.forEach((candidate) => {
      if (candidate.path.startsWith(`${folder.path}/`)) visible.add(candidate.path);
    });
  });
  return visible;
}

function renderFolderTree() {
  const folders = catalogState.data.folders;
  const query = catalogState.folderQuery;
  const visiblePaths = folderVisiblePaths(folders, query);
  const children = new Map();
  folders.forEach((folder) => {
    const list = children.get(folder.parent_path) || [];
    list.push(folder);
    children.set(folder.parent_path, list);
  });
  children.forEach((items) => items.sort((a, b) => a.name.localeCompare(b.name)));
  catalogElements.folderTree.replaceChildren();

  const all = node("button", null, "folder-item folder-all");
  all.type = "button";
  all.dataset.folder = "";
  all.setAttribute("aria-pressed", String(catalogState.folderPath === ""));
  all.classList.toggle("is-active", catalogState.folderPath === "");
  all.append(icon("folder"), node("span", "All recordings", "folder-label"), node("strong", catalogState.data.summary.recordings));
  all.addEventListener("click", () => selectFolder(""));
  catalogElements.folderTree.append(all);

  const root = node("div", null, "folder-children folder-root-children");
  const appendBranch = (parentPath, host) => {
    (children.get(parentPath) || []).forEach((folder) => {
      if (!visiblePaths.has(folder.path)) return;
      const wrapper = node("div", null, "folder-node");
      const hasChildren = (children.get(folder.path) || []).some((item) => visiblePaths.has(item.path));
      const button = node("button", null, hasChildren ? "folder-parent" : "folder-item");
      button.type = "button";
      button.dataset.folder = folder.path;
      button.setAttribute("aria-pressed", String(catalogState.folderPath === folder.path));
      button.classList.toggle("is-active", catalogState.folderPath === folder.path);
      if (hasChildren) {
        button.setAttribute("aria-expanded", String(!catalogState.collapsedFolders.has(folder.path)));
        button.append(icon("chevron", "folder-chevron"));
      }
      button.append(icon("folder", "folder-icon"));
      const label = node("span", folder.name, "folder-label");
      label.title = folder.name;
      button.append(label, node("strong", folder.descendant_recording_count));
      button.addEventListener("click", () => {
        if (hasChildren) {
          if (catalogState.collapsedFolders.has(folder.path)) catalogState.collapsedFolders.delete(folder.path);
          else catalogState.collapsedFolders.add(folder.path);
        }
        selectFolder(folder.path);
      });
      wrapper.append(button);
      if (hasChildren) {
        const branch = node("div", null, "folder-children");
        branch.hidden = catalogState.collapsedFolders.has(folder.path) && !query;
        appendBranch(folder.path, branch);
        wrapper.append(branch);
      }
      host.append(wrapper);
    });
  };
  appendBranch("", root);
  catalogElements.folderTree.append(root);
  if (root.children.length === 0 && query) catalogElements.folderTree.append(node("div", "No folders found", "folder-empty"));
}

function selectFolder(path) {
  catalogState.folderPath = path;
  catalogState.page = 1;
  renderFolderTree();
  renderRecordingTable();
  announce(path ? `${path} folder selected.` : "All recordings selected.");
}

function canPrepare(recording) {
  return recording.presentation_health === "readable"
    && OUTPUT_ORDER.every((kind) => {
      const output = recording.outputs.find((candidate) => candidate.kind === kind);
      return output && output.state !== "unavailable";
    });
}

function filteredRecordings() {
  const query = catalogState.query;
  const path = catalogState.folderPath;
  const rows = catalogState.data.recordings.filter((recording) => {
    const matchesQuery = !query || `${recording.name} ${recording.folder_path}`.toLocaleLowerCase().includes(query);
    const matchesFolder = !path || recording.folder_path === path || recording.folder_path.startsWith(`${path}/`);
    const matchesAnalysis = catalogState.analysis === "all" || recording.analysis_state === catalogState.analysis;
    const matchesHealth = catalogState.health === "all" || recording.presentation_health === catalogState.health;
    return matchesQuery && matchesFolder && matchesAnalysis && matchesHealth;
  });
  const ranks = {
    health: { readable: 1, damaged: 2 },
    analysis: { ready: 1, processing: 2, queued: 3, not_planned: 4, failed: 5 },
  };
  const direction = catalogState.sort.direction === "ascending" ? 1 : -1;
  return rows.sort((left, right) => {
    const key = catalogState.sort.key;
    let compared = 0;
    if (key === "name") compared = left.name.localeCompare(right.name);
    else if (key === "recorded") compared = compareIntegerStrings(left.start_time_ns, right.start_time_ns);
    else if (key === "duration") compared = compareIntegerStrings(left.duration_ns, right.duration_ns);
    else if (key === "size") compared = compareIntegerStrings(left.total_source_size_bytes, right.total_source_size_bytes);
    else if (key === "health") compared = ranks.health[left.presentation_health] - ranks.health[right.presentation_health];
    else compared = ranks.analysis[left.analysis_state] - ranks.analysis[right.analysis_state];
    return compared === 0 ? left.id - right.id : compared * direction;
  });
}

function statusIndicator(label, className, details, iconName) {
  const indicator = node("span", null, `status-indicator ${className}`);
  indicator.tabIndex = 0;
  indicator.setAttribute("aria-label", label);
  const glyph = node("span", null, "status-glyph");
  glyph.append(icon(iconName));
  const tooltip = node("span", null, "status-tooltip");
  tooltip.setAttribute("role", "tooltip");
  tooltip.append(node("strong", label));
  details.filter(Boolean).forEach((detail) => tooltip.append(node("span", detail)));
  indicator.append(glyph, node("span", label, "status-label"), tooltip);
  return indicator;
}

function analysisDetails(recording) {
  const outputs = outputFacts(recording);
  return OUTPUT_ORDER.map((kind) => {
    const output = outputs.get(kind);
    const diagnostic = output?.diagnostic?.message;
    return `${OUTPUT_SHORT_LABELS[kind]}: ${humanize(output?.state || "unavailable")}${diagnostic ? ` — ${diagnostic}` : ""}`;
  });
}

function createRecordingRow(recording) {
  const row = document.createElement("tr");
  row.dataset.recordingId = String(recording.id);
  const selection = node("td", null, "selection-column");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "row-select";
  checkbox.value = String(recording.id);
  checkbox.checked = catalogState.selectedIds.has(recording.id);
  checkbox.disabled = !canPrepare(recording);
  checkbox.setAttribute("aria-label", checkbox.disabled
    ? `${recording.name} cannot be prepared because prerequisites are unavailable`
    : `Select ${recording.name}`);
  checkbox.addEventListener("click", (event) => event.stopPropagation());
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) catalogState.selectedIds.add(recording.id);
    else catalogState.selectedIds.delete(recording.id);
    updateSelectionState();
  });
  selection.append(checkbox);

  const nameCell = document.createElement("td");
  const copy = node("span", null, "recording-copy");
  const link = node("a", recordingDisplayName(recording.name), "recording-link");
  link.href = `/recordings/${recording.id}`;
  link.dataset.route = "";
  link.title = recording.name;
  const sublabel = node("span", recording.name, "cell-sublabel");
  sublabel.title = recording.name;
  copy.append(link, sublabel);
  nameCell.append(copy);
  row.append(selection, nameCell);
  const recordedCell = node("td", null, "date-cell");
  const recorded = recordedDateParts(recording.start_time_ns);
  if (recorded) {
    const time = node("time");
    time.setAttribute("datetime", recorded.iso);
    time.append(node("span", recorded.date), node("span", recorded.time));
    recordedCell.append(time);
  } else {
    recordedCell.textContent = "Unavailable";
  }
  row.append(
    recordedCell,
    node("td", formatDurationNanoseconds(recording.duration_ns)),
    node("td", formatBytes(recording.total_source_size_bytes)),
  );

  const healthCell = node("td", null, "status-cell");
  healthCell.append(statusIndicator(
    recording.presentation_health === "readable" ? "Readable" : "Damaged",
    `table-health--${recording.presentation_health}`,
    [recording.diagnostic?.message || (recording.presentation_health === "readable" ? "Source prerequisites are readable." : "Open the recording for the precise diagnostic.")],
    recording.presentation_health === "readable" ? "check" : "damaged",
  ));
  const analysisCell = node("td", null, "status-cell");
  const analysisLabel = recording.analysis_state === "not_planned" ? "Not planned" : humanize(recording.analysis_state);
  const analysisIcon = { ready: "check", processing: "processing", queued: "queue", failed: "warning", not_planned: "info" }[recording.analysis_state];
  analysisCell.append(statusIndicator(analysisLabel, `table-status--${recording.analysis_state.replaceAll("_", "-")}`, analysisDetails(recording), analysisIcon));
  row.append(healthCell, analysisCell);
  row.addEventListener("click", (event) => {
    if (event.target.closest("input, a, button, .status-indicator")) return;
    navigate(`/recordings/${recording.id}`);
  });
  return row;
}

function renderRecordingTable() {
  if (!catalogState.data) return;
  const matching = filteredRecordings();
  const totalPages = Math.max(1, Math.ceil(matching.length / ROWS_PER_PAGE));
  catalogState.page = Math.min(catalogState.page, totalPages);
  const start = (catalogState.page - 1) * ROWS_PER_PAGE;
  const visible = matching.slice(start, start + ROWS_PER_PAGE);
  catalogElements.rows.replaceChildren(...visible.map(createRecordingRow));
  catalogElements.empty.hidden = catalogState.data.recordings.length !== 0;
  catalogElements.filterEmpty.hidden = catalogState.data.recordings.length === 0 || matching.length !== 0;
  renderPagination(totalPages);
  updateSelectionState();
}

function renderPagination(totalPages) {
  catalogElements.pageButtons.replaceChildren();
  for (let page = 1; page <= totalPages; page += 1) {
    const button = node("button", page);
    button.type = "button";
    button.classList.toggle("is-active", page === catalogState.page);
    button.setAttribute("aria-label", `Page ${page}`);
    if (page === catalogState.page) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => { catalogState.page = page; renderRecordingTable(); });
    catalogElements.pageButtons.append(button);
  }
  catalogElements.previous.disabled = catalogState.page === 1;
  catalogElements.next.disabled = catalogState.page === totalPages;
  catalogElements.pageStatus.textContent = `Page ${catalogState.page} of ${totalPages}`;
}

function updateSelectionState() {
  const visible = [...catalogElements.rows.querySelectorAll(".row-select:not(:disabled)")];
  const checked = visible.filter((item) => item.checked).length;
  catalogElements.rows.querySelectorAll("tr").forEach((row) => {
    row.classList.toggle("is-selected", Boolean(row.querySelector(".row-select")?.checked));
  });
  catalogElements.selectAll.checked = visible.length > 0 && checked === visible.length;
  catalogElements.selectAll.indeterminate = checked > 0 && checked < visible.length;
  catalogElements.selectedCount.textContent = String(catalogState.selectedIds.size);
  catalogElements.prepare.disabled = catalogState.selectedIds.size === 0 || catalogState.loading;
}

function sortRecordings(key) {
  catalogState.sort = {
    key,
    direction: catalogState.sort.key === key && catalogState.sort.direction === "ascending" ? "descending" : "ascending",
  };
  document.querySelectorAll(".table-sort").forEach((button) => {
    button.setAttribute("aria-sort", button.dataset.sort === key ? catalogState.sort.direction : "none");
  });
  catalogState.page = 1;
  renderRecordingTable();
}

async function rescanCatalog() {
  if (catalogElements.rescan.disabled) return;
  catalogElements.rescan.disabled = true;
  catalogElements.rescan.classList.add("is-scanning");
  catalogElements.rescan.setAttribute("aria-label", "Scanning archive");
  catalogElements.lastScanned.textContent = "Scanning archive…";
  try {
    const result = await requestJson("/api/v1/catalog/rescan", { method: "POST", signal: routeController?.signal });
    await loadCatalog({ retained: true });
    announce(`Archive scan complete. ${result.scan.counts.recordings} recordings found.`);
  } catch (error) {
    if (error?.name !== "AbortError") {
      if (catalogState.data) renderCatalog();
      announce("Archive scan failed. The previous catalog is still visible.");
    }
  } finally {
    catalogElements.rescan.disabled = false;
    catalogElements.rescan.classList.remove("is-scanning");
    catalogElements.rescan.setAttribute("aria-label", "Rescan archive");
  }
}

function validatePrepareResponse(document, submittedIds) {
  if (!Array.isArray(document.recordings)) throw new ApiError("The preparation response was invalid.", "validation");
  const returned = new Set();
  document.recordings.forEach((recording) => {
    if (
      !submittedIds.includes(recording.recording_id)
      || returned.has(recording.recording_id)
      || typeof recording.outcome !== "string"
      || typeof recording.analysis_state !== "string"
      || !Array.isArray(recording.outputs)
    ) {
      throw new ApiError("The preparation response was invalid.", "validation");
    }
    returned.add(recording.recording_id);
    recording.outputs.forEach((output) => {
      if (!OUTPUT_ORDER.includes(output.kind) || typeof output.outcome !== "string" || typeof output.state !== "string") {
        throw new ApiError("The preparation response was invalid.", "validation");
      }
    });
  });
  if (returned.size !== submittedIds.length) throw new ApiError("The preparation response was incomplete.", "validation");
  return document;
}

async function prepareSelected() {
  if (catalogElements.prepare.disabled || !catalogState.data) return;
  const submitted = filteredRecordings().map((item) => item.id).filter((id) => catalogState.selectedIds.has(id));
  catalogState.data.recordings.forEach((item) => {
    if (catalogState.selectedIds.has(item.id) && !submitted.includes(item.id)) submitted.push(item.id);
  });
  catalogElements.prepare.disabled = true;
  catalogElements.prepare.setAttribute("aria-busy", "true");
  catalogElements.prepare.textContent = "Preparing…";
  try {
    const document = validatePrepareResponse(await requestJson("/api/v1/recordings/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recording_ids: submitted }),
      signal: routeController?.signal,
    }), submitted);
    const counts = { queued: 0, reused: 0, unavailable: 0, notFound: 0, failed: 0 };
    let activeWork = false;
    document.recordings.forEach((recording) => {
      recording.outputs.forEach((output) => {
        if (["queued", "retry_queued"].includes(output.outcome)) { counts.queued += 1; activeWork = true; }
        else if (output.outcome === "active_reused") { counts.reused += 1; activeWork = true; }
        else if (output.outcome === "ready_reused") counts.reused += 1;
        else if (output.outcome === "unavailable") counts.unavailable += 1;
        else counts.failed += 1;
      });
      if (recording.outcome === "not_found") counts.notFound += 1;
      if (recording.outcome === "request_failed") counts.failed += 1;
    });
    catalogState.selectedIds.clear();
    const summary = `${counts.queued} queued, ${counts.reused} reused, ${counts.unavailable} unavailable, ${counts.notFound} not found, ${counts.failed} failed.`;
    await loadCatalog({ retained: true });
    announce(summary);
    if (activeWork) navigate("/processing");
  } catch (error) {
    if (error?.name !== "AbortError") {
      announce("Preparation request failed. The selection has been retained.");
    }
  } finally {
    catalogElements.prepare.removeAttribute("aria-busy");
    catalogElements.prepare.textContent = "Prepare selected";
    updateSelectionState();
  }
}

function setProcessingTab(tab) {
  processingState.tab = tab;
  document.querySelectorAll("[data-job-filter]").forEach((button) => {
    const active = button.dataset.jobFilter === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  ["queue", "failures", "history"].forEach((name) => {
    byId(`processing-${name}-panel`).hidden = name !== (tab === "failed" ? "failures" : tab);
  });
  if (tab !== "queue") loadProcessingPage(tab, { append: false });
  else renderQueue();
}

function stopProcessingActivity() {
  if (processingState.pollTimer !== null) window.clearTimeout(processingState.pollTimer);
  processingState.pollTimer = null;
  processingState.pollController?.abort();
  processingState.pageController?.abort();
  processingState.pollController = null;
  processingState.pageController = null;
  if (processingState.elapsedFrame !== null) window.cancelAnimationFrame(processingState.elapsedFrame);
  processingState.elapsedFrame = null;
  processingState.elapsedAnchor = null;
}

function validateOverview(document) {
  if (typeof document.worker_online !== "boolean" || !Array.isArray(document.queue) || typeof document.recommended_poll_interval_ms !== "number") {
    throw new ApiError("The processing response was invalid.", "validation");
  }
  return document;
}

async function loadProcessing({ manual = false } = {}) {
  if (currentRoute?.view !== "processing" || processingState.pollController) return;
  if (manual) processingElements.refresh.disabled = true;
  const serial = ++processingState.requestSerial;
  const controller = new AbortController();
  processingState.pollController = controller;
  try {
    const overview = validateOverview(await requestJson("/api/v1/processing/overview", { signal: controller.signal }));
    if (serial !== processingState.requestSerial || currentRoute?.view !== "processing") return;
    processingState.overview = overview;
    processingState.pollFailures = 0;
    renderProcessingOverview();
    showNotice(processingElements.notice, overview.worker_online ? "" : "Worker offline. Queued work is paused until the serial worker returns.", overview.worker_online ? "" : "warning");
    if (processingState.tab !== "queue") await loadProcessingPage(processingState.tab, { append: false });
  } catch (error) {
    if (error?.name !== "AbortError") {
      processingState.pollFailures += 1;
      showNotice(processingElements.notice, `${error.message} Previously loaded processing facts are retained.`, "error");
    }
  } finally {
    if (processingState.pollController === controller) {
      processingState.pollController = null;
      processingElements.refresh.disabled = false;
      scheduleProcessingPoll();
    }
  }
}

function scheduleProcessingPoll() {
  if (processingState.pollTimer !== null) window.clearTimeout(processingState.pollTimer);
  processingState.pollTimer = null;
  if (currentRoute?.view !== "processing" || !processingState.autoRefresh || document.hidden) return;
  const recommended = processingState.overview?.recommended_poll_interval_ms || MINIMUM_POLL_MS;
  const base = Math.min(MAXIMUM_POLL_MS, Math.max(MINIMUM_POLL_MS, recommended));
  const delay = Math.min(MAXIMUM_POLL_MS, base * (2 ** Math.min(processingState.pollFailures, 5)));
  processingState.pollTimer = window.setTimeout(() => {
    processingState.pollTimer = null;
    loadProcessing();
  }, delay);
}

function renderProcessingOverview() {
  const overview = processingState.overview;
  if (!overview) return;
  byId("processing-queue-count").textContent = String(overview.queued_count);
  byId("processing-failed-count").textContent = String(overview.failed_count);
  byId("processing-history-count").textContent = String(overview.succeeded_count);
  processingElements.lastUpdate.textContent = `Updated ${formatDateTime(overview.server_time)}`;
  renderCurrentJob();
  renderQueue();
}

function processingLink(job, label = job.recording_name) {
  const link = node("a", label);
  link.href = `/recordings/${job.recording_id}`;
  link.dataset.route = "";
  return link;
}

function renderCurrentJob() {
  processingElements.currentHost.replaceChildren();
  const job = processingState.overview?.current;
  if (!job) {
    processingElements.currentHost.append(node("article", "No job is currently running.", "panel current-job current-job--empty"));
    stopElapsedTicker();
    return;
  }
  const article = node("article", null, "panel current-job");
  article.setAttribute("aria-label", "Current processing job");
  const heading = node("header", null, "current-job-heading");
  heading.append(node("span", "In progress"), node("span", processingState.overview.worker_online ? "Processing now" : "Worker offline", "current-job-activity"));
  const body = node("div", null, "current-job-body");
  const main = node("div", null, "current-job-main");
  const glyph = node("span", null, "current-job-icon");
  glyph.append(icon("processing"));
  const copy = node("div");
  copy.append(node("h2", OUTPUT_LABELS[job.kind] || humanize(job.kind)), processingLink(job));
  main.append(glyph, copy);
  const meta = node("dl", null, "current-job-meta");
  const metaItem = (label, value, className = "") => {
    const item = node("div");
    item.append(node("dt", label), node("dd", value, className));
    return item;
  };
  meta.append(
    metaItem("Started", formatAge(job.elapsed_ms)),
    metaItem("Elapsed", formatMilliseconds(job.elapsed_ms), "current-elapsed"),
    metaItem("Est. remaining", estimateText(job.estimate), "current-estimate"),
  );
  body.append(main, meta, node("span", estimateTotalText(job.estimate), "current-job-estimate"));
  const track = node("div", null, "indeterminate-track");
  track.append(node("i"));
  article.append(heading, body, track);
  processingElements.currentHost.append(article);
  startElapsedTicker(job);
}

function estimateText(estimate) {
  if (!estimate || estimate.status === "unavailable") return estimate?.sample_count === 0 ? "Not enough history" : "Estimating…";
  if (estimate.status === "exceeded") return "Estimate exceeded";
  return `≈ ${formatMilliseconds(estimate.remaining_ms)}`;
}

function estimateTotalText(estimate) {
  return estimate?.status === "available" ? `Approximately ${formatMilliseconds(estimate.estimated_total_ms)} total` : "Approximate timing may be unavailable";
}

function stopElapsedTicker() {
  if (processingState.elapsedFrame !== null) window.cancelAnimationFrame(processingState.elapsedFrame);
  processingState.elapsedFrame = null;
  processingState.elapsedAnchor = null;
}

function startElapsedTicker(job) {
  stopElapsedTicker();
  processingState.elapsedAnchor = { id: job.id, elapsedMs: job.elapsed_ms || 0, at: performance.now(), shownSecond: -1 };
  const tick = (now) => {
    const anchor = processingState.elapsedAnchor;
    if (!anchor || currentRoute?.view !== "processing" || processingState.overview?.current?.id !== anchor.id) return;
    const elapsed = anchor.elapsedMs + Math.max(0, now - anchor.at);
    const second = Math.floor(elapsed / 1000);
    if (second !== anchor.shownSecond) {
      anchor.shownSecond = second;
      const target = document.querySelector(".current-elapsed");
      if (target) target.textContent = formatMilliseconds(elapsed);
    }
    processingState.elapsedFrame = window.requestAnimationFrame(tick);
  };
  processingState.elapsedFrame = window.requestAnimationFrame(tick);
}

function renderQueue() {
  const queue = processingState.overview?.queue || [];
  const query = processingElements.search.value.trim().toLocaleLowerCase();
  const visible = queue.filter((job) => `${job.recording_name} ${OUTPUT_LABELS[job.kind] || job.kind}`.toLocaleLowerCase().includes(query));
  processingElements.queueRows.replaceChildren(...visible.map((job) => {
    const row = document.createElement("tr");
    row.append(node("td", job.queue_position ?? "—"));
    const recording = document.createElement("td");
    recording.append(processingLink(job));
    row.append(recording, node("td", OUTPUT_LABELS[job.kind] || humanize(job.kind)), node("td", formatAge(job.queued_age_ms)));
    const state = document.createElement("td");
    state.append(node("span", "Queued", "processing-state"));
    row.append(state);
    return row;
  }));
  processingElements.queueEmpty.hidden = visible.length !== 0;
  processingElements.queueDescription.textContent = queue.length === 1 ? "1 job waiting" : `${queue.length} jobs waiting`;
}

async function loadProcessingPage(view, { append = false } = {}) {
  if (!['failed', 'history'].includes(view) || currentRoute?.view !== "processing") return;
  processingState.pageController?.abort();
  const controller = new AbortController();
  processingState.pageController = controller;
  const serial = ++processingState.requestSerial;
  const previous = processingState.pages[view];
  const cursor = append ? previous?.next_cursor : null;
  const query = processingElements.search.value.trim();
  const params = new URLSearchParams({ view, limit: "25" });
  if (cursor) params.set("cursor", cursor);
  if (query) params.set("q", query);
  try {
    const page = await requestJson(`/api/v1/processing/jobs?${params}`, { signal: controller.signal });
    if (serial !== processingState.requestSerial || processingState.tab !== view || !Array.isArray(page.items)) return;
    if (view === "history") {
      if (!append) processingState.historyIds.clear();
      const items = append ? [...(previous?.items || [])] : [];
      page.items.forEach((item) => {
        if (!processingState.historyIds.has(item.id)) { items.push(item); processingState.historyIds.add(item.id); }
      });
      processingState.pages.history = { items, next_cursor: page.next_cursor };
    } else {
      processingState.pages.failed = page;
    }
    renderProcessingPage(view);
  } catch (error) {
    if (error?.name !== "AbortError") showNotice(processingElements.notice, `${error.message} The prior job page has been retained.`, "error");
  } finally {
    if (processingState.pageController === controller) processingState.pageController = null;
  }
}

function renderProcessingPage(view) {
  const page = processingState.pages[view] || { items: [], next_cursor: null };
  if (view === "failed") {
    processingElements.failureRows.replaceChildren(...page.items.map(createFailureRow));
    processingElements.failuresEmpty.hidden = page.items.length !== 0;
  } else {
    processingElements.historyRows.replaceChildren(...page.items.map(createHistoryRow));
    processingElements.historyEmpty.hidden = page.items.length !== 0;
    processingElements.historyDescription.textContent = `Showing ${page.items.length} completed jobs`;
    processingElements.historyMore.hidden = !page.next_cursor;
  }
}

function createFailureRow(job) {
  const row = document.createElement("tr");
  const recording = document.createElement("td");
  recording.append(processingLink(job));
  row.append(
    recording,
    node("td", OUTPUT_LABELS[job.kind] || humanize(job.kind)),
    node("td", formatDateTime(job.finished_at)),
    node("td", formatMilliseconds(job.runtime_ms)),
    node("td", job.diagnostic?.message || "Processing failed.", "failure-reason"),
  );
  const actions = node("td");
  const host = node("div", null, "processing-row-actions");
  const retry = node("button", "Retry", "job-action-primary");
  retry.type = "button";
  retry.addEventListener("click", () => retryJob(job, retry));
  const details = node("button", "Details");
  details.type = "button";
  details.addEventListener("click", () => showFailureDialog(job, details));
  host.append(retry, details);
  actions.append(host);
  row.append(actions);
  return row;
}

function createHistoryRow(job) {
  const row = document.createElement("tr");
  const recording = document.createElement("td");
  recording.append(processingLink(job));
  row.append(
    recording,
    node("td", OUTPUT_LABELS[job.kind] || humanize(job.kind)),
    node("td", formatDateTime(job.finished_at)),
    node("td", formatMilliseconds(job.runtime_ms)),
    node("td", formatBytes(job.output_size_bytes)),
  );
  const action = document.createElement("td");
  action.append(processingLink(job, "Open"));
  row.append(action);
  return row;
}

let dialogReturnFocus = null;
function showFailureDialog(job, trigger) {
  dialogReturnFocus = trigger;
  processingElements.dialogTitle.textContent = `${OUTPUT_LABELS[job.kind] || humanize(job.kind)} · ${job.recording_name}`;
  processingElements.dialogCopy.textContent = job.diagnostic?.message || "Processing failed.";
  processingElements.dialogMeta.replaceChildren();
  [["Code", job.diagnostic?.code || "processing_failed"], ["Attempted", formatDateTime(job.finished_at)], ["Runtime", formatMilliseconds(job.runtime_ms)], ["Recording", job.recording_name]].forEach(([label, value]) => {
    const item = node("div");
    item.append(node("dt", label), node("dd", value));
    processingElements.dialogMeta.append(item);
  });
  processingElements.dialog.showModal();
}

function closeFailureDialog() {
  processingElements.dialog.close();
  dialogReturnFocus?.focus();
  dialogReturnFocus = null;
}

async function retryJob(job, button) {
  button.disabled = true;
  button.textContent = "Retrying…";
  try {
    const generation = routeGeneration;
    const result = await requestJson(`/api/v1/processing/jobs/${job.id}/retry`, {
      method: "POST",
      signal: routeController?.signal,
    });
    if (generation !== routeGeneration || currentRoute?.view !== "processing") return;
    announce(result.state === "ready" ? "Compatible output is already ready." : "A current processing attempt is queued or active.");
    await loadProcessing({ manual: true });
    if (processingState.tab === "failed") await loadProcessingPage("failed", { append: false });
  } catch (error) {
    showNotice(processingElements.notice, error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Retry";
  }
}

function resetAnalyzer(message = "Loading recording details…") {
  detailElements.name.textContent = "—";
  [detailElements.recorded, detailElements.duration, detailElements.size, detailElements.storage, detailElements.messages, detailElements.topics, detailElements.health].forEach((item) => { item.textContent = "—"; });
  detailElements.error.hidden = true;
  detailElements.components.replaceChildren();
  detailElements.outputs.replaceChildren();
  detailElements.componentCount.textContent = "0";
  detailElements.action.hidden = true;
  detailElements.outputs.closest(".metadata-section")?.classList.add("is-terminal");
  resetPreview("front", message, "Loading", "loading");
  resetPreview("topdown", message, "Loading", "loading");
  resetImu(message, "Loading", "loading");
  resetTimeline();
}

async function loadRecordingDetail(recordingId) {
  resetAnalyzer();
  const generation = routeGeneration;
  try {
    const detail = await requestJson(`/api/v1/recordings/${recordingId}`, { signal: routeController.signal });
    if (generation !== routeGeneration || currentRoute?.recordingId !== recordingId) return;
    validateDetail(detail, recordingId);
    renderDetail(detail);
    announce(`${detail.name} loaded.`);
  } catch (error) {
    if (error?.name === "AbortError") return;
    detailElements.error.textContent = error.message;
    detailElements.error.hidden = false;
    resetPreview("front", error.message, "Unavailable", "failed");
    resetPreview("topdown", error.message, "Unavailable", "failed");
    resetImu(error.message, "Unavailable", "failed");
    announce("Recording details could not be loaded.");
  }
}

function validateDetail(detail, recordingId) {
  if (detail.id !== recordingId || !Array.isArray(detail.components) || !Array.isArray(detail.outputs)) {
    throw new ApiError("The recording detail response was invalid.", "validation");
  }
  const kinds = detail.outputs.map((output) => output.kind);
  if (OUTPUT_ORDER.some((kind) => !kinds.includes(kind))) throw new ApiError("The recording output response was incomplete.", "validation");
}

function renderDetail(detail) {
  detailElements.name.textContent = detail.name;
  detailElements.recorded.textContent = formatRecorded(detail.start_time_ns);
  detailElements.duration.textContent = formatDurationNanoseconds(detail.duration_ns);
  detailElements.size.textContent = formatBytes(detail.total_source_size_bytes);
  if (detail.storage_format) detailElements.storage.replaceChildren(node("code", detail.storage_format));
  else detailElements.storage.textContent = "Unavailable";
  detailElements.messages.textContent = formatCount(detail.message_count);
  detailElements.topics.textContent = detail.topic_count === null ? "Unavailable" : String(detail.topic_count);
  detailElements.health.replaceChildren(metadataStatus(
    humanize(detail.ros_health),
    detail.presentation_health === "readable" ? "metadata-status--good" : "metadata-status--bad",
  ));
  detailElements.error.textContent = detail.diagnostic?.message || "";
  detailElements.error.hidden = !detail.diagnostic;
  renderComponents(detail.components);
  renderOutputFacts(detail.outputs);
  reviewController = createGlobalTimeline(detail);
  const outputs = outputFacts(detail);
  renderPreviewOutput("front", detail, outputs.get("front_preview"));
  renderPreviewOutput("topdown", detail, outputs.get("topdown_preview"));
  renderImuOutput(detail, outputs.get("imu_series"));
  renderAnalyzerAction(detail);
}

function renderComponents(components) {
  detailElements.components.replaceChildren();
  detailElements.componentCount.textContent = String(components.length);
  components.forEach((component) => {
    const item = node("article", null, "metadata-item");
    const copy = node("div");
    const name = node("strong", ROLE_LABELS[component.role] || humanize(component.role));
    const description = component.diagnostic?.message
      ? `${component.file_name || "No file"} — ${component.diagnostic.message}`
      : component.file_name || "No file";
    const file = node("span", description);
    file.title = component.file_name || "No file";
    copy.append(name, file);
    const facts = node("div");
    facts.append(
      node("small", formatBytes(component.size_bytes)),
      metadataStatus(
        humanize(component.condition),
        `metadata-status--${component.condition === "readable" || component.condition === "present" ? "good" : "bad"}`,
      ),
    );
    item.append(copy, facts);
    if (component.diagnostic) item.title = component.diagnostic.message;
    detailElements.components.append(item);
  });
}

function renderOutputFacts(outputs) {
  detailElements.outputs.replaceChildren();
  outputs.forEach((output) => {
    const item = node("article", null, "metadata-item");
    const copy = node("div");
    let description = output.diagnostic?.message || "No current compatible file";
    if (output.artifact) {
      const coverageStart = formatSignedSeconds(Number(BigInt(output.artifact.coverage_start_ns)) / 1e9);
      const coverageEnd = formatSignedSeconds(Number(BigInt(output.artifact.coverage_end_ns)) / 1e9);
      description = `${output.artifact.mime_type} · coverage ${coverageStart}–${coverageEnd}`;
    }
    copy.append(node("strong", OUTPUT_LABELS[output.kind] || humanize(output.kind)), node("span", description));
    const facts = node("div");
    facts.append(
      node("small", output.artifact ? formatBytes(output.artifact.size_bytes) : "No ready file"),
      metadataStatus(
        humanize(output.state),
        `metadata-status--${output.state === "ready" ? "good" : "neutral"}`,
      ),
    );
    item.append(copy, facts);
    if (output.diagnostic) item.title = output.diagnostic.message;
    detailElements.outputs.append(item);
  });
}

function renderAnalyzerAction(detail) {
  const outputSection = detailElements.outputs.closest(".metadata-section");
  if (detail.analysis_state === "ready") {
    detailElements.action.hidden = true;
    outputSection?.classList.add("is-terminal");
    return;
  }
  outputSection?.classList.remove("is-terminal");
  detailElements.action.replaceChildren();
  detailElements.action.append(node("p", "This recording is not completely prepared. Review the current output states above."));
  const target = detail.outputs.some((output) => ["queued", "processing", "failed"].includes(output.state)) ? "/processing" : "/";
  if (target === "/processing") {
    const link = node("a", "Open Processing");
    link.href = target;
    link.dataset.route = "";
    detailElements.action.append(link);
  }
  detailElements.action.hidden = false;
}

function previewElements(kind) {
  const prefix = kind === "front" ? "front" : "topdown";
  return {
    pane: byId(`${prefix}-preview-pane`), badge: byId(`${prefix}-state-badge`), video: byId(`${prefix}-video`),
    message: byId(`${prefix}-message`), messageTitle: byId(`${prefix}-message-title`), status: byId(`${prefix}-status`),
    action: byId(`${prefix}-state-action`), coverage: byId(`${prefix}-coverage`), retry: byId(`${prefix}-media-retry`),
  };
}

function setStateBadge(element, label, state) {
  element.textContent = label;
  element.className = `state-badge ${state || ""}`.trim();
  element.hidden = state === "ready";
}

function resetVideo(video) {
  video.pause();
  video.removeAttribute("src");
  if (typeof video.load === "function") video.load();
  video.hidden = true;
}

function resetPreview(kind, message, badge = "Not planned", state = "not_requested") {
  const elements = previewElements(kind);
  removePlayer(kind);
  resetVideo(elements.video);
  elements.pane.setAttribute("aria-busy", String(state === "loading"));
  elements.message.hidden = false;
  elements.messageTitle.textContent = badge;
  elements.status.textContent = message;
  elements.action.hidden = true;
  elements.coverage.hidden = true;
  elements.retry.hidden = true;
  setStateBadge(elements.badge, badge, state);
}

function outputStateAction(elements, state) {
  if (!["queued", "processing", "failed"].includes(state)) {
    elements.action.hidden = true;
    elements.action.onclick = null;
    return;
  }
  elements.action.textContent = "Open Processing";
  elements.action.hidden = false;
  elements.action.onclick = () => navigate("/processing");
}

function renderPreviewOutput(kind, detail, output) {
  const elements = previewElements(kind);
  const label = output.state === "not_requested" ? "Not planned" : humanize(output.state);
  resetPreview(kind, output.diagnostic?.message || "No current compatible output is ready.", label, output.state);
  elements.pane.setAttribute("aria-busy", String(["queued", "processing"].includes(output.state)));
  if (output.state !== "ready" || !output.artifact) {
    elements.messageTitle.textContent = label;
    elements.status.textContent = output.diagnostic?.message || {
      not_requested: "Use Prepare selected on Recordings to request the complete analyzer bundle.",
      queued: "Waiting for the one serial worker.",
      processing: "The serial worker is preparing this output.",
      failed: "The current processing attempt failed.",
      unavailable: "The current source or configuration cannot produce this output.",
    }[output.state] || "This output is unavailable.";
    outputStateAction(elements, output.state);
    return;
  }
  attachReadyVideo(kind, detail.id, output.artifact);
}

function validArtifactUrl(kind, recordingId, artifact) {
  const route = kind === "front" ? "front-preview" : kind === "topdown" ? "topdown-preview" : "imu-series";
  const type = kind === "imu" ? "data" : "media";
  return typeof artifact.url === "string" && artifact.url === `/api/recordings/${recordingId}/${route}/${type}/${artifact.id}`;
}

function attachReadyVideo(kind, recordingId, artifact) {
  const elements = previewElements(kind);
  if (!validArtifactUrl(kind, recordingId, artifact)) {
    resetPreview(kind, "The ready artifact URL was invalid.", "Data unavailable", "failed");
    return;
  }
  const coverageStart = Number(BigInt(artifact.coverage_start_ns)) / 1e9;
  const coverageEnd = Number(BigInt(artifact.coverage_end_ns)) / 1e9;
  elements.video.src = artifact.url;
  elements.video.hidden = false;
  elements.message.hidden = true;
  setStateBadge(elements.badge, "Ready", "ready");
  elements.retry.onclick = () => {
    resetVideo(elements.video);
    elements.video.src = artifact.url;
    elements.video.hidden = false;
    elements.message.hidden = true;
    elements.coverage.hidden = true;
    elements.retry.hidden = true;
    const player = reviewController?.players[kind];
    if (player) player.mediaFailed = false;
    setStateBadge(elements.badge, "Ready", "ready");
  };
  reviewController.players[kind] = {
    video: elements.video, coverageStart, coverageEnd, coverageMessage: elements.coverage,
    mediaRetry: elements.retry, mediaFailed: false, insideCoverage: false, playAttempt: 0, playPending: false,
    buffering: false, seekPending: false, seekRequestedAt: null, seekTarget: null,
  };
  updateTransportAvailability();
  applyGlobalTime(reviewController.clock.globalTime, true);
}

function formatSignedSeconds(value) {
  return `${value < 0 ? "−" : ""}${formatSeconds(Math.abs(value), true)}`;
}

function resetImu(message, badge = "Not planned", state = "not_requested") {
  removeImuGraph();
  imuElements.pane.setAttribute("aria-busy", String(state === "loading"));
  imuElements.message.hidden = false;
  imuElements.messageTitle.textContent = badge;
  imuElements.status.textContent = message;
  imuElements.action.hidden = true;
  imuElements.graph.hidden = true;
  imuElements.warnings.replaceChildren();
  imuElements.currentValue.textContent = "—";
  imuElements.pickerTrigger.disabled = true;
  setStateBadge(imuElements.badge, badge, state);
}

function renderImuOutput(detail, output) {
  const label = output.state === "not_requested" ? "Not planned" : humanize(output.state);
  resetImu(output.diagnostic?.message || "No current compatible IMU bundle is ready.", label, output.state);
  imuElements.pane.setAttribute("aria-busy", String(["queued", "processing"].includes(output.state)));
  if (output.state !== "ready" || !output.artifact) {
    imuElements.status.textContent = output.diagnostic?.message || {
      not_requested: "Use Prepare selected on Recordings to request the complete analyzer bundle.",
      queued: "Waiting for the one serial worker.",
      processing: "The serial worker is extracting six IMU channels.",
      failed: "The current IMU attempt failed.",
      unavailable: "The current source or configuration cannot provide IMU output.",
    }[output.state] || "IMU output is unavailable.";
    outputStateAction(imuElements, output.state);
    return;
  }
  loadReadyImu(detail.id, output.artifact);
}

async function loadReadyImu(recordingId, v1Artifact) {
  if (!validArtifactUrl("imu", recordingId, v1Artifact)) {
    resetImu("The ready IMU artifact URL was invalid.", "Data unavailable", "failed");
    return;
  }
  imuElements.pane.setAttribute("aria-busy", "true");
  imuElements.messageTitle.textContent = "Loading telemetry";
  imuElements.status.textContent = "Loading and validating the six-channel IMU bundle…";
  try {
    const state = await requestJson(`/api/recordings/${recordingId}/imu-series`, { signal: routeController.signal });
    const artifact = state.artifact;
    if (state.state !== "ready" || !artifact || artifact.data_url !== v1Artifact.url || !Array.isArray(artifact.series)) {
      throw new ApiError("The IMU artifact identity no longer matches the recording detail.", "validation");
    }
    const document = await requestJson(artifact.data_url, { signal: routeController.signal });
    if (currentRoute?.recordingId !== recordingId || !reviewController) return;
    const parsed = window.ImuGraph.parseSeries(document, artifact);
    renderImuGraph(artifact, parsed);
  } catch (error) {
    if (error?.name === "AbortError") return;
    resetImu("The ready IMU data could not be loaded and validated.", "Data unavailable", "failed");
    imuElements.action.textContent = "Reload data";
    imuElements.action.hidden = false;
    imuElements.action.onclick = () => loadReadyImu(recordingId, v1Artifact);
  } finally {
    imuElements.pane.setAttribute("aria-busy", "false");
  }
}

function renderImuGraph(artifact, parsed) {
  if (!reviewController) return;
  imuElements.message.hidden = true;
  imuElements.graph.hidden = false;
  imuElements.pickerTrigger.disabled = false;
  setStateBadge(imuElements.badge, "Ready", "ready");
  const telemetry = {
    artifact, parsed, selectedSeriesId: null, samples: [], coverageStart: parsed.coverageStart,
    coverageEnd: parsed.coverageEnd, minimumValue: 0, maximumValue: 0, units: "",
    canvas: imuElements.canvas, plot: imuElements.plot, cursor: imuElements.cursor,
    currentValue: imuElements.currentValue, currentState: imuElements.currentState,
    plotLeft: 0, plotWidth: 1, resizeObserver: null, lastCursorTransform: null, lastReadoutKey: null,
  };
  reviewController.telemetry = telemetry;
  populateSensorPicker(parsed.series);
  let resizeFrame = null;
  telemetry.resizeObserver = new ResizeObserver(() => {
    if (resizeFrame !== null) window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = null;
      if (reviewController?.telemetry === telemetry) {
        drawImuTrace(telemetry);
        updateImuAtGlobalTime(reviewController.clock.globalTime);
      }
    });
  });
  telemetry.resizeObserver.observe(imuElements.plot);
  applyImuSeriesSelection(parsed.defaultSeriesId);
  updateTransportAvailability();
  applyGlobalTime(reviewController.clock.globalTime, true);
}

function populateSensorPicker(series) {
  imuElements.pickerMenu.replaceChildren();
  [["Angular velocity", "angular_velocity"], ["Linear acceleration", "linear_acceleration"]].forEach(([label, prefix]) => {
    const group = node("div", null, "sensor-picker-group");
    group.setAttribute("role", "presentation");
    group.append(node("span", label));
    series.filter((item) => item.component.startsWith(prefix)).forEach((definition) => {
      const button = node("button");
      button.type = "button";
      button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", "false");
      button.dataset.sensor = definition.id;
      button.disabled = !definition.available;
      button.append(node("i"), node("span", definition.component), node("small", definition.units));
      button.addEventListener("click", () => applyImuSeriesSelection(definition.id));
      group.append(button);
    });
    imuElements.pickerMenu.append(group);
  });
}

function applyImuSeriesSelection(seriesId) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return;
  const selected = window.ImuGraph.selectSeries(telemetry.parsed, seriesId);
  telemetry.selectedSeriesId = selected.id;
  telemetry.samples = selected.samples;
  telemetry.minimumValue = selected.minimumValue;
  telemetry.maximumValue = selected.maximumValue;
  telemetry.units = selected.units;
  telemetry.lastReadoutKey = null;
  imuElements.selectedLabel.textContent = selected.component;
  imuElements.pickerMenu.querySelectorAll("[data-sensor]").forEach((button) => {
    const active = button.dataset.sensor === seriesId;
    button.classList.toggle("is-selected", active);
    button.setAttribute("aria-checked", String(active));
  });
  imuElements.pickerMenu.hidden = true;
  imuElements.pickerTrigger.setAttribute("aria-expanded", "false");
  imuElements.plot.setAttribute("aria-label", `${selected.displayLabel} graph recording time`);
  imuElements.summary.textContent = `${selected.displayLabel} graph on the recording timeline`;
  imuElements.warnings.replaceChildren();
  if (selected.nonFiniteCount > 0) {
    imuElements.warnings.append(node(
      "p",
      `${selected.nonFiniteCount.toLocaleString()} sample gap${selected.nonFiniteCount === 1 ? "" : "s"} remain visible as breaks in this series.`,
    ));
  }
  drawImuTrace(telemetry);
  updateImuAtGlobalTime(reviewController.clock.globalTime);
}

function drawImuTrace(telemetry) {
  const rect = telemetry.plot.getBoundingClientRect();
  const width = Math.max(1, Math.floor(rect.width));
  const height = Math.max(160, Math.floor(rect.height));
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  telemetry.canvas.width = Math.floor(width * ratio);
  telemetry.canvas.height = Math.floor(height * ratio);
  telemetry.canvas.style.width = `${width}px`;
  telemetry.canvas.style.height = `${height}px`;
  const context = telemetry.canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  const left = 28;
  const right = 28;
  const top = 30;
  const bottom = 40;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  telemetry.plotLeft = left;
  telemetry.plotWidth = plotWidth;
  let minimum = telemetry.minimumValue;
  let maximum = telemetry.maximumValue;
  if (minimum === maximum) { const padding = Math.max(1, Math.abs(minimum) * 0.1); minimum -= padding; maximum += padding; }
  const padding = (maximum - minimum) * 0.08;
  minimum -= padding;
  maximum += padding;
  const y = (value) => top + ((maximum - value) / (maximum - minimum)) * plotHeight;
  const duration = reviewController?.durationSeconds || 0;
  const x = (value) => left + window.ImuGraph.cursorFraction(value, duration) * plotWidth;
  const middle = minimum <= 0 && maximum >= 0 ? 0 : (minimum + maximum) / 2;
  const horizontalValues = [maximum, middle, minimum];
  context.font = "9px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textAlign = "left";
  context.textBaseline = "bottom";
  horizontalValues.forEach((value) => {
    const lineY = y(value);
    context.beginPath();
    context.moveTo(left, lineY + 0.5);
    context.lineTo(left + plotWidth, lineY + 0.5);
    context.strokeStyle = value === middle ? "#303235" : "#202224";
    context.lineWidth = value === middle ? 1.5 : 1;
    context.stroke();
    context.fillStyle = "#787878";
    context.fillText(value.toFixed(2), left, lineY - 4);
  });
  context.save(); context.beginPath(); context.rect(left, top, plotWidth, plotHeight); context.clip();
  const gradient = context.createLinearGradient(0, top, 0, top + plotHeight);
  gradient.addColorStop(0, "rgba(167, 206, 251, 0.24)");
  gradient.addColorStop(1, "rgba(167, 206, 251, 0.015)");
  context.strokeStyle = "#a7cefb";
  context.lineWidth = 1.35;
  window.ImuGraph.traceSegments(telemetry.samples).forEach((segment) => {
    const visible = segment.filter((sample) => sample.timeSeconds >= 0 && sample.timeSeconds <= duration);
    if (!visible.length) return;
    if (visible.length === 1) {
      context.fillStyle = "#a7cefb";
      context.beginPath();
      context.arc(x(visible[0].timeSeconds), y(visible[0].value), 2, 0, Math.PI * 2);
      context.fill();
      return;
    }
    const tracePath = () => {
      context.beginPath();
      context.moveTo(x(visible[0].timeSeconds), y(visible[0].value));
      visible.slice(1).forEach((sample) => context.lineTo(x(sample.timeSeconds), y(sample.value)));
    };
    tracePath();
    context.lineTo(x(visible.at(-1).timeSeconds), top + plotHeight);
    context.lineTo(x(visible[0].timeSeconds), top + plotHeight);
    context.closePath();
    context.fillStyle = gradient;
    context.fill();
    tracePath();
    context.strokeStyle = "#a7cefb";
    context.stroke();
  });
  context.restore();
  context.fillStyle = "#787878";
  context.font = "9px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textBaseline = "alphabetic";
  context.textAlign = "left"; context.fillText("0:00", left, height - 9);
  context.textAlign = "right"; context.fillText(formatSeconds(duration, false), left + plotWidth, height - 9);
}

function updateImuAtGlobalTime(globalTime) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return;
  const position = window.ImuGraph.snappedCursorPosition(globalTime, reviewController.durationSeconds, telemetry.plotLeft, telemetry.plotWidth, window.devicePixelRatio || 1);
  const transform = `translate3d(${position}px, 0, 0)`;
  if (transform !== telemetry.lastCursorTransform) { telemetry.cursor.style.transform = transform; telemetry.lastCursorTransform = transform; }
  const inside = globalTime >= telemetry.coverageStart && globalTime <= telemetry.coverageEnd;
  telemetry.cursor.classList.toggle("outside-coverage", !inside);
  if (!inside) { updateImuReadout(telemetry, "outside", "—", "Outside IMU coverage"); return; }
  const sample = window.ImuGraph.sampleAtOrBefore(telemetry.samples, globalTime);
  if (!sample || sample.value === null) { updateImuReadout(telemetry, sample ? `null-${sample.timeNs}` : "none", "—", "No finite IMU value at this time"); return; }
  updateImuReadout(telemetry, `sample-${sample.timeNs}-${telemetry.selectedSeriesId}`, `${sample.value.toFixed(4)} ${telemetry.units}`, "");
}

function updateImuReadout(telemetry, key, value, state) {
  if (telemetry.lastReadoutKey === key) return;
  telemetry.lastReadoutKey = key;
  telemetry.currentValue.textContent = value;
  telemetry.currentState.textContent = state;
}

function removeImuGraph() {
  if (imuSeekAnimation !== null) window.cancelAnimationFrame(imuSeekAnimation);
  imuSeekAnimation = null;
  pendingImuSeekTime = null;
  if (activeImuPointerId !== null && imuElements.plot.hasPointerCapture?.(activeImuPointerId)) imuElements.plot.releasePointerCapture(activeImuPointerId);
  activeImuPointerId = null;
  imuElements.plot.classList.remove("is-seeking");
  imuElements.pickerMenu.hidden = true;
  imuElements.pickerMenu.replaceChildren();
  imuElements.pickerTrigger.setAttribute("aria-expanded", "false");
  imuElements.selectedLabel.textContent = "angular_velocity.z";
  if (!reviewController?.telemetry) return;
  reviewController.telemetry.resizeObserver?.disconnect();
  reviewController.telemetry = null;
  updateTransportAvailability();
}

function createGlobalTimeline(detail) {
  resetTimeline();
  const durationSeconds = detail.duration_ns === null ? 0 : Number(BigInt(detail.duration_ns)) / 1e9;
  const startSeconds = detail.start_time_ns === null ? null : Number(BigInt(detail.start_time_ns)) / 1e9;
  timelineElements.slider.max = String(durationSeconds);
  timelineElements.total.textContent = startSeconds === null ? formatSeconds(durationSeconds, true) : (startSeconds + durationSeconds).toFixed(3);
  return { recordingId: detail.id, durationSeconds, startSeconds, players: {}, telemetry: null, clock: { globalTime: 0, playing: false, anchorGlobal: 0, anchorPerformance: 0 } };
}

function resetTimeline() {
  timelineElements.play.disabled = true;
  timelineElements.play.classList.remove("is-playing");
  timelineElements.play.setAttribute("aria-pressed", "false");
  timelineElements.play.setAttribute("aria-label", "Play timeline");
  timelineElements.slider.disabled = true;
  timelineElements.slider.min = "0";
  timelineElements.slider.max = "0";
  timelineElements.slider.value = "0";
  timelineElements.current.textContent = "0:00.000";
  timelineElements.total.textContent = "0:00.000";
}

function pausePlayer(player) {
  player.playAttempt += 1;
  player.playPending = false;
  player.video.pause();
}

function clearPlayerSeek(player) {
  player.seekPending = false;
  player.seekRequestedAt = null;
  player.seekTarget = null;
}

function requestPlayerTime(player, desired, explicit = false) {
  if (player.video.readyState < 1) return false;
  const target = Number.isFinite(player.video.duration) ? Math.min(desired, player.video.duration) : desired;
  if (!explicit && Math.abs(player.video.currentTime - target) <= VIDEO_DRIFT_TOLERANCE_SECONDS) return false;
  if (!explicit && player.buffering) return false;
  if (!explicit && (player.seekPending || player.video.seeking)) {
    const pendingFor = player.seekRequestedAt === null ? 0 : performance.now() - player.seekRequestedAt;
    if (pendingFor < VIDEO_SEEK_RETRY_MS) return false;
  }
  player.seekPending = true;
  player.seekRequestedAt = performance.now();
  player.seekTarget = target;
  player.video.currentTime = target;
  return true;
}

function removePlayer(kind) {
  const player = reviewController?.players[kind];
  if (!player) return;
  pausePlayer(player);
  delete reviewController.players[kind];
  updateTransportAvailability();
}

function stopReviewActivity() {
  if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
  timelineAnimation = null;
  if (reviewController) {
    Object.values(reviewController.players).forEach(pausePlayer);
    reviewController.telemetry?.resizeObserver?.disconnect();
  }
  reviewController = null;
}

function setPlaybackState(playing) {
  timelineElements.play.classList.toggle("is-playing", playing);
  timelineElements.play.setAttribute("aria-pressed", String(playing));
  timelineElements.play.setAttribute("aria-label", playing ? "Pause timeline" : "Play timeline");
  timelineElements.play.title = playing ? "Pause timeline" : "Play timeline";
}

function updateTimelineOutput() {
  if (!reviewController) return;
  const current = reviewController.clock.globalTime;
  timelineElements.slider.value = String(current);
  const absolute = reviewController.startSeconds === null ? null : reviewController.startSeconds + current;
  timelineElements.current.textContent = absolute === null ? formatSeconds(current, true) : absolute.toFixed(3);
  const accessible = `${formatSeconds(current, true)} elapsed of ${formatSeconds(reviewController.durationSeconds, true)}`;
  timelineElements.play.setAttribute("aria-description", accessible);
  imuElements.plot.setAttribute("aria-valuemax", String(reviewController.durationSeconds));
  imuElements.plot.setAttribute("aria-valuenow", String(current));
  imuElements.plot.setAttribute("aria-valuetext", accessible);
}

function applyGlobalTime(value, forceSeek = false) {
  if (!reviewController) return;
  const controller = reviewController;
  controller.clock.globalTime = Math.min(Math.max(Number(value) || 0, 0), controller.durationSeconds);
  updateTimelineOutput();
  Object.entries(controller.players).forEach(([kind, player]) => {
    if (player.mediaFailed) return;
    const inside = controller.clock.globalTime >= player.coverageStart && controller.clock.globalTime <= player.coverageEnd;
    if (!inside) {
      if (!player.video.paused || player.playPending) pausePlayer(player);
      clearPlayerSeek(player);
      player.video.hidden = true;
      player.coverageMessage.hidden = false;
      player.insideCoverage = false;
      return;
    }
    const entered = !player.insideCoverage;
    player.insideCoverage = true;
    player.coverageMessage.hidden = true;
    player.video.hidden = false;
    const desired = controller.clock.globalTime - player.coverageStart;
    requestPlayerTime(player, desired, forceSeek || entered);
    if (controller.clock.playing && player.video.paused && !player.playPending) {
      const attempt = ++player.playAttempt;
      player.playPending = true;
      player.video.play().then(() => { if (player.playAttempt === attempt) player.playPending = false; }).catch(() => {
        if (player.playAttempt === attempt && reviewController === controller) showMediaFailure(kind);
      });
    } else if (!controller.clock.playing && (!player.video.paused || player.playPending)) pausePlayer(player);
  });
  updateImuAtGlobalTime(controller.clock.globalTime);
}

function updateTransportAvailability() {
  if (!reviewController) return;
  const usablePlayers = Object.values(reviewController.players).filter((player) => !player.mediaFailed);
  const usable = (usablePlayers.length > 0 || reviewController.telemetry) && reviewController.durationSeconds > 0;
  timelineElements.play.disabled = !usable;
  timelineElements.slider.disabled = !usable;
  imuElements.plot.tabIndex = reviewController.telemetry ? 0 : -1;
  if (!usable && reviewController.clock.playing) {
    reviewController.clock.playing = false;
    setPlaybackState(false);
    if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
  }
}

function togglePlayback() {
  if (!reviewController || timelineElements.play.disabled) return;
  const clock = reviewController.clock;
  if (clock.playing) {
    clock.playing = false;
    setPlaybackState(false);
    if (timelineAnimation !== null) window.cancelAnimationFrame(timelineAnimation);
    timelineAnimation = null;
    applyGlobalTime(clock.globalTime);
    return;
  }
  if (clock.globalTime >= reviewController.durationSeconds) applyGlobalTime(0, true);
  clock.playing = true;
  clock.anchorGlobal = clock.globalTime;
  clock.anchorPerformance = performance.now();
  setPlaybackState(true);
  applyGlobalTime(clock.globalTime);
  timelineAnimation = window.requestAnimationFrame(tickTimeline);
}

function tickTimeline(now) {
  if (!reviewController?.clock.playing) return;
  const clock = reviewController.clock;
  const next = Math.min(reviewController.durationSeconds, clock.anchorGlobal + (now - clock.anchorPerformance) / 1000);
  const ended = next >= reviewController.durationSeconds;
  if (ended) clock.playing = false;
  applyGlobalTime(next);
  if (ended) { setPlaybackState(false); timelineAnimation = null; return; }
  timelineAnimation = window.requestAnimationFrame(tickTimeline);
}

function seekGlobalTime(value) {
  if (!reviewController) return;
  applyGlobalTime(value, true);
  if (reviewController.clock.playing) {
    reviewController.clock.anchorGlobal = reviewController.clock.globalTime;
    reviewController.clock.anchorPerformance = performance.now();
  }
}

function imuTimeFromPointer(event) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return null;
  const bounds = telemetry.plot.getBoundingClientRect();
  return window.ImuGraph.timeFromPlotPosition(event.clientX - (bounds.left || 0), telemetry.plotLeft, telemetry.plotWidth, reviewController.durationSeconds);
}

function beginImuSeek(event) {
  if (!reviewController?.telemetry || activeImuPointerId !== null || event.isPrimary === false || (event.pointerType === "mouse" && event.button !== 0)) return;
  const value = imuTimeFromPointer(event);
  if (value === null) return;
  activeImuPointerId = event.pointerId;
  imuElements.plot.setPointerCapture?.(event.pointerId);
  imuElements.plot.classList.add("is-seeking");
  event.preventDefault();
  seekGlobalTime(value);
}

function moveImuSeek(event) {
  if (event.pointerId !== activeImuPointerId) return;
  pendingImuSeekTime = imuTimeFromPointer(event);
  if (pendingImuSeekTime === null || imuSeekAnimation !== null) return;
  event.preventDefault();
  imuSeekAnimation = window.requestAnimationFrame(() => {
    imuSeekAnimation = null;
    const value = pendingImuSeekTime;
    pendingImuSeekTime = null;
    seekGlobalTime(value);
  });
}

function endImuSeek(event) {
  if (event.pointerId !== activeImuPointerId) return;
  if (imuSeekAnimation !== null) window.cancelAnimationFrame(imuSeekAnimation);
  imuSeekAnimation = null;
  pendingImuSeekTime = null;
  const value = imuTimeFromPointer(event);
  if (value !== null) seekGlobalTime(value);
  if (imuElements.plot.hasPointerCapture?.(event.pointerId)) imuElements.plot.releasePointerCapture(event.pointerId);
  activeImuPointerId = null;
  imuElements.plot.classList.remove("is-seeking");
  event.preventDefault();
}

function cancelImuSeek(event) {
  if (event.pointerId !== activeImuPointerId) return;
  if (imuSeekAnimation !== null) window.cancelAnimationFrame(imuSeekAnimation);
  imuSeekAnimation = null;
  pendingImuSeekTime = null;
  if (imuElements.plot.hasPointerCapture?.(event.pointerId)) imuElements.plot.releasePointerCapture(event.pointerId);
  activeImuPointerId = null;
  imuElements.plot.classList.remove("is-seeking");
}

function keyboardImuSeek(event) {
  if (!reviewController?.telemetry) return;
  const changes = { ArrowLeft: -GRAPH_SEEK_STEP_SECONDS, ArrowDown: -GRAPH_SEEK_STEP_SECONDS, ArrowRight: GRAPH_SEEK_STEP_SECONDS, ArrowUp: GRAPH_SEEK_STEP_SECONDS, PageDown: -GRAPH_SEEK_PAGE_SECONDS, PageUp: GRAPH_SEEK_PAGE_SECONDS };
  let target = null;
  if (event.key in changes) target = reviewController.clock.globalTime + changes[event.key];
  else if (event.key === "Home") target = 0;
  else if (event.key === "End") target = reviewController.durationSeconds;
  if (target === null) return;
  event.preventDefault();
  seekGlobalTime(target);
}

function showMediaFailure(kind) {
  const player = reviewController?.players[kind];
  if (!player) return;
  player.mediaFailed = true;
  player.buffering = false;
  clearPlayerSeek(player);
  pausePlayer(player);
  player.video.hidden = true;
  const elements = previewElements(kind);
  player.coverageMessage.hidden = true;
  elements.messageTitle.textContent = "Media unavailable";
  elements.status.textContent = "Preview media could not be loaded.";
  elements.message.hidden = false;
  player.mediaRetry.hidden = false;
  setStateBadge(elements.badge, "Media unavailable", "failed");
  updateTransportAvailability();
}

document.addEventListener("click", (event) => {
  const routeLink = event.target.closest("[data-route]");
  if (routeLink) {
    if (routeLink.getAttribute("aria-disabled") === "true") { event.preventDefault(); return; }
    const url = new URL(routeLink.href, window.location.origin);
    if (url.origin === window.location.origin) { event.preventDefault(); navigate(url.pathname); }
  }
  if (!imuElements.picker.contains(event.target)) {
    imuElements.pickerMenu.hidden = true;
    imuElements.pickerTrigger.setAttribute("aria-expanded", "false");
  }
});
window.addEventListener("popstate", () => activateRoute(parseRoute(window.location.pathname) || { view: "recordings" }));
window.addEventListener("beforeunload", () => { stopProcessingActivity(); stopReviewActivity(); });
document.addEventListener("visibilitychange", () => {
  if (currentRoute?.view !== "processing") return;
  if (document.hidden) {
    if (processingState.pollTimer !== null) window.clearTimeout(processingState.pollTimer);
    processingState.pollTimer = null;
  } else {
    loadProcessing({ manual: true });
  }
});

catalogElements.folderSearch.addEventListener("input", () => { catalogState.folderQuery = catalogElements.folderSearch.value.trim().toLocaleLowerCase(); renderFolderTree(); });
catalogElements.search.addEventListener("input", () => { catalogState.query = catalogElements.search.value.trim().toLocaleLowerCase(); catalogState.page = 1; renderRecordingTable(); });
catalogElements.analysisFilter.addEventListener("change", () => { catalogState.analysis = catalogElements.analysisFilter.value; catalogState.page = 1; renderRecordingTable(); syncSummaryCards(); });
catalogElements.healthFilter.addEventListener("change", () => { catalogState.health = catalogElements.healthFilter.value; catalogState.page = 1; renderRecordingTable(); syncSummaryCards(); });
document.querySelectorAll(".table-sort").forEach((button) => button.addEventListener("click", () => sortRecordings(button.dataset.sort)));
document.querySelectorAll("[data-summary-analysis]").forEach((button) => button.addEventListener("click", () => {
  catalogState.analysis = catalogState.analysis === button.dataset.summaryAnalysis ? "all" : button.dataset.summaryAnalysis;
  catalogElements.analysisFilter.value = catalogState.analysis;
  catalogState.page = 1;
  renderRecordingTable();
  syncSummaryCards();
}));
document.querySelectorAll("[data-summary-health]").forEach((button) => button.addEventListener("click", () => {
  catalogState.health = catalogState.health === button.dataset.summaryHealth ? "all" : button.dataset.summaryHealth;
  catalogElements.healthFilter.value = catalogState.health;
  catalogState.page = 1;
  renderRecordingTable();
  syncSummaryCards();
}));
function syncSummaryCards() {
  document.querySelectorAll("[data-summary-analysis]").forEach((button) => button.classList.toggle("is-active", button.dataset.summaryAnalysis === catalogState.analysis));
  document.querySelectorAll("[data-summary-health]").forEach((button) => button.classList.toggle("is-active", button.dataset.summaryHealth === catalogState.health));
}
catalogElements.selectAll.addEventListener("change", () => {
  catalogElements.rows.querySelectorAll(".row-select:not(:disabled)").forEach((checkbox) => {
    checkbox.checked = catalogElements.selectAll.checked;
    const id = Number(checkbox.value);
    if (checkbox.checked) catalogState.selectedIds.add(id); else catalogState.selectedIds.delete(id);
  });
  updateSelectionState();
});
catalogElements.previous.addEventListener("click", () => { catalogState.page -= 1; renderRecordingTable(); });
catalogElements.next.addEventListener("click", () => { catalogState.page += 1; renderRecordingTable(); });
catalogElements.retry.addEventListener("click", () => loadCatalog({ initial: true }));
catalogElements.rescan.addEventListener("click", rescanCatalog);
catalogElements.prepare.addEventListener("click", prepareSelected);
byId("clear-filters").addEventListener("click", () => {
  catalogState.query = ""; catalogState.analysis = "all"; catalogState.health = "all"; catalogState.folderPath = ""; catalogState.page = 1;
  catalogElements.search.value = ""; catalogElements.analysisFilter.value = "all"; catalogElements.healthFilter.value = "all";
  renderFolderTree(); renderRecordingTable(); syncSummaryCards();
});
catalogElements.collapseFolders.addEventListener("click", () => setFolderPanel(false));
catalogElements.expandFolders.addEventListener("click", () => setFolderPanel(true));
function setFolderPanel(open) {
  byId("recordings-view").classList.toggle("is-folders-collapsed", !open);
  catalogElements.folderPanel.classList.toggle("is-collapsed", !open);
  catalogElements.folderPanel.toggleAttribute("inert", !open);
  catalogElements.expandFolders.hidden = open;
  try { localStorage.setItem("tectrace-folders", open ? "open" : "collapsed"); } catch { /* Visual preference remains in memory. */ }
}

document.querySelectorAll("[data-job-filter]").forEach((button) => {
  button.addEventListener("click", () => setProcessingTab(button.dataset.jobFilter));
  button.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("[data-job-filter]")];
    const index = tabs.indexOf(button);
    let target = null;
    if (event.key === "Home") target = tabs[0];
    else if (event.key === "End") target = tabs.at(-1);
    else if (["ArrowRight", "ArrowDown"].includes(event.key)) target = tabs[(index + 1) % tabs.length];
    else if (["ArrowLeft", "ArrowUp"].includes(event.key)) target = tabs[(index - 1 + tabs.length) % tabs.length];
    if (!target) return;
    event.preventDefault();
    setProcessingTab(target.dataset.jobFilter);
    target.focus();
  });
});
processingElements.refresh.addEventListener("click", () => loadProcessing({ manual: true }));
processingElements.liveToggle.addEventListener("click", () => {
  processingState.autoRefresh = !processingState.autoRefresh;
  processingElements.liveToggle.setAttribute("aria-pressed", String(processingState.autoRefresh));
  processingElements.liveLabel.textContent = processingState.autoRefresh ? "Auto-refresh on" : "Auto-refresh off";
  if (processingState.autoRefresh) loadProcessing({ manual: true }); else scheduleProcessingPoll();
  announce(processingState.autoRefresh ? "Automatic processing refresh enabled." : "Automatic refresh paused. Worker processing is unaffected.");
});
processingElements.search.addEventListener("input", () => {
  if (processingState.tab === "queue") renderQueue();
  else loadProcessingPage(processingState.tab, { append: false });
});
processingElements.historyMore.addEventListener("click", () => loadProcessingPage("history", { append: true }));
processingElements.dialogClose.addEventListener("click", closeFailureDialog);
processingElements.dialogDismiss.addEventListener("click", closeFailureDialog);
processingElements.dialog.addEventListener("click", (event) => { if (event.target === processingElements.dialog) closeFailureDialog(); });
processingElements.dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeFailureDialog(); });

timelineElements.play.addEventListener("click", togglePlayback);
timelineElements.slider.addEventListener("input", () => seekGlobalTime(Number(timelineElements.slider.value)));
imuElements.pickerTrigger.addEventListener("click", () => {
  if (imuElements.pickerTrigger.disabled) return;
  const open = imuElements.pickerMenu.hidden;
  imuElements.pickerMenu.hidden = !open;
  imuElements.pickerTrigger.setAttribute("aria-expanded", String(open));
  if (open) imuElements.pickerMenu.querySelector('[aria-checked="true"]')?.focus();
});
imuElements.pickerMenu.addEventListener("keydown", (event) => {
  const options = [...imuElements.pickerMenu.querySelectorAll("[data-sensor]:not(:disabled)")];
  const index = options.indexOf(document.activeElement);
  if (event.key === "Escape") { event.preventDefault(); imuElements.pickerMenu.hidden = true; imuElements.pickerTrigger.focus(); return; }
  if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(event.key) || index < 0) return;
  event.preventDefault();
  const direction = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
  options[(index + direction + options.length) % options.length].focus();
});
imuElements.plot.addEventListener("pointerdown", beginImuSeek);
imuElements.plot.addEventListener("pointermove", moveImuSeek);
imuElements.plot.addEventListener("pointerup", endImuSeek);
imuElements.plot.addEventListener("pointercancel", cancelImuSeek);
imuElements.plot.addEventListener("keydown", keyboardImuSeek);
[["front", previewElements("front")], ["topdown", previewElements("topdown")]].forEach(([kind, elements]) => {
  elements.video.addEventListener("loadedmetadata", () => { if (reviewController?.players[kind]) applyGlobalTime(reviewController.clock.globalTime, true); });
  elements.video.addEventListener("seeking", () => {
    const player = reviewController?.players[kind];
    if (!player) return;
    player.seekPending = true;
    if (player.seekRequestedAt === null) player.seekRequestedAt = performance.now();
  });
  elements.video.addEventListener("seeked", () => {
    const player = reviewController?.players[kind];
    if (player) clearPlayerSeek(player);
  });
  ["waiting", "stalled"].forEach((eventName) => elements.video.addEventListener(eventName, () => {
    const player = reviewController?.players[kind];
    if (player) player.buffering = true;
  }));
  ["canplay", "playing"].forEach((eventName) => elements.video.addEventListener(eventName, () => {
    const player = reviewController?.players[kind];
    if (!player) return;
    player.buffering = false;
    applyGlobalTime(reviewController.clock.globalTime);
  }));
  elements.video.addEventListener("error", () => showMediaFailure(kind));
});

try { setFolderPanel(localStorage.getItem("tectrace-folders") !== "collapsed"); } catch { setFolderPanel(true); }
const initialRoute = parseRoute(window.location.pathname);
if (initialRoute) activateRoute(initialRoute);
else navigate("/", { replace: true });
