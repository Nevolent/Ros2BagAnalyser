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
  filterControls: [...document.querySelectorAll("[data-catalog-filter]")],
  clearFilters: byId("clear-filter-menu"),
  selectAll: byId("select-all-recordings"),
  selectedCount: byId("selected-count"),
  selectionContext: byId("selection-context"),
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
  tabs: document.querySelector(".processing-tabs"),
  tabIndicator: document.querySelector(".processing-tab-indicator"),
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
  dialogRecovery: byId("processing-error-recovery"),
  dialogClose: byId("close-processing-error"),
  dialogDismiss: byId("dismiss-processing-error"),
  dialogCopyButton: byId("copy-processing-error"),
  dialogOpenButton: byId("open-processing-recording"),
  dialogRetryButton: byId("retry-processing-error"),
  queueSelectAll: byId("select-all-queued"),
  queueSelectionActions: byId("queue-selection-actions"),
  queueSelectionFooter: byId("queue-selection-footer"),
  queueSelectedCount: byId("queue-selected-count"),
  moveEarlier: byId("move-selected-queue-up"),
  moveLater: byId("move-selected-queue-down"),
  cancelSelected: byId("cancel-selected-queue"),
  failureSelectAll: byId("select-all-failures"),
  failureSelectionActions: byId("failure-selection-actions"),
  failureSelectionFooter: byId("failure-selection-footer"),
  failureSelectedCount: byId("failure-selected-count"),
  retrySelected: byId("retry-selected-failures"),
};

const preparationElements = {
  dialog: byId("prepare-dialog"),
  form: byId("prepare-form"),
  summary: byId("prepare-selection-summary"),
  recordings: byId("prepare-recordings"),
  impact: byId("prepare-impact"),
  cancel: byId("cancel-prepare"),
  confirm: byId("confirm-prepare"),
};

const cancelElements = {
  dialog: byId("cancel-job-dialog"),
  title: byId("cancel-job-title"),
  copy: byId("cancel-job-copy"),
  keep: byId("keep-processing"),
  confirm: byId("confirm-job-cancel"),
};

const toastElements = {
  root: byId("operation-toast"),
  title: byId("operation-toast-title"),
  copy: byId("operation-toast-copy"),
  processing: byId("view-processing-toast"),
  dismiss: byId("dismiss-toast"),
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
  cursorMarker: byId("imu-cursor-marker"),
  selection: byId("imu-selection"),
  selectionStart: byId("imu-selection-start"),
  selectionEnd: byId("imu-selection-end"),
  summary: byId("imu-summary"),
  currentValue: byId("imu-current-value"),
  currentTime: byId("imu-current-time"),
  currentState: byId("imu-current-state"),
  warnings: byId("imu-warnings"),
  picker: document.querySelector(".sensor-picker"),
  pickerTrigger: byId("sensor-picker-trigger"),
  pickerMenu: byId("sensor-picker-menu"),
  selectedLabel: byId("selected-sensor-label"),
  reset: byId("chart-reset"),
  zoomOut: byId("chart-zoom-out"),
  zoomIn: byId("chart-zoom-in"),
};

const OUTPUT_ORDER = ["front_preview", "topdown_preview", "imu_series"];
const OUTPUT_LABELS = {
  front_preview: "Front-camera preview",
  topdown_preview: "Top-down preview",
  imu_series: "IMU data bundle",
};
const OUTPUT_FORMAT_LABELS = {
  front_preview: "MP4 · H.264",
  topdown_preview: "MP4 · H.264",
  imu_series: "JSON",
};
const CURRENT_JOB_LABELS = { ...OUTPUT_LABELS, front_preview: "Front camera preview" };
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
const RECORDING_DETAILS_RESIZE_DURATION = 360;
const RECORDING_DETAILS_GRAPH_DURATION = 520;

let routeGeneration = 0;
let routeController = null;
let currentRoute = null;
let reviewController = null;
let timelineAnimation = null;
let imuSeekAnimation = null;
let pendingImuSeekTime = null;
let activeImuPointerId = null;
let activeImuGesture = null;
let dialogReturnFocus = null;
let pendingCancellation = null;
let diagnosticJob = null;
const reduceMotionQuery = window.matchMedia
  ? window.matchMedia("(prefers-reduced-motion: reduce)")
  : { matches: false };
let folderPanelTransitionVersion = 0;
let folderPanelAnimations = [];
const transientPanelAnimations = new WeakMap();
let recordingDetailsTransitionVersion = 0;
let recordingDetailsLayoutAnimations = [];
let toolIndicatorAnimation = null;
let clearFilterAnimation = null;
let clearFilterShouldShow = false;
let tableHeightAnimation = null;

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
  selectedQueueIds: new Set(),
  selectedFailureIds: new Set(),
  busyControlKeys: new Set(),
  canceledJobIds: new Set(),
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

function acknowledgeStateChange(element) {
  if (!element || reduceMotionQuery.matches || typeof element.animate !== "function") return;
  element.animate([
    { opacity: 0.64 },
    { opacity: 1 },
  ], { duration: 180, easing: "cubic-bezier(.16, 1, .3, 1)" });
}

function setTransientPanelOpen(panel, open) {
  const running = transientPanelAnimations.get(panel);
  running?.cancel();
  if (open) panel.hidden = false;
  if (reduceMotionQuery.matches || typeof panel.animate !== "function") {
    panel.hidden = !open;
    return;
  }
  const animation = panel.animate(open ? [
    { opacity: 0, transform: "translate3d(0, -4px, 0)" },
    { opacity: 1, transform: "translate3d(0, 0, 0)" },
  ] : [
    { opacity: 1, transform: "translate3d(0, 0, 0)" },
    { opacity: 0, transform: "translate3d(0, -2px, 0)" },
  ], {
    duration: open ? 150 : 100,
    easing: open ? "cubic-bezier(.16, 1, .3, 1)" : "cubic-bezier(.4, 0, 1, 1)",
    fill: "both",
  });
  transientPanelAnimations.set(panel, animation);
  animation.finished.then(() => {
    if (transientPanelAnimations.get(panel) !== animation) return;
    if (!open) panel.hidden = true;
    animation.cancel();
    transientPanelAnimations.delete(panel);
  }).catch(() => {});
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
  activateRoute(route, { focus: true });
}

function setActiveView(view, { previousView = null } = {}) {
  const indicator = document.querySelector(".tool-list-indicator");
  const canAnimateIndicator = previousView !== null && previousView !== view
    && !reduceMotionQuery.matches
    && indicator
    && typeof indicator.animate === "function"
    && typeof window.getComputedStyle === "function";
  const previousTransform = canAnimateIndicator ? window.getComputedStyle(indicator).transform : "";
  toolIndicatorAnimation?.cancel();
  if (canAnimateIndicator) indicator.style.transition = "none";
  viewPanels.forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== view; });
  navLinks.forEach((link) => {
    const active = link.dataset.nav === view;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (canAnimateIndicator) {
    const nextTransform = window.getComputedStyle(indicator).transform;
    indicator.style.transition = "";
    toolIndicatorAnimation = indicator.animate([
      { transform: previousTransform },
      { transform: nextTransform },
    ], { duration: 280, easing: "cubic-bezier(.16, 1, .3, 1)" });
    toolIndicatorAnimation.finished.then(() => { toolIndicatorAnimation = null; }).catch(() => {});
  }
  syncFolderReveal();
  const label = view === "recordings" ? "Recordings" : view === "processing" ? "Processing" : "Analyzer";
  document.title = `${label} — Tectrace`;
}

function activateRoute(route, { focus = false } = {}) {
  const previousView = currentRoute?.view || null;
  routeGeneration += 1;
  currentRoute = route;
  if (routeController) routeController.abort();
  routeController = new AbortController();
  stopProcessingActivity();
  stopReviewActivity();
  [preparationElements.dialog, cancelElements.dialog, processingElements.dialog].forEach((dialog) => {
    if (dialog?.open) dialog.close();
  });
  pendingCancellation = null;
  setActiveView(route.view, { previousView });
  if (focus) window.requestAnimationFrame(() => {
    viewPanels.find((panel) => panel.dataset.viewPanel === route.view)?.focus();
  });
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

function formatHistoryCompletion(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: "Unavailable", time: "", full: "Unavailable" };
  return {
    date: date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }),
    time: date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    full: date.toLocaleString(),
  };
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
    const currentIds = new Set(document.recordings.map((recording) => recording.id));
    catalogState.selectedIds.forEach((id) => {
      if (!currentIds.has(id)) catalogState.selectedIds.delete(id);
    });
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
  all.addEventListener("click", () => selectFolder("", { renderTree: false }));
  all.hidden = Boolean(query) && !"all recordings".includes(query);
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
      button.append(icon(hasChildren && !catalogState.collapsedFolders.has(folder.path) ? "folder-open" : "folder", "folder-icon"));
      const label = node("span", folder.name, "folder-label");
      label.title = folder.name;
      button.append(label, node("strong", folder.descendant_recording_count));
      button.addEventListener("click", () => {
        if (hasChildren) {
          if (catalogState.collapsedFolders.has(folder.path)) catalogState.collapsedFolders.delete(folder.path);
          else catalogState.collapsedFolders.add(folder.path);
          const collapsed = catalogState.collapsedFolders.has(folder.path);
          button.setAttribute("aria-expanded", String(!collapsed));
          const folderIcon = button.querySelector(".folder-icon use");
          if (folderIcon) folderIcon.setAttribute("href", collapsed ? "#icon-folder" : "#icon-folder-open");
          const branch = wrapper.querySelector(":scope > .folder-children");
          if (branch && !query) branch.hidden = collapsed;
        }
        selectFolder(folder.path, { renderTree: false });
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

function selectFolder(path, { renderTree = true } = {}) {
  catalogState.folderPath = path;
  catalogState.page = 1;
  if (renderTree) renderFolderTree();
  else catalogElements.folderTree.querySelectorAll("[data-folder]").forEach((button) => {
    const active = button.dataset.folder === path;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderRecordingTable();
  announce(path ? `${path} folder selected.` : "All recordings selected.");
}

function canPrepare(recording) {
  return recording.presentation_health === "readable"
    && OUTPUT_ORDER.some((kind) => {
      const output = recording.outputs.find((candidate) => candidate.kind === kind);
      return output && output.state !== "unavailable";
    });
}

function filteredRecordings() {
  const query = catalogState.query;
  const path = catalogState.folderPath;
  const rows = catalogState.data.recordings.filter((recording) => {
    const matchesQuery = !query || `${recordingDisplayName(recording.name)} ${recording.name} ${recording.folder_path}`.toLocaleLowerCase().includes(query);
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
    if (key === "name") compared = recordingDisplayName(left.name).localeCompare(recordingDisplayName(right.name));
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
  const tooltipId = `status-tooltip-${statusIndicator.nextId++}`;
  indicator.setAttribute("aria-describedby", tooltipId);
  const glyph = node("span", null, "status-glyph");
  glyph.append(icon(iconName));
  const tooltip = node("span", null, "status-tooltip");
  tooltip.setAttribute("role", "tooltip");
  tooltip.id = tooltipId;
  tooltip.append(node("strong", label));
  details.filter(Boolean).forEach((detail) => tooltip.append(node("span", detail)));
  indicator.append(glyph, node("span", label, "status-label"), tooltip);
  const positionTooltip = () => {
    if (typeof indicator.getBoundingClientRect !== "function" || typeof tooltip.getBoundingClientRect !== "function") return;
    const anchor = indicator.getBoundingClientRect();
    const bounds = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement?.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement?.clientHeight || 0;
    if (!viewportWidth || !viewportHeight) return;
    const gap = 8;
    const edge = 8;
    const width = bounds.width || 238;
    const height = bounds.height || 0;
    const roomOnRight = viewportWidth - anchor.right;
    const left = roomOnRight >= width + gap
      ? anchor.right + gap
      : Math.max(edge, anchor.left - width - gap);
    const top = Math.max(edge, Math.min(viewportHeight - height - edge, anchor.top + (anchor.height - height) / 2));
    tooltip.style.left = `${Math.min(left, viewportWidth - width - edge)}px`;
    tooltip.style.top = `${top}px`;
  };
  indicator.addEventListener("pointerenter", positionTooltip);
  indicator.addEventListener("focus", positionTooltip);
  return indicator;
}
statusIndicator.nextId = 1;

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
  link.setAttribute("aria-label", `${recordingDisplayName(recording.name)}. Exact source name ${recording.name}. Recorded ${formatRecorded(recording.start_time_ns)}.`);
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
    recording.presentation_health === "readable" ? "table-health--readable" : "table-health--unreadable",
    [recording.diagnostic?.message || (recording.presentation_health === "readable" ? "Source prerequisites are readable." : "Open the recording for the precise diagnostic.")],
    recording.presentation_health === "readable" ? "status-check" : "status-x",
  ));
  const analysisCell = node("td", null, "status-cell");
  const hasReadyOutput = recording.outputs.some((output) => output.state === "ready");
  const isPartial = recording.analysis_state === "not_planned" && hasReadyOutput;
  const analysisLabel = isPartial ? "Partially prepared"
    : recording.analysis_state === "not_planned" ? "Not planned"
      : humanize(recording.analysis_state);
  const analysisIcon = isPartial ? "analysis-subset"
    : { ready: "status-check", processing: "analysis-processing", queued: "clock", failed: "status-alert", not_planned: "clock" }[recording.analysis_state];
  const analysisClass = isPartial ? "partial" : recording.analysis_state.replaceAll("_", "-");
  analysisCell.append(statusIndicator(analysisLabel, `table-status--${analysisClass}`, analysisDetails(recording), analysisIcon));
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
  [...catalogElements.rows.children].at(-1)?.classList.add("is-last-visible");
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
    button.addEventListener("click", () => { catalogState.page = page; renderRecordingTableWithHeightTransition(); });
    catalogElements.pageButtons.append(button);
  }
  catalogElements.previous.disabled = catalogState.page === 1;
  catalogElements.next.disabled = catalogState.page === totalPages;
  catalogElements.pageStatus.textContent = `Page ${catalogState.page} of ${totalPages}`;
}

function setClearFilterVisible(visible) {
  if (visible === clearFilterShouldShow) return;
  clearFilterShouldShow = visible;
  clearFilterAnimation?.cancel();
  if (visible) catalogElements.clearFilters.hidden = false;
  if (reduceMotionQuery.matches || typeof catalogElements.clearFilters.animate !== "function") {
    catalogElements.clearFilters.hidden = !visible;
    return;
  }
  const width = catalogElements.clearFilters.scrollWidth;
  const animation = catalogElements.clearFilters.animate(visible ? [
    { width: "0px", opacity: 0, paddingInline: "0px" },
    { width: `${width}px`, opacity: 1, paddingInline: "7px" },
  ] : [
    { width: `${width}px`, opacity: 1, paddingInline: "7px" },
    { width: "0px", opacity: 0, paddingInline: "0px" },
  ], {
    duration: visible ? 180 : 140,
    easing: "cubic-bezier(.22, 1, .36, 1)",
  });
  clearFilterAnimation = animation;
  animation.finished.then(() => {
    if (!clearFilterShouldShow) catalogElements.clearFilters.hidden = true;
    if (clearFilterAnimation === animation) clearFilterAnimation = null;
  }).catch(() => {});
}

function renderRecordingTableWithHeightTransition() {
  const panel = document.querySelector(".home-table-panel");
  const startHeight = panel?.getBoundingClientRect().height || 0;
  tableHeightAnimation?.cancel();
  renderRecordingTable();
  if (!panel || reduceMotionQuery.matches || typeof panel.animate !== "function") return;
  const endHeight = panel.getBoundingClientRect().height;
  if (Math.abs(startHeight - endHeight) < 1) return;
  const animation = panel.animate([
    { height: `${startHeight}px` },
    { height: `${endHeight}px` },
  ], { duration: 340, easing: "cubic-bezier(.22, 1, .36, 1)" });
  tableHeightAnimation = animation;
  const clearAnimation = () => { if (tableHeightAnimation === animation) tableHeightAnimation = null; };
  animation.finished.then(clearAnimation).catch(clearAnimation);
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
  catalogElements.selectionContext.hidden = catalogState.selectedIds.size === 0;
  catalogElements.prepare.disabled = catalogState.selectedIds.size === 0 || catalogState.loading;
  const filterBar = catalogElements.prepare.closest(".table-filter-bar");
  filterBar?.classList.toggle("has-selection", catalogState.selectedIds.size > 0);
  catalogElements.prepare.setAttribute("aria-hidden", String(catalogState.selectedIds.size === 0));
  catalogElements.prepare.tabIndex = catalogState.selectedIds.size === 0 ? -1 : 0;
  const filtersActive = Boolean(catalogState.query || catalogState.folderPath || catalogState.analysis !== "all" || catalogState.health !== "all");
  filterBar?.classList.toggle("has-active-filters", filtersActive);
  setClearFilterVisible(filtersActive);
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
      catalogElements.lastScanned.textContent = "Rescan failed · previous catalog retained";
      announce("Archive scan failed. The previous catalog is still visible.");
    }
  } finally {
    catalogElements.rescan.disabled = false;
    catalogElements.rescan.classList.remove("is-scanning");
    catalogElements.rescan.setAttribute("aria-label", "Rescan archive");
  }
}

function validatePrepareResponse(document, submittedIds, submittedKinds) {
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
    const returnedKinds = new Set();
    recording.outputs.forEach((output) => {
      if (!submittedKinds.includes(output.kind) || returnedKinds.has(output.kind) || typeof output.outcome !== "string" || typeof output.state !== "string") {
        throw new ApiError("The preparation response was invalid.", "validation");
      }
      returnedKinds.add(output.kind);
    });
    if (returnedKinds.size !== submittedKinds.length) throw new ApiError("The preparation response was incomplete.", "validation");
  });
  if (returned.size !== submittedIds.length) throw new ApiError("The preparation response was incomplete.", "validation");
  return document;
}

function selectedRecordingsInStableOrder() {
  if (!catalogState.data) return [];
  const visibleOrder = filteredRecordings().filter((item) => catalogState.selectedIds.has(item.id));
  const delivered = new Set(visibleOrder.map((item) => item.id));
  return [...visibleOrder, ...catalogState.data.recordings.filter((item) => catalogState.selectedIds.has(item.id) && !delivered.has(item.id))];
}

function selectedOutputKinds() {
  return [...preparationElements.form.querySelectorAll('[name="output_kind"]')].filter((input) => input.checked).map((input) => input.value);
}

function updatePreparationDialog() {
  const recordings = selectedRecordingsInStableOrder();
  const kinds = selectedOutputKinds();
  preparationElements.summary.textContent = `${recordings.length} recording${recordings.length === 1 ? "" : "s"} selected`;
  preparationElements.recordings.replaceChildren(...recordings.map((recording) => {
    const item = node("span", recordingDisplayName(recording.name));
    item.title = recording.name;
    return item;
  }));
  const potential = recordings.length * kinds.length;
  preparationElements.impact.textContent = kinds.length === 0
    ? "Select at least one output."
    : `Up to ${potential} independent job${potential === 1 ? "" : "s"} will be resolved in front, top-down, then IMU order.`;
  preparationElements.confirm.disabled = recordings.length === 0 || kinds.length === 0;
}

function openPreparationDialog() {
  if (catalogElements.prepare.disabled || !catalogState.data) return;
  dialogReturnFocus = catalogElements.prepare;
  updatePreparationDialog();
  preparationElements.dialog.showModal();
}

function showToast(title, copy, { processing = false } = {}) {
  toastElements.title.textContent = title;
  toastElements.copy.textContent = copy;
  toastElements.processing.hidden = !processing;
  toastElements.root.hidden = false;
  acknowledgeStateChange(toastElements.root);
}

function closePreparationDialog() {
  preparationElements.dialog.close();
  dialogReturnFocus?.focus();
  dialogReturnFocus = null;
}

async function prepareSelected(event) {
  event?.preventDefault();
  if (preparationElements.confirm.disabled || !catalogState.data) return;
  const submittedRecordings = selectedRecordingsInStableOrder();
  const submitted = submittedRecordings.map((item) => item.id);
  const outputKinds = selectedOutputKinds();
  const generation = routeGeneration;
  catalogElements.prepare.disabled = true;
  preparationElements.confirm.disabled = true;
  preparationElements.form.setAttribute("aria-busy", "true");
  preparationElements.confirm.textContent = "Adding…";
  try {
    const document = validatePrepareResponse(await requestJson("/api/v1/recordings/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recording_ids: submitted, output_kinds: outputKinds }),
      signal: routeController?.signal,
    }), submitted, outputKinds);
    if (generation !== routeGeneration || currentRoute?.view !== "recordings") return;
    const counts = { queued: 0, reused: 0, unavailable: 0, notFound: 0, failed: 0 };
    let activeWork = false;
    const rejected = new Set();
    document.recordings.forEach((recording) => {
      recording.outputs.forEach((output) => {
        if (["queued", "retry_queued"].includes(output.outcome)) { counts.queued += 1; activeWork = true; }
        else if (output.outcome === "active_reused") { counts.reused += 1; activeWork = true; }
        else if (output.outcome === "ready_reused") counts.reused += 1;
        else if (output.outcome === "unavailable") { counts.unavailable += 1; rejected.add(recording.recording_id); }
        else { counts.failed += 1; rejected.add(recording.recording_id); }
      });
      if (recording.outcome === "not_found") { counts.notFound += 1; rejected.add(recording.recording_id); }
      if (recording.outcome === "request_failed") { counts.failed += 1; rejected.add(recording.recording_id); }
    });
    catalogState.selectedIds = rejected;
    const summary = `${counts.queued} queued, ${counts.reused} reused, ${counts.unavailable} unavailable, ${counts.notFound} not found, ${counts.failed} failed.`;
    closePreparationDialog();
    await loadCatalog({ retained: true });
    announce(summary);
    showToast(activeWork ? "Preparation resolved" : "Preparation checked", summary, { processing: activeWork });
    if (activeWork) navigate("/processing");
  } catch (error) {
    if (error?.name !== "AbortError") {
      preparationElements.impact.textContent = error.message;
      announce("Preparation request failed. The selection has been retained.");
    }
  } finally {
    preparationElements.form.removeAttribute("aria-busy");
    preparationElements.confirm.textContent = "Add to processing";
    updateSelectionState();
    updatePreparationDialog();
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
  syncProcessingTabIndicator();
}

function syncProcessingTabIndicator({ animate = true } = {}) {
  const active = document.querySelector('[data-job-filter].is-active');
  const tabs = processingElements.tabs;
  const indicator = processingElements.tabIndicator;
  if (!active || !tabs || !indicator || typeof active.getBoundingClientRect !== "function") return;
  const tabsRect = tabs.getBoundingClientRect();
  const activeRect = active.getBoundingClientRect();
  indicator.classList.toggle("is-positioning", !animate);
  indicator.style.width = `${activeRect.width}px`;
  indicator.style.transform = `translate3d(${activeRect.left - tabsRect.left + (tabs.scrollLeft || 0)}px, 0, 0)`;
  if (!animate) window.requestAnimationFrame(() => indicator.classList.remove("is-positioning"));
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
    overview.queue = overview.queue.filter((job) => !processingState.canceledJobIds.has(job.id));
    overview.queued_count = overview.queue.length;
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

async function refreshProcessingAfterMutation() {
  if (processingState.pollTimer !== null) window.clearTimeout(processingState.pollTimer);
  processingState.pollTimer = null;
  if (processingState.pollController) {
    processingState.requestSerial += 1;
    processingState.pollController.abort();
    processingState.pollController = null;
  }
  await loadProcessing({ manual: true });
}

function controlKey(jobId, action) {
  return `${jobId}:${action}`;
}

function controlIsBusy(jobId, action) {
  return processingState.busyControlKeys.has(controlKey(jobId, action));
}

function beginControls(jobIds, action, button) {
  if (jobIds.some((jobId) => controlIsBusy(jobId, action))) return false;
  jobIds.forEach((jobId) => processingState.busyControlKeys.add(controlKey(jobId, action)));
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  return true;
}

function finishControls(jobIds, action, button) {
  jobIds.forEach((jobId) => processingState.busyControlKeys.delete(controlKey(jobId, action)));
  button.disabled = false;
  button.removeAttribute("aria-busy");
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
  syncProcessingTabIndicator({ animate: false });
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
    processingElements.currentHost.hidden = false;
    const queuedCount = processingState.overview?.queued_count || 0;
    const article = node("article", null, "panel current-job current-job--empty");
    article.setAttribute("aria-label", "Current processing status");
    const empty = node("div", null, "current-job-empty-state");
    empty.append(
      node("h2", "Nothing is processing currently"),
      node(
        "p",
        queuedCount > 0
          ? `${queuedCount} ${queuedCount === 1 ? "job is" : "jobs are"} waiting in the queue.`
          : "The queue is empty.",
      ),
    );
    article.append(empty);
    processingElements.currentHost.append(article);
    stopElapsedTicker();
    return;
  }
  processingElements.currentHost.hidden = false;
  const article = node("article", null, "panel current-job");
  article.setAttribute("aria-label", "Current processing job");
  article.dataset.jobState = job.control_state === "none" ? job.state : job.control_state;
  const activity = job.control_state === "pause_requested" ? "Pause requested"
    : job.control_state === "paused" ? "Paused"
      : job.control_state === "cancel_requested" ? "Cancellation requested"
        : processingState.overview.worker_online ? humanize(job.execution_phase || "processing") : "Worker offline";
  const body = node("div", null, "current-job-body");
  const main = node("div", null, "current-job-main");
  const copy = node("div");
  const titleLine = node("div", null, "current-job-title-line");
  titleLine.append(node("h2", CURRENT_JOB_LABELS[job.kind] || humanize(job.kind)), node("span", activity, "sr-only"));
  const exact = processingLink(job, job.recording_name);
  exact.className = "recording-reference";
  exact.title = job.recording_name;
  exact.setAttribute("aria-label", `Open ${recordingDisplayName(job.recording_name)} in Analyzer`);
  copy.append(titleLine, exact);
  main.append(copy);
  const meta = node("dl", null, "current-job-meta");
  const metaItem = (label, value, className = "") => {
    const item = node("div");
    item.append(node("dt", label), node("dd", value, className));
    return item;
  };
  const activeMeta = metaItem("Active:", formatMilliseconds(job.active_elapsed_ms), "current-active-elapsed");
  activeMeta.className = "sr-only";
  meta.append(
    metaItem("Elapsed:", formatMilliseconds(job.elapsed_ms), "current-elapsed"),
    metaItem("Likely duration", estimateText(job.estimate), "current-estimate"),
    activeMeta,
  );
  const progress = node("div", null, "current-job-progress");
  const track = node("div", null, "indeterminate-track job-progress-track");
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", `${CURRENT_JOB_LABELS[job.kind] || humanize(job.kind)} ${activity.toLocaleLowerCase()}`);
  track.append(node("i"));
  progress.title = estimateTotalText(job.estimate);
  progress.append(track, meta);
  const actions = node("div", null, "current-job-actions");
  (job.allowed_controls || []).filter((control) => ["pause", "resume", "cancel"].includes(control)).forEach((control) => {
    const button = node("button", null, `current-job-icon-action${control === "cancel" ? " danger-action" : ""}`);
    button.type = "button";
    button.disabled = controlIsBusy(job.id, control);
    button.append(icon(control === "pause" ? "pause" : control === "resume" ? "play" : "x"), node("span", humanize(control)));
    button.setAttribute("aria-label", `${humanize(control)} ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
    button.addEventListener("click", () => {
      if (control === "cancel") requestCancellation([job], button);
      else controlJob(job.id, control, button);
    });
    actions.append(button);
  });
  const side = node("div", null, "current-job-side");
  side.append(actions);
  body.append(main, progress, side);
  article.append(body);
  processingElements.currentHost.append(article);
  startElapsedTicker(job);
}

function estimateText(estimate) {
  if (!estimate || estimate.status === "unavailable") return estimate?.sample_count === 0 ? "Not enough history" : "Estimating…";
  if (estimate.status === "exceeded") return "Estimate exceeded";
  return `≈ ${formatMilliseconds(estimate.remaining_ms)}`;
}

function estimateTotalText(estimate) {
  return estimate?.status === "available" ? `≈ ${formatMilliseconds(estimate.estimated_total_ms)} total · ${estimate.sample_count} samples` : "Approximate timing unavailable";
}

function stopElapsedTicker() {
  if (processingState.elapsedFrame !== null) window.cancelAnimationFrame(processingState.elapsedFrame);
  processingState.elapsedFrame = null;
  processingState.elapsedAnchor = null;
}

function startElapsedTicker(job) {
  stopElapsedTicker();
  processingState.elapsedAnchor = {
    id: job.id,
    elapsedMs: job.elapsed_ms || 0,
    activeMs: job.active_elapsed_ms || 0,
    advances: processingState.overview?.worker_online && job.control_state !== "paused",
    at: performance.now(),
    shownSecond: -1,
  };
  const tick = (now) => {
    const anchor = processingState.elapsedAnchor;
    if (!anchor || currentRoute?.view !== "processing" || processingState.overview?.current?.id !== anchor.id) return;
    const delta = Math.max(0, now - anchor.at);
    const elapsed = anchor.elapsedMs + delta;
    const activeElapsed = anchor.activeMs + (anchor.advances ? delta : 0);
    const second = Math.floor(elapsed / 1000);
    if (second !== anchor.shownSecond) {
      anchor.shownSecond = second;
      const target = document.querySelector(".current-elapsed");
      if (target) target.textContent = formatMilliseconds(elapsed);
      const activeTarget = document.querySelector(".current-active-elapsed");
      if (activeTarget) activeTarget.textContent = formatMilliseconds(activeElapsed);
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
    row.dataset.jobId = String(job.id);
    row.classList.toggle("is-selected", processingState.selectedQueueIds.has(job.id));
    const selectionCell = node("td", null, "selection-column");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "queue-row-select";
    checkbox.checked = processingState.selectedQueueIds.has(job.id);
    checkbox.setAttribute("aria-label", `Select ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) processingState.selectedQueueIds.add(job.id);
      else processingState.selectedQueueIds.delete(job.id);
      row.classList.toggle("is-selected", checkbox.checked);
      updateQueueSelectionState();
    });
    selectionCell.append(checkbox);
    const recording = node("td", null, "queue-recording");
    const link = processingLink(job, recordingDisplayName(job.recording_name));
    link.title = job.recording_name;
    recording.append(link, node("span", job.recording_name, "cell-sublabel"));
    const ready = node("td", null, "queue-estimate");
    if (job.queue_estimate?.status === "available") {
      ready.append(node("strong", `≈ ${formatMilliseconds(job.queue_estimate.ready_in_ms)}`), node("span", `${job.queue_estimate.sample_count} historical samples`));
    } else {
      ready.append(node("strong", "Unavailable"), node("span", "Approximation prerequisites missing"));
    }
    const controlsCell = document.createElement("td");
    const queued = node("td", null, "queue-age");
    queued.append(
      node("strong", job.queue_position === null || job.queue_position === undefined ? "Position unavailable" : `#${job.queue_position}`),
      node("span", formatAge(job.queued_age_ms)),
    );
    const controls = node("div", null, "queue-controls");
    [["move_earlier", "chevron", "Move earlier", "queue-move queue-move--up"], ["move_later", "chevron", "Move later", "queue-move queue-move--down"], ["cancel", "x", "Cancel", "queue-cancel"]].forEach(([control, iconName, label, className]) => {
      if (!(job.allowed_controls || []).includes(control)) return;
      const button = node("button", null, className);
      button.type = "button";
      button.disabled = controlIsBusy(job.id, control);
      button.title = label;
      button.setAttribute("aria-label", `${label} ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
      button.append(icon(iconName));
      button.addEventListener("click", () => {
        if (control === "cancel") requestCancellation([job], button);
        else reorderJobs([job.id], control === "move_earlier" ? "earlier" : "later", button);
      });
      controls.append(button);
    });
    controlsCell.append(controls);
    row.append(selectionCell, recording, node("td", OUTPUT_LABELS[job.kind] || humanize(job.kind), "queue-artifact"), queued, ready, controlsCell);
    return row;
  }));
  const currentIds = new Set(queue.map((job) => job.id));
  processingState.selectedQueueIds.forEach((id) => { if (!currentIds.has(id)) processingState.selectedQueueIds.delete(id); });
  processingElements.queueEmpty.hidden = visible.length !== 0;
  processingElements.queueDescription.textContent = queue.length === 1 ? "1 job waiting" : `${queue.length} jobs waiting`;
  updateQueueSelectionState();
}

function updateQueueSelectionState() {
  const queue = processingState.overview?.queue || [];
  const selected = queue.filter((job) => processingState.selectedQueueIds.has(job.id));
  processingElements.queueSelectedCount.textContent = String(selected.length);
  processingElements.queueSelectionActions.hidden = processingState.tab !== "queue" || selected.length === 0;
  processingElements.queueSelectionFooter.hidden = selected.length === 0;
  processingElements.queueSelectAll.checked = queue.length > 0 && selected.length === queue.length;
  processingElements.queueSelectAll.indeterminate = selected.length > 0 && selected.length < queue.length;
  const selectedIds = new Set(selected.map((job) => job.id));
  const canMoveEarlier = selected.some((job) => {
    const index = queue.findIndex((candidate) => candidate.id === job.id);
    return index > 0 && !selectedIds.has(queue[index - 1].id);
  });
  const canMoveLater = selected.some((job) => {
    const index = queue.findIndex((candidate) => candidate.id === job.id);
    return index >= 0 && index < queue.length - 1 && !selectedIds.has(queue[index + 1].id);
  });
  processingElements.moveEarlier.disabled = !canMoveEarlier || selected.some((job) => controlIsBusy(job.id, "move_earlier"));
  processingElements.moveLater.disabled = !canMoveLater || selected.some((job) => controlIsBusy(job.id, "move_later"));
  processingElements.cancelSelected.disabled = selected.length === 0 || selected.some((job) => controlIsBusy(job.id, "cancel"));
  processingElements.cancelSelected.querySelector("span").textContent = selected.length > 0 ? `Cancel ${selected.length} selected` : "Cancel selected";
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
    const availableIds = new Set(page.items.map((item) => item.id));
    processingState.selectedFailureIds.forEach((id) => { if (!availableIds.has(id)) processingState.selectedFailureIds.delete(id); });
    processingElements.failureRows.replaceChildren(...page.items.map(createFailureRow));
    processingElements.failuresEmpty.hidden = page.items.length !== 0;
    updateFailureSelectionState();
  } else {
    processingElements.historyRows.replaceChildren(...page.items.map(createHistoryRow));
    processingElements.historyEmpty.hidden = page.items.length !== 0;
    processingElements.historyDescription.textContent = `Showing ${page.items.length} completed jobs`;
    processingElements.historyMore.hidden = !page.next_cursor;
  }
}

function createFailureRow(job) {
  const row = document.createElement("tr");
  row.dataset.jobId = String(job.id);
  row.classList.toggle("is-selected", processingState.selectedFailureIds.has(job.id));
  const selectionCell = node("td", null, "selection-column");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "failure-row-select";
  checkbox.checked = processingState.selectedFailureIds.has(job.id);
  checkbox.setAttribute("aria-label", `Select failed ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) processingState.selectedFailureIds.add(job.id);
    else processingState.selectedFailureIds.delete(job.id);
    row.classList.toggle("is-selected", checkbox.checked);
    updateFailureSelectionState();
  });
  selectionCell.append(checkbox);
  const recording = node("td", null, "processing-recording");
  const link = processingLink(job, recordingDisplayName(job.recording_name));
  link.title = job.recording_name;
  recording.append(link, node("span", OUTPUT_LABELS[job.kind] || humanize(job.kind), "cell-sublabel"));
  const problem = node("td", null, "failure-reason");
  const details = node("button", job.diagnostic?.message || "Processing failed.");
  details.type = "button";
  details.addEventListener("click", () => showFailureDialog(job, details));
  problem.append(details);
  const actions = node("td");
  const host = node("div", null, "processing-row-actions");
  const retry = node("button", null, "failure-retry-button");
  retry.type = "button";
  retry.disabled = controlIsBusy(job.id, "retry");
  retry.title = "Retry";
  retry.setAttribute("aria-label", `Retry ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
  retry.append(icon("refresh"));
  retry.addEventListener("click", () => retryJob(job, retry));
  host.append(retry);
  actions.append(host);
  row.append(selectionCell, recording, problem, actions);
  return row;
}

function createHistoryRow(job) {
  const row = document.createElement("tr");
  const recording = node("td", null, "processing-recording");
  recording.append(processingLink(job, recordingDisplayName(job.recording_name)), node("span", OUTPUT_LABELS[job.kind] || humanize(job.kind), "cell-sublabel"));
  const completed = formatHistoryCompletion(job.finished_at);
  const completedCell = node("td", null, "history-completed");
  const completedTime = document.createElement("time");
  if (completed.full !== "Unavailable") completedTime.dateTime = job.finished_at;
  completedTime.title = completed.full;
  completedTime.append(node("strong", completed.date));
  if (completed.time) completedTime.append(node("span", completed.time));
  completedCell.append(completedTime);
  row.append(
    recording,
    completedCell,
    node("td", formatMilliseconds(job.runtime_ms), "history-runtime"),
    node("td", formatBytes(job.output_size_bytes), "history-size"),
  );
  row.tabIndex = 0;
  row.setAttribute("role", "link");
  row.setAttribute("aria-label", `Open ${OUTPUT_LABELS[job.kind] || humanize(job.kind)} for ${recordingDisplayName(job.recording_name)}`);
  row.addEventListener("click", () => navigate(`/recordings/${job.recording_id}`));
  row.addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    event.preventDefault();
    navigate(`/recordings/${job.recording_id}`);
  });
  return row;
}

function showFailureDialog(job, trigger) {
  dialogReturnFocus = trigger;
  diagnosticJob = job;
  processingElements.dialogTitle.textContent = `${OUTPUT_LABELS[job.kind] || humanize(job.kind)} · ${job.recording_name}`;
  processingElements.dialogCopy.textContent = job.diagnostic?.message || "Processing failed.";
  processingElements.dialogMeta.replaceChildren();
  [["Code", job.diagnostic?.code || "processing_failed"], ["Attempted", formatDateTime(job.finished_at)], ["Runtime", formatMilliseconds(job.runtime_ms)], ["Recording ID", job.recording_id], ["Recording", job.recording_name], ["Output", OUTPUT_LABELS[job.kind] || humanize(job.kind)]].forEach(([label, value]) => {
    const item = node("div");
    item.append(node("dt", label), node("dd", value));
    processingElements.dialogMeta.append(item);
  });
  const recoveryByCode = {
    source_unavailable: "Confirm that the configured read-only source is available, then rescan before retrying.",
    worker_interrupted: "Retry creates a new attempt from the current recording identity.",
    processing_failed: "Review the retained diagnostic, then retry if the source is still available.",
  };
  processingElements.dialogRecovery.replaceChildren(
    node("strong", "Suggested recovery"),
    node("p", recoveryByCode[job.diagnostic?.code]
      || "Review the retained diagnostic and recording state before retrying."),
  );
  processingElements.dialogRetryButton.hidden = !(job.allowed_controls || ["retry"]).includes("retry");
  processingElements.dialog.showModal();
}

function closeFailureDialog() {
  processingElements.dialog.close();
  dialogReturnFocus?.focus();
  dialogReturnFocus = null;
  diagnosticJob = null;
}

function processingDiagnosticText(job) {
  return [
    `Code: ${job.diagnostic?.code || "processing_failed"}`,
    `Message: ${job.diagnostic?.message || "Processing failed."}`,
    `Attempted: ${formatDateTime(job.finished_at)}`,
    `Runtime: ${formatMilliseconds(job.runtime_ms)}`,
    `Recording ID: ${job.recording_id}`,
    `Recording: ${job.recording_name}`,
    `Output: ${OUTPUT_LABELS[job.kind] || humanize(job.kind)}`,
  ].join("\n");
}

async function retryJob(job, button) {
  if (!beginControls([job.id], "retry", button)) return;
  try {
    const generation = routeGeneration;
    const result = await requestJson(`/api/v1/processing/jobs/${job.id}/retry`, {
      method: "POST",
      signal: routeController?.signal,
    });
    if (generation !== routeGeneration || currentRoute?.view !== "processing") return;
    announce(result.state === "ready" ? "Compatible output is already ready." : "A current processing attempt is queued or active.");
    await refreshProcessingAfterMutation();
    if (processingState.tab === "failed") await loadProcessingPage("failed", { append: false });
  } catch (error) {
    showNotice(processingElements.notice, error.message, "error");
    await refreshProcessingAfterMutation();
  } finally {
    finishControls([job.id], "retry", button);
  }
}

function updateFailureSelectionState() {
  const items = processingState.pages.failed?.items || [];
  const selected = items.filter((job) => processingState.selectedFailureIds.has(job.id));
  processingElements.failureSelectedCount.textContent = String(selected.length);
  processingElements.failureSelectionActions.hidden = processingState.tab !== "failed" || selected.length === 0;
  processingElements.failureSelectionFooter.hidden = selected.length === 0;
  processingElements.failureSelectAll.checked = items.length > 0 && selected.length === items.length;
  processingElements.failureSelectAll.indeterminate = selected.length > 0 && selected.length < items.length;
  processingElements.retrySelected.disabled = selected.length === 0 || selected.some((job) => controlIsBusy(job.id, "retry"));
  processingElements.retrySelected.querySelector("span").textContent = selected.length > 0 ? `Retry ${selected.length} selected` : "Retry selected";
}

async function runJobMutation(url, body = null) {
  return requestJson(url, {
    method: "POST",
    headers: body === null ? undefined : { "Content-Type": "application/json" },
    body: body === null ? undefined : JSON.stringify(body),
    signal: routeController?.signal,
  });
}

async function controlJob(jobId, action, button) {
  if (!beginControls([jobId], action, button)) return;
  try {
    const result = await runJobMutation(`/api/v1/processing/jobs/${jobId}/${action}`);
    announce(`${humanize(action)} request: ${humanize(result.outcome)}.`);
    await refreshProcessingAfterMutation();
  } catch (error) {
    showNotice(processingElements.notice, error.message, "error");
    await refreshProcessingAfterMutation();
  } finally {
    finishControls([jobId], action, button);
    updateQueueSelectionState();
    updateFailureSelectionState();
  }
}

function queueRowPositions() {
  return new Map([...processingElements.queueRows.querySelectorAll("tr")].filter((row) => row.dataset.jobId).map((row) => [
    row.dataset.jobId,
    row.getBoundingClientRect().top,
  ]));
}

function animateAuthoritativeQueueOrder(previousPositions, movedJobIds) {
  if (reduceMotionQuery.matches) return;
  const moved = new Set(movedJobIds.map(String));
  [...processingElements.queueRows.querySelectorAll("tr")].filter((row) => row.dataset.jobId).forEach((row) => {
    if (typeof row.animate !== "function" || !previousPositions.has(row.dataset.jobId)) return;
    const offset = previousPositions.get(row.dataset.jobId) - row.getBoundingClientRect().top;
    if (!offset) return;
    row.animate(moved.has(row.dataset.jobId) ? [
      { transform: `translate3d(0, ${offset}px, 0) scale(.985)`, filter: "brightness(1)" },
      { offset: 0.55, transform: "translate3d(0, 0, 0) scale(.985)", filter: "brightness(1.18)" },
      { transform: "translate3d(0, 0, 0) scale(1)", filter: "brightness(1)" },
    ] : [
      { transform: `translate3d(0, ${offset}px, 0)` },
      { transform: "translate3d(0, 0, 0)" },
    ], {
      duration: moved.has(row.dataset.jobId) ? 420 : 320,
      easing: moved.has(row.dataset.jobId) ? "cubic-bezier(.16, 1, .3, 1)" : "cubic-bezier(.22, 1, .36, 1)",
    });
  });
}

async function reorderJobs(jobIds, direction, button) {
  if (jobIds.length === 0) return;
  const action = direction === "earlier" ? "move_earlier" : "move_later";
  if (!beginControls(jobIds, action, button)) return;
  const previousPositions = queueRowPositions();
  try {
    const result = await runJobMutation("/api/v1/processing/jobs/reorder", { job_ids: jobIds, direction });
    const conflicts = result.items.filter((item) => item.outcome !== "reordered").length;
    announce(conflicts ? `${conflicts} queue rows changed before reorder.` : `${jobIds.length} queue row${jobIds.length === 1 ? "" : "s"} moved ${direction}.`);
    await refreshProcessingAfterMutation();
    animateAuthoritativeQueueOrder(previousPositions, jobIds);
    if (!conflicts) showToast("Queue updated", `${jobIds.length} job${jobIds.length === 1 ? "" : "s"} moved ${direction}.`);
  } catch (error) {
    showNotice(processingElements.notice, error.message, "error");
    await refreshProcessingAfterMutation();
  } finally {
    finishControls(jobIds, action, button);
    updateQueueSelectionState();
  }
}

function requestCancellation(jobs, trigger) {
  if (jobs.length === 0 || jobs.some((job) => controlIsBusy(job.id, "cancel"))) return;
  dialogReturnFocus = trigger;
  pendingCancellation = jobs.map((job) => job.id);
  cancelElements.title.textContent = jobs.length === 1 ? "Cancel this job?" : `Cancel ${jobs.length} jobs?`;
  cancelElements.copy.textContent = "Cancellation never modifies a source recording or removes an earlier valid artifact. Running work stops at a bounded safe checkpoint.";
  cancelElements.dialog.showModal();
}

function closeCancelDialog() {
  cancelElements.dialog.close();
  pendingCancellation = null;
  dialogReturnFocus?.focus();
  dialogReturnFocus = null;
}

async function confirmCancellation() {
  const jobIds = pendingCancellation;
  if (!jobIds || !beginControls(jobIds, "cancel", cancelElements.confirm)) return;
  try {
    const result = jobIds.length === 1
      ? { items: [await runJobMutation(`/api/v1/processing/jobs/${jobIds[0]}/cancel`)] }
      : await runJobMutation("/api/v1/processing/jobs/cancel", { job_ids: jobIds });
    const accepted = result.items.filter((item) => ["requested", "canceled", "already_requested", "already_canceled"].includes(item.outcome)).length;
    const canceledIds = new Set(result.items
      .filter((item) => ["canceled", "already_canceled"].includes(item.outcome))
      .map((item) => item.requested_job_id ?? item.job_id));
    canceledIds.forEach((jobId) => processingState.canceledJobIds.add(jobId));
    if (processingState.overview && canceledIds.size > 0) {
      processingState.overview.queue = processingState.overview.queue.filter((job) => !canceledIds.has(job.id));
      processingState.overview.queued_count = processingState.overview.queue.length;
      renderProcessingOverview();
    }
    closeCancelDialog();
    processingState.selectedQueueIds.clear();
    announce(`${accepted} cancellation${accepted === 1 ? "" : "s"} accepted.`);
    await refreshProcessingAfterMutation();
  } catch (error) {
    closeCancelDialog();
    showNotice(processingElements.notice, error.message, "error");
    await refreshProcessingAfterMutation();
  } finally {
    finishControls(jobIds, "cancel", cancelElements.confirm);
    updateQueueSelectionState();
  }
}

async function retrySelectedFailures() {
  const jobIds = (processingState.pages.failed?.items || [])
    .filter((job) => processingState.selectedFailureIds.has(job.id))
    .map((job) => job.id);
  if (jobIds.length === 0 || !beginControls(jobIds, "retry", processingElements.retrySelected)) return;
  try {
    const result = await runJobMutation("/api/v1/processing/jobs/retry", { job_ids: jobIds });
    const active = result.items.filter((item) => ["queued", "processing"].includes(item.state)).length;
    processingState.selectedFailureIds.clear();
    announce(`${active} current processing attempt${active === 1 ? "" : "s"} queued or active.`);
    await refreshProcessingAfterMutation();
    if (processingState.tab === "failed") await loadProcessingPage("failed", { append: false });
  } catch (error) {
    showNotice(processingElements.notice, error.message, "error");
    await refreshProcessingAfterMutation();
  } finally {
    finishControls(jobIds, "retry", processingElements.retrySelected);
    updateFailureSelectionState();
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
    resetPreview("front", "Recording details are unavailable.", "Unavailable", "failed");
    resetPreview("topdown", "Recording details are unavailable.", "Unavailable", "failed");
    resetImu("Recording details are unavailable.", "Unavailable", "failed");
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
  const diagnosticMessages = [
    detail.diagnostic?.message,
    ...detail.components.map((component) => component.diagnostic?.message),
    ...detail.outputs.map((output) => output.diagnostic?.message),
  ].filter(Boolean).filter((message, index, messages) => messages.indexOf(message) === index);
  detailElements.error.textContent = diagnosticMessages.join("\n");
  detailElements.error.hidden = diagnosticMessages.length === 0;
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
    const description = component.file_name || "No file";
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
    detailElements.components.append(item);
  });
}

function renderOutputFacts(outputs) {
  detailElements.outputs.replaceChildren();
  outputs.forEach((output) => {
    const item = node("article", null, "metadata-item");
    const copy = node("div");
    let description = "No current compatible file";
    if (output.artifact) description = OUTPUT_FORMAT_LABELS[output.kind] || output.artifact.mime_type;
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
    detailElements.outputs.append(item);
  });
}

function renderAnalyzerAction(detail) {
  if (detail.analysis_state === "ready") {
    detailElements.action.hidden = true;
    return;
  }
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
  element.hidden = ["ready", "not_requested", "unavailable", "failed"].includes(state);
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
  resetPreview(kind, "No current compatible output is ready.", label, output.state);
  elements.pane.setAttribute("aria-busy", String(["queued", "processing"].includes(output.state)));
  if (output.state !== "ready" || !output.artifact) {
    elements.messageTitle.textContent = label;
    elements.status.textContent = {
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
  resetImu("No current compatible IMU bundle is ready.", label, output.state);
  imuElements.pane.setAttribute("aria-busy", String(["queued", "processing"].includes(output.state)));
  if (output.state !== "ready" || !output.artifact) {
    imuElements.status.textContent = {
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
    cursorMarker: imuElements.cursorMarker, currentValue: imuElements.currentValue,
    currentTime: imuElements.currentTime, currentState: imuElements.currentState,
    plotLeft: 0, plotTop: 30, plotWidth: 1, plotHeight: 1,
    renderedMinimum: 0, renderedMaximum: 1,
    resizeObserver: null, lastCursorTransform: null, lastReadoutKey: null,
    viewStart: 0, viewEnd: reviewController.durationSeconds,
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
  updateGraphControls();
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
      button.addEventListener("click", () => applyImuSeriesSelection(definition.id, { announceChange: true }));
      group.append(button);
    });
    imuElements.pickerMenu.append(group);
  });
}

function applyImuSeriesSelection(seriesId, { announceChange = false } = {}) {
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
  setTransientPanelOpen(imuElements.pickerMenu, false);
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
  if (announceChange) announce(`${selected.displayLabel} shown on timeline.`);
}

function chartColor(name, fallback) {
  if (typeof window.getComputedStyle !== "function") return fallback;
  return window.getComputedStyle(imuElements.plot).getPropertyValue(name).trim() || fallback;
}

function graphTimestamp(globalTime) {
  return reviewController?.startSeconds === null
    ? formatSeconds(globalTime, true)
    : (reviewController.startSeconds + globalTime).toFixed(3);
}

function visibleImuSegment(segment, start, end) {
  if (!segment.length || segment.at(-1).timeSeconds < start || segment[0].timeSeconds > end) return [];
  const visible = [];
  if (segment[0].timeSeconds <= start && segment.at(-1).timeSeconds >= start) {
    const boundary = window.ImuGraph.sampleAtOrBefore(segment, start) || segment[0];
    visible.push({ ...boundary, timeSeconds: start });
  }
  segment.forEach((sample) => {
    if (sample.timeSeconds > start && sample.timeSeconds < end) visible.push(sample);
  });
  if (segment[0].timeSeconds <= end && segment.at(-1).timeSeconds >= end) {
    const boundary = window.ImuGraph.sampleAtOrBefore(segment, end) || segment[0];
    visible.push({ ...boundary, timeSeconds: end });
  }
  return visible;
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
  const bottom = 30;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  telemetry.plotLeft = left;
  telemetry.plotTop = top;
  telemetry.plotWidth = plotWidth;
  telemetry.plotHeight = plotHeight;

  let minimum = telemetry.minimumValue;
  let maximum = telemetry.maximumValue;
  if (minimum === maximum) {
    const padding = Math.max(0.001, Math.abs(minimum) * 0.1);
    minimum -= padding;
    maximum += padding;
  }
  telemetry.renderedMinimum = minimum;
  telemetry.renderedMaximum = maximum;
  const valueRange = Math.max(0.001, maximum - minimum);
  const y = (value) => top + ((maximum - value) / valueRange) * plotHeight;
  const viewSpan = Math.max(Number.EPSILON, telemetry.viewEnd - telemetry.viewStart);
  const x = (value) => left + window.ImuGraph.cursorFraction(value - telemetry.viewStart, viewSpan) * plotWidth;
  const lineColor = chartColor("--chart-line", "#202224");
  const strongLineColor = chartColor("--chart-line-strong", "#303235");
  const mutedColor = chartColor("--chart-text-dim", "#787878");
  const accentColor = chartColor("--chart-accent", "#f4f4f5");

  context.font = "9px ui-monospace, SFMono-Regular, Menlo, monospace";
  [...new Set([maximum, 0, minimum])].forEach((value) => {
    const lineY = y(value);
    const interiorZero = value === 0 && value !== minimum && value !== maximum;
    context.beginPath();
    context.moveTo(left, lineY + 0.5);
    context.lineTo(left + plotWidth, lineY + 0.5);
    context.strokeStyle = interiorZero ? strongLineColor : lineColor;
    context.lineWidth = interiorZero ? 1.75 : 1;
    context.stroke();
    if (value !== 0) {
      context.fillStyle = mutedColor;
      context.textAlign = "left";
      context.textBaseline = "bottom";
      context.fillText(value.toFixed(2), left, lineY - 4);
    }
  });

  context.save();
  context.beginPath();
  context.rect(left, top, plotWidth, plotHeight);
  context.clip();
  window.ImuGraph.traceSegments(telemetry.samples).forEach((segment) => {
    const visible = visibleImuSegment(segment, telemetry.viewStart, telemetry.viewEnd);
    if (!visible.length) return;
    if (visible.length === 1) {
      context.fillStyle = accentColor;
      context.globalAlpha = 0.88;
      context.beginPath();
      context.arc(x(visible[0].timeSeconds), y(visible[0].value), 1.75, 0, Math.PI * 2);
      context.fill();
      context.globalAlpha = 1;
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
    const gradient = context.createLinearGradient(0, top, 0, top + plotHeight);
    gradient.addColorStop(0, "rgba(244, 244, 245, 0.22)");
    gradient.addColorStop(1, "rgba(244, 244, 245, 0.012)");
    context.fillStyle = gradient;
    context.fill();
    tracePath();
    context.strokeStyle = accentColor;
    context.globalAlpha = 0.88;
    context.lineWidth = 1.05;
    context.lineJoin = "round";
    context.lineCap = "round";
    context.stroke();
    context.globalAlpha = 1;
  });
  context.restore();

  context.fillStyle = mutedColor;
  context.font = "9px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textAlign = "right";
  context.textBaseline = "top";
  context.fillText(graphTimestamp(telemetry.viewEnd), left + plotWidth, top + plotHeight + 10);
}

function updateImuAtGlobalTime(globalTime) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return;
  if (reviewController.clock.playing) ensureGraphWindowContains(globalTime);
  const insideWindow = globalTime >= telemetry.viewStart && globalTime <= telemetry.viewEnd;
  telemetry.cursor.hidden = !insideWindow;
  const span = Math.max(Number.EPSILON, telemetry.viewEnd - telemetry.viewStart);
  const position = window.ImuGraph.snappedCursorPosition(globalTime - telemetry.viewStart, span, telemetry.plotLeft, telemetry.plotWidth, window.devicePixelRatio || 1);
  const transform = `translate3d(${position}px, 0, 0)`;
  if (transform !== telemetry.lastCursorTransform) { telemetry.cursor.style.transform = transform; telemetry.lastCursorTransform = transform; }
  telemetry.currentTime.textContent = graphTimestamp(globalTime);
  const inside = globalTime >= telemetry.coverageStart && globalTime <= telemetry.coverageEnd;
  telemetry.cursor.classList.toggle("outside-coverage", !inside);
  if (!inside) {
    telemetry.cursorMarker.hidden = true;
    updateImuReadout(telemetry, "outside", "—", "Outside IMU coverage");
    return;
  }
  const sample = window.ImuGraph.sampleAtOrBefore(telemetry.samples, globalTime);
  if (!sample || sample.value === null) {
    telemetry.cursorMarker.hidden = true;
    updateImuReadout(telemetry, sample ? `null-${sample.timeNs}` : "none", "—", "No finite IMU value at this time");
    return;
  }
  const valueRange = Math.max(0.001, telemetry.renderedMaximum - telemetry.renderedMinimum);
  const markerY = ((telemetry.renderedMaximum - sample.value) / valueRange) * telemetry.plotHeight;
  telemetry.cursorMarker.hidden = reviewController.clock.playing && activeImuGesture?.type !== "scrub";
  telemetry.cursorMarker.style.transform = `translate3d(-50%, ${markerY - 3.5}px, 0)`;
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
  activeImuGesture = null;
  imuElements.plot.classList.remove("is-seeking", "is-selecting");
  imuElements.selection.hidden = true;
  imuElements.pickerMenu.hidden = true;
  imuElements.pickerMenu.replaceChildren();
  imuElements.pickerTrigger.setAttribute("aria-expanded", "false");
  imuElements.selectedLabel.textContent = "angular_velocity.z";
  if (!reviewController?.telemetry) return;
  reviewController.telemetry.resizeObserver?.disconnect();
  reviewController.telemetry = null;
  updateGraphControls();
  updateTransportAvailability();
}

function updateGraphControls() {
  const telemetry = reviewController?.telemetry;
  const full = reviewController?.durationSeconds || 0;
  const minimumSpan = Math.max(full * 0.04, 0.001);
  const zoomed = Boolean(telemetry && (telemetry.viewStart > 0 || telemetry.viewEnd < full));
  imuElements.reset.disabled = !zoomed;
  imuElements.zoomOut.disabled = !telemetry || !zoomed;
  imuElements.zoomIn.disabled = !telemetry || full <= 0 || (telemetry.viewEnd - telemetry.viewStart) <= minimumSpan + 0.0001;
}

function setGraphWindow(start, end, { announceChange = false } = {}) {
  const telemetry = reviewController?.telemetry;
  const full = reviewController?.durationSeconds || 0;
  if (!telemetry || full <= 0) return;
  const minimumSpan = Math.max(full * 0.04, 0.001);
  let nextStart = Math.max(0, Math.min(Number(start) || 0, full));
  let nextEnd = Math.max(nextStart, Math.min(Number(end) || 0, full));
  if (nextEnd - nextStart < minimumSpan) {
    const anchor = (nextStart + nextEnd) / 2;
    nextStart = Math.max(0, anchor - minimumSpan / 2);
    nextEnd = Math.min(full, nextStart + minimumSpan);
    nextStart = Math.max(0, nextEnd - minimumSpan);
  }
  telemetry.viewStart = nextStart;
  telemetry.viewEnd = nextEnd;
  telemetry.lastCursorTransform = null;
  drawImuTrace(telemetry);
  updateGraphControls();
  updateImuAtGlobalTime(reviewController.clock.globalTime);
  if (announceChange) announce(`Chart zoomed to ${graphTimestamp(nextStart)} through ${graphTimestamp(nextEnd)}.`);
}

function zoomGraph(factor) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry || !reviewController) return;
  const span = telemetry.viewEnd - telemetry.viewStart;
  const nextSpan = Math.min(reviewController.durationSeconds, span * factor);
  const clock = reviewController.clock.globalTime;
  const anchor = clock >= telemetry.viewStart && clock <= telemetry.viewEnd
    ? clock
    : (telemetry.viewStart + telemetry.viewEnd) / 2;
  const ratio = span <= 0 ? 0.5 : (anchor - telemetry.viewStart) / span;
  let start = anchor - nextSpan * ratio;
  let end = start + nextSpan;
  if (start < 0) { end -= start; start = 0; }
  if (end > reviewController.durationSeconds) { start -= end - reviewController.durationSeconds; end = reviewController.durationSeconds; }
  setGraphWindow(start, end, { announceChange: true });
}

function resetGraphWindow() {
  if (!reviewController) return;
  if (reviewController.clock.playing) togglePlayback();
  setGraphWindow(0, reviewController.durationSeconds, { announceChange: true });
}

function ensureGraphWindowContains(globalTime) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry || globalTime >= telemetry.viewStart && globalTime < telemetry.viewEnd) return;
  const full = reviewController.durationSeconds;
  const span = telemetry.viewEnd - telemetry.viewStart;
  if (span >= full) return;
  let start = Math.floor(globalTime / span) * span;
  let end = start + span;
  if (end > full) { end = full; start = Math.max(0, end - span); }
  telemetry.viewStart = start;
  telemetry.viewEnd = end;
  telemetry.lastCursorTransform = null;
  drawImuTrace(telemetry);
  updateGraphControls();
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
  return telemetry.viewStart + window.ImuGraph.timeFromPlotPosition(
    event.clientX - (bounds.left || 0),
    telemetry.plotLeft,
    telemetry.plotWidth,
    telemetry.viewEnd - telemetry.viewStart,
  );
}

function beginImuSeek(event) {
  if (!reviewController?.telemetry || activeImuPointerId !== null || event.isPrimary === false || (event.pointerType === "mouse" && event.button !== 0)) return;
  const value = imuTimeFromPointer(event);
  if (value === null) return;
  if (reviewController.clock.playing) togglePlayback();
  activeImuPointerId = event.pointerId;
  activeImuGesture = { type: event.shiftKey ? "zoom" : "scrub", start: value, current: value };
  imuElements.plot.setPointerCapture?.(event.pointerId);
  imuElements.plot.focus?.({ preventScroll: true });
  imuElements.plot.classList.add(event.shiftKey ? "is-selecting" : "is-seeking");
  event.preventDefault();
  if (event.shiftKey) updateImuSelection(value, value);
  else seekGlobalTime(value);
}

function moveImuSeek(event) {
  if (event.pointerId !== activeImuPointerId) return;
  if (activeImuGesture?.type === "zoom") {
    const value = imuTimeFromPointer(event);
    if (value !== null) {
      activeImuGesture.current = value;
      updateImuSelection(activeImuGesture.start, value);
    }
    event.preventDefault();
    return;
  }
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
  if (activeImuGesture?.type === "zoom") {
    const value = imuTimeFromPointer(event);
    const start = Math.min(activeImuGesture.start, value ?? activeImuGesture.current);
    const end = Math.max(activeImuGesture.start, value ?? activeImuGesture.current);
    const telemetry = reviewController.telemetry;
    const minimumSelection = (telemetry.viewEnd - telemetry.viewStart) * (8 / Math.max(1, telemetry.plotWidth));
    if (end - start >= minimumSelection) setGraphWindow(start, end, { announceChange: true });
    finishImuGesture(event);
    event.preventDefault();
    return;
  }
  if (imuSeekAnimation !== null) window.cancelAnimationFrame(imuSeekAnimation);
  imuSeekAnimation = null;
  pendingImuSeekTime = null;
  const value = imuTimeFromPointer(event);
  if (value !== null) seekGlobalTime(value);
  if (imuElements.plot.hasPointerCapture?.(event.pointerId)) imuElements.plot.releasePointerCapture(event.pointerId);
  activeImuPointerId = null;
  activeImuGesture = null;
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
  activeImuGesture = null;
  imuElements.plot.classList.remove("is-seeking", "is-selecting");
  imuElements.selection.hidden = true;
}

function updateImuSelection(start, end) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return;
  const span = Math.max(Number.EPSILON, telemetry.viewEnd - telemetry.viewStart);
  const first = Math.max(0, Math.min(1, (Math.min(start, end) - telemetry.viewStart) / span));
  const last = Math.max(0, Math.min(1, (Math.max(start, end) - telemetry.viewStart) / span));
  const selectionLeft = telemetry.plotLeft + first * telemetry.plotWidth;
  const selectionRight = telemetry.plotLeft + last * telemetry.plotWidth;
  imuElements.selection.style.left = `${selectionLeft}px`;
  imuElements.selection.style.width = `${Math.max(1, selectionRight - selectionLeft)}px`;
  imuElements.selectionStart.textContent = graphTimestamp(Math.min(start, end));
  imuElements.selectionEnd.textContent = graphTimestamp(Math.max(start, end));
  imuElements.selection.hidden = false;
  const plotRight = telemetry.plotLeft + telemetry.plotWidth;
  const startWidth = imuElements.selectionStart.offsetWidth || 0;
  const endWidth = imuElements.selectionEnd.offsetWidth || 0;
  const startX = Math.max(telemetry.plotLeft + 5, Math.min(plotRight - startWidth - 5, selectionLeft + 5));
  const endX = Math.max(telemetry.plotLeft + endWidth + 5, Math.min(plotRight - 5, selectionRight - 5));
  imuElements.selectionStart.style.left = `${startX - selectionLeft}px`;
  imuElements.selectionEnd.style.left = `${endX - selectionLeft}px`;
}

function finishImuGesture(event) {
  if (imuElements.plot.hasPointerCapture?.(event.pointerId)) imuElements.plot.releasePointerCapture(event.pointerId);
  activeImuPointerId = null;
  activeImuGesture = null;
  imuElements.plot.classList.remove("is-seeking", "is-selecting");
  imuElements.selection.hidden = true;
}

function keyboardImuSeek(event) {
  if (!reviewController?.telemetry) return;
  const full = reviewController.durationSeconds;
  const changes = { ArrowLeft: -full * 0.01, ArrowDown: -full * 0.01, ArrowRight: full * 0.01, ArrowUp: full * 0.01, PageDown: -full * 0.1, PageUp: full * 0.1 };
  let target = null;
  if (event.key in changes) target = reviewController.clock.globalTime + changes[event.key];
  else if (event.key === "Home") target = 0;
  else if (event.key === "End") target = reviewController.durationSeconds;
  else if (["+", "="].includes(event.key)) { event.preventDefault(); if (reviewController.clock.playing) togglePlayback(); zoomGraph(0.625); return; }
  else if (["-", "_"].includes(event.key)) { event.preventDefault(); if (reviewController.clock.playing) togglePlayback(); zoomGraph(1.6); return; }
  else if ([" ", "k", "K"].includes(event.key)) { event.preventDefault(); togglePlayback(); return; }
  if (target === null) return;
  event.preventDefault();
  if (reviewController.clock.playing) togglePlayback();
  seekGlobalTime(target);
}

function wheelImuSeek(event) {
  const telemetry = reviewController?.telemetry;
  if (!telemetry) return;
  event.preventDefault();
  if (reviewController.clock.playing) togglePlayback();
  const delta = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
  const direction = Math.sign(delta);
  const step = reviewController.durationSeconds * Math.max(0.005, Math.min(0.04, Math.abs(delta) * 0.0002));
  if (direction !== 0) seekGlobalTime(reviewController.clock.globalTime + direction * step);
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
    if (url.origin === window.location.origin) {
      event.preventDefault();
      if (routeLink.dataset.nav === "recordings" && currentRoute?.view === "recordings") {
        setFolderPanel(byId("recordings-view").classList.contains("is-folders-collapsed"), { returnFocus: false });
      } else {
        navigate(url.pathname);
      }
    }
  }
  if (!imuElements.picker.contains(event.target)) {
    setTransientPanelOpen(imuElements.pickerMenu, false);
    imuElements.pickerTrigger.setAttribute("aria-expanded", "false");
  }
  if (!event.target.closest("[data-catalog-filter]")) closeCatalogFilterMenus();
});
window.addEventListener("popstate", () => activateRoute(parseRoute(window.location.pathname) || { view: "recordings" }, { focus: true }));
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
function catalogFilterControl(key) {
  return catalogElements.filterControls.find((control) => control.dataset.catalogFilter === key);
}

function syncCatalogFilterControl(key) {
  const control = catalogFilterControl(key);
  if (!control) return;
  const input = key === "analysis" ? catalogElements.analysisFilter : catalogElements.healthFilter;
  const selected = control.querySelector(`[data-filter-value="${input.value}"]`) || control.querySelector("[data-filter-value]");
  control.querySelectorAll("[data-filter-value]").forEach((option) => option.setAttribute("aria-selected", String(option === selected)));
  const value = control.querySelector(".recording-filter-value");
  if (value && selected) value.textContent = selected.textContent;
  const trigger = control.querySelector(".recording-filter-trigger");
  if (trigger && selected) trigger.setAttribute("aria-label", `${key === "analysis" ? "Analysis" : "ROS health"} filter, ${selected.textContent}`);
}

function closeCatalogFilterMenus(except = null) {
  catalogElements.filterControls.forEach((control) => {
    if (control === except) return;
    const trigger = control.querySelector(".recording-filter-trigger");
    const menu = control.querySelector(".recording-filter-menu");
    if (!trigger || !menu) return;
    trigger.setAttribute("aria-expanded", "false");
    menu.hidden = true;
  });
}

function applyCatalogFilter(key, value) {
  const input = key === "analysis" ? catalogElements.analysisFilter : catalogElements.healthFilter;
  input.value = value;
  catalogState[key] = value;
  catalogState.page = 1;
  syncCatalogFilterControl(key);
  renderRecordingTable();
  syncSummaryCards();
}

catalogElements.filterControls.forEach((control) => {
  const key = control.dataset.catalogFilter;
  const trigger = control.querySelector(".recording-filter-trigger");
  const menu = control.querySelector(".recording-filter-menu");
  const options = [...control.querySelectorAll("[data-filter-value]")];
  if (!trigger || !menu || options.length === 0) return;
  trigger.addEventListener("click", () => {
    const open = trigger.getAttribute("aria-expanded") !== "true";
    closeCatalogFilterMenus(open ? control : null);
    trigger.setAttribute("aria-expanded", String(open));
    menu.hidden = !open;
  });
  trigger.addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    closeCatalogFilterMenus(control);
    trigger.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    const selectedIndex = Math.max(0, options.findIndex((option) => option.getAttribute("aria-selected") === "true"));
    options[event.key === "ArrowDown" ? selectedIndex : Math.max(0, selectedIndex - 1)].focus();
  });
  options.forEach((option) => option.addEventListener("click", () => {
    applyCatalogFilter(key, option.dataset.filterValue);
    closeCatalogFilterMenus();
    trigger.focus();
  }));
  menu.addEventListener("keydown", (event) => {
    const current = options.indexOf(document.activeElement);
    let target = null;
    if (event.key === "Home") target = options[0];
    else if (event.key === "End") target = options.at(-1);
    else if (event.key === "ArrowDown") target = options[(current + 1 + options.length) % options.length];
    else if (event.key === "ArrowUp") target = options[(current - 1 + options.length) % options.length];
    else if (event.key === "Escape") {
      event.preventDefault();
      closeCatalogFilterMenus();
      trigger.focus();
      return;
    }
    if (target) { event.preventDefault(); target.focus(); }
  });
  syncCatalogFilterControl(key);
});
document.querySelectorAll(".table-sort").forEach((button) => button.addEventListener("click", () => sortRecordings(button.dataset.sort)));
document.querySelectorAll("[data-summary-analysis]").forEach((button) => button.addEventListener("click", () => {
  catalogState.analysis = catalogState.analysis === button.dataset.summaryAnalysis ? "all" : button.dataset.summaryAnalysis;
  catalogElements.analysisFilter.value = catalogState.analysis;
  syncCatalogFilterControl("analysis");
  catalogState.page = 1;
  renderRecordingTable();
  syncSummaryCards();
}));
document.querySelectorAll("[data-summary-health]").forEach((button) => button.addEventListener("click", () => {
  catalogState.health = catalogState.health === button.dataset.summaryHealth ? "all" : button.dataset.summaryHealth;
  catalogElements.healthFilter.value = catalogState.health;
  syncCatalogFilterControl("health");
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
catalogElements.previous.addEventListener("click", () => { catalogState.page -= 1; renderRecordingTableWithHeightTransition(); });
catalogElements.next.addEventListener("click", () => { catalogState.page += 1; renderRecordingTableWithHeightTransition(); });
catalogElements.retry.addEventListener("click", () => loadCatalog({ initial: true }));
catalogElements.rescan.addEventListener("click", rescanCatalog);
catalogElements.prepare.addEventListener("click", openPreparationDialog);
preparationElements.form.addEventListener("submit", prepareSelected);
preparationElements.form.querySelectorAll('[name="output_kind"]').forEach((input) => input.addEventListener("change", updatePreparationDialog));
preparationElements.cancel.addEventListener("click", closePreparationDialog);
preparationElements.dialog.addEventListener("cancel", (event) => { event.preventDefault(); closePreparationDialog(); });
preparationElements.dialog.addEventListener("click", (event) => { if (event.target === preparationElements.dialog) closePreparationDialog(); });
toastElements.dismiss.addEventListener("click", () => { toastElements.root.hidden = true; });
toastElements.processing.addEventListener("click", () => { toastElements.root.hidden = true; navigate("/processing"); });
function clearCatalogFilters() {
  catalogState.query = ""; catalogState.analysis = "all"; catalogState.health = "all"; catalogState.folderPath = ""; catalogState.page = 1;
  catalogElements.search.value = ""; catalogElements.analysisFilter.value = "all"; catalogElements.healthFilter.value = "all";
  syncCatalogFilterControl("analysis"); syncCatalogFilterControl("health"); closeCatalogFilterMenus();
  renderFolderTree(); renderRecordingTable(); syncSummaryCards();
  announce("Recording filters cleared.");
}
byId("clear-filters").addEventListener("click", clearCatalogFilters);
catalogElements.clearFilters.addEventListener("click", clearCatalogFilters);
catalogElements.collapseFolders.addEventListener("click", (event) => setFolderPanel(false, { returnFocus: event.detail === 0 }));
catalogElements.expandFolders.addEventListener("click", (event) => setFolderPanel(true, { returnFocus: event.detail === 0 }));

function updateFolderPanelState(open) {
  const recordingsView = byId("recordings-view");
  recordingsView.classList.toggle("is-folders-collapsed", !open);
  catalogElements.folderPanel.classList.toggle("is-collapsed", !open);
  catalogElements.folderPanel.setAttribute("aria-hidden", String(!open));
  catalogElements.folderPanel.toggleAttribute("inert", !open);
  catalogElements.collapseFolders.setAttribute("aria-expanded", String(open));
  const archiveViewButton = byId("archive-view-button");
  archiveViewButton?.setAttribute("aria-expanded", String(open));
  archiveViewButton?.setAttribute("aria-controls", "folder-panel");
  syncFolderReveal();
  try { localStorage.setItem("tectrace-folders", open ? "open" : "collapsed"); } catch { /* Visual preference remains in memory. */ }
}

function syncFolderReveal() {
  const collapsed = byId("recordings-view").classList.contains("is-folders-collapsed");
  const shouldShow = collapsed && currentRoute?.view === "recordings";
  const sidebar = document.querySelector(".sidebar");
  const slot = byId("folder-reveal-slot");
  sidebar?.classList.toggle("has-folder-slot", shouldShow);
  sidebar?.classList.toggle("has-folder-reveal", shouldShow);
  slot.classList.toggle("is-reserved", shouldShow);
  slot.classList.toggle("is-visible", shouldShow);
  slot.setAttribute("aria-hidden", String(!shouldShow));
  slot.toggleAttribute("inert", !shouldShow);
  catalogElements.expandFolders.tabIndex = shouldShow ? 0 : -1;
}

function setFolderPanel(open, { returnFocus = true } = {}) {
  const recordingsView = byId("recordings-view");
  if (recordingsView.classList.contains("is-folders-collapsed") === !open && folderPanelAnimations.length === 0) return;
  const transitionVersion = ++folderPanelTransitionVersion;
  const canAnimate = !reduceMotionQuery.matches
    && typeof recordingsView.animate === "function"
    && typeof catalogElements.folderPanel.animate === "function"
    && typeof window.getComputedStyle === "function";
  const oldGridColumns = canAnimate ? window.getComputedStyle(recordingsView).gridTemplateColumns : "";
  const oldPanelStyle = canAnimate ? window.getComputedStyle(catalogElements.folderPanel) : null;
  const oldPanelOpacity = oldPanelStyle?.opacity || "1";
  const oldPanelTransform = oldPanelStyle?.transform === "none" ? "translate3d(0, 0, 0)" : oldPanelStyle?.transform || "translate3d(0, 0, 0)";
  if (!open && catalogElements.folderPanel.contains(document.activeElement)) document.activeElement?.blur?.();
  folderPanelAnimations.forEach((animation) => animation.cancel());
  folderPanelAnimations = [];
  updateFolderPanelState(open);

  const finish = () => {
    if (folderPanelTransitionVersion !== transitionVersion) return;
    folderPanelAnimations.forEach((animation) => animation.cancel());
    folderPanelAnimations = [];
    if (returnFocus) (open ? catalogElements.collapseFolders : catalogElements.expandFolders).focus();
    announce(open ? "Folders shown" : "Folders hidden");
  };
  if (!canAnimate) { finish(); return; }

  const newGridColumns = window.getComputedStyle(recordingsView).gridTemplateColumns;
  if (oldGridColumns !== newGridColumns) {
    folderPanelAnimations.push(recordingsView.animate([
      { gridTemplateColumns: oldGridColumns },
      { gridTemplateColumns: newGridColumns },
    ], { duration: 260, easing: "cubic-bezier(.4, 0, .2, 1)", fill: "both" }));
  }
  folderPanelAnimations.push(catalogElements.folderPanel.animate([
    { opacity: oldPanelOpacity, transform: oldPanelTransform },
    { opacity: open ? 1 : 0, transform: open ? "translate3d(0, 0, 0)" : "translate3d(-100%, 0, 0)" },
  ], { duration: 260, easing: "cubic-bezier(.4, 0, .2, 1)", fill: "both" }));
  Promise.allSettled(folderPanelAnimations.map((animation) => animation.finished)).then(finish);
}

function setRecordingDetailsCollapsed(collapsed, { returnFocus = true } = {}) {
  const analyzerView = byId("analyzer-view");
  const detailsPanel = byId("recording-details-panel");
  const telemetryPanel = imuElements.pane;
  const toggle = byId("collapse-recording-details");
  const transitionVersion = ++recordingDetailsTransitionVersion;
  const detailsBefore = detailsPanel.getBoundingClientRect();
  const telemetryBefore = telemetryPanel.getBoundingClientRect();
  const layoutWasCollapsed = analyzerView.classList.contains("is-details-collapsed");

  recordingDetailsLayoutAnimations.forEach((animation) => animation.cancel());
  recordingDetailsLayoutAnimations = [];
  detailsPanel.style.height = "";
  telemetryPanel.style.width = "";

  // Measure the destination without letting the browser paint it early.
  analyzerView.classList.toggle("is-details-collapsed", collapsed);
  const detailsAfter = detailsPanel.getBoundingClientRect();
  const telemetryAfter = telemetryPanel.getBoundingClientRect();
  analyzerView.classList.toggle("is-details-collapsed", layoutWasCollapsed);

  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "Expand recording details" : "Compact recording details");
  toggle.title = collapsed ? "Expand recording details" : "Compact recording details";

  detailsPanel.style.height = `${detailsBefore.height}px`;
  telemetryPanel.style.width = `${telemetryBefore.width}px`;

  const finishLayout = () => window.requestAnimationFrame(() => {
    if (recordingDetailsTransitionVersion !== transitionVersion) return;
    analyzerView.classList.toggle("is-details-collapsed", collapsed);
    detailsPanel.style.height = "";
    telemetryPanel.style.width = "";
    document.documentElement?.classList.remove("is-recording-details-transition");
    recordingDetailsLayoutAnimations.forEach((animation) => animation.cancel());
    recordingDetailsLayoutAnimations = [];
    if (reviewController?.telemetry) {
      drawImuTrace(reviewController.telemetry);
      updateImuAtGlobalTime(reviewController.clock.globalTime);
    }
    if (returnFocus) toggle.focus();
  });

  if (reduceMotionQuery.matches
      || typeof detailsPanel.animate !== "function"
      || typeof telemetryPanel.animate !== "function") {
    finishLayout();
  } else {
    document.documentElement?.classList.add("is-recording-details-transition");
    const runPhase = async (element, property, from, to, duration) => {
      const animation = element.animate([
        { [property]: `${from}px` },
        { [property]: `${to}px` },
      ], {
        duration,
        easing: "cubic-bezier(.16, 1, .3, 1)",
        fill: "forwards",
      });
      recordingDetailsLayoutAnimations = [animation];

      try {
        await animation.finished;
      } catch {
        return false;
      }
      if (recordingDetailsTransitionVersion !== transitionVersion) return false;

      element.style[property] = `${to}px`;
      animation.cancel();
      recordingDetailsLayoutAnimations = [];
      return true;
    };

    const runTransition = async () => {
      if (collapsed) {
        if (!await runPhase(detailsPanel, "height", detailsBefore.height, detailsAfter.height, RECORDING_DETAILS_RESIZE_DURATION)) return;
        analyzerView.classList.add("is-details-collapsed");
        if (!await runPhase(telemetryPanel, "width", telemetryBefore.width, telemetryAfter.width, RECORDING_DETAILS_GRAPH_DURATION)) return;
      } else {
        if (!await runPhase(telemetryPanel, "width", telemetryBefore.width, telemetryAfter.width, RECORDING_DETAILS_GRAPH_DURATION)) return;
        analyzerView.classList.remove("is-details-collapsed");
        if (!await runPhase(detailsPanel, "height", detailsBefore.height, detailsAfter.height, RECORDING_DETAILS_RESIZE_DURATION)) return;
      }
      finishLayout();
    };

    runTransition();
  }
  announce(collapsed ? "Recording details compacted" : "Recording details expanded");
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
processingElements.queueSelectAll.addEventListener("change", () => {
  (processingState.overview?.queue || []).forEach((job) => {
    if (processingElements.queueSelectAll.checked) processingState.selectedQueueIds.add(job.id);
    else processingState.selectedQueueIds.delete(job.id);
  });
  renderQueue();
});
function selectedQueueIdsInOrder() {
  return (processingState.overview?.queue || [])
    .filter((job) => processingState.selectedQueueIds.has(job.id))
    .map((job) => job.id);
}
processingElements.moveEarlier.addEventListener("click", () => reorderJobs(selectedQueueIdsInOrder(), "earlier", processingElements.moveEarlier));
processingElements.moveLater.addEventListener("click", () => reorderJobs(selectedQueueIdsInOrder(), "later", processingElements.moveLater));
processingElements.cancelSelected.addEventListener("click", () => {
  const selected = (processingState.overview?.queue || []).filter((job) => processingState.selectedQueueIds.has(job.id));
  requestCancellation(selected, processingElements.cancelSelected);
});
processingElements.failureSelectAll.addEventListener("change", () => {
  (processingState.pages.failed?.items || []).forEach((job) => {
    if (processingElements.failureSelectAll.checked) processingState.selectedFailureIds.add(job.id);
    else processingState.selectedFailureIds.delete(job.id);
  });
  renderProcessingPage("failed");
});
processingElements.retrySelected.addEventListener("click", retrySelectedFailures);
cancelElements.keep.addEventListener("click", closeCancelDialog);
cancelElements.confirm.addEventListener("click", confirmCancellation);
cancelElements.dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeCancelDialog(); });
cancelElements.dialog.addEventListener("click", (event) => { if (event.target === cancelElements.dialog) closeCancelDialog(); });
processingElements.dialogClose.addEventListener("click", closeFailureDialog);
processingElements.dialogDismiss.addEventListener("click", closeFailureDialog);
processingElements.dialogCopyButton.addEventListener("click", async () => {
  if (!diagnosticJob) return;
  const copy = processingDiagnosticText(diagnosticJob);
  try {
    await navigator.clipboard.writeText(copy);
    announce("Diagnostic copied.");
  } catch {
    announce("The diagnostic could not be copied automatically.");
  }
});
processingElements.dialogOpenButton.addEventListener("click", () => {
  const job = diagnosticJob;
  if (!job) return;
  closeFailureDialog();
  navigate(`/recordings/${job.recording_id}`);
});
processingElements.dialogRetryButton.addEventListener("click", () => {
  const job = diagnosticJob;
  if (!job) return;
  closeFailureDialog();
  retryJob(job, processingElements.dialogRetryButton);
});
processingElements.dialog.addEventListener("click", (event) => { if (event.target === processingElements.dialog) closeFailureDialog(); });
processingElements.dialog.addEventListener("cancel", (event) => { event.preventDefault(); closeFailureDialog(); });

timelineElements.play.addEventListener("click", togglePlayback);
timelineElements.slider.addEventListener("input", () => seekGlobalTime(Number(timelineElements.slider.value)));
imuElements.pickerTrigger.addEventListener("click", () => {
  if (imuElements.pickerTrigger.disabled) return;
  const open = imuElements.pickerMenu.hidden;
  setTransientPanelOpen(imuElements.pickerMenu, open);
  imuElements.pickerTrigger.setAttribute("aria-expanded", String(open));
  if (open) imuElements.pickerMenu.querySelector('[aria-checked="true"]')?.focus();
});
imuElements.pickerMenu.addEventListener("keydown", (event) => {
  const options = [...imuElements.pickerMenu.querySelectorAll("[data-sensor]:not(:disabled)")];
  const index = options.indexOf(document.activeElement);
  if (event.key === "Escape") { event.preventDefault(); setTransientPanelOpen(imuElements.pickerMenu, false); imuElements.pickerTrigger.setAttribute("aria-expanded", "false"); imuElements.pickerTrigger.focus(); return; }
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
imuElements.plot.addEventListener("wheel", wheelImuSeek, { passive: false });
imuElements.zoomIn.addEventListener("click", () => { if (reviewController?.clock.playing) togglePlayback(); zoomGraph(0.625); });
imuElements.zoomOut.addEventListener("click", () => { if (reviewController?.clock.playing) togglePlayback(); zoomGraph(1.6); });
imuElements.reset.addEventListener("click", resetGraphWindow);
document.addEventListener("keydown", (event) => {
  if (event.key === "Shift" && currentRoute?.view === "analyzer" && reviewController?.telemetry) imuElements.plot.classList.add("is-shift-ready");
  const editing = event.target?.matches?.("input, textarea, select, button, [contenteditable='true']");
  if (currentRoute?.view === "analyzer" && !editing && event.target !== imuElements.plot && imuElements.pickerMenu.hidden) keyboardImuSeek(event);
});
document.addEventListener("keyup", (event) => {
  if (event.key === "Shift" && activeImuGesture?.type !== "zoom") imuElements.plot.classList.remove("is-shift-ready");
});
window.addEventListener("blur", () => {
  if (activeImuGesture?.type !== "zoom") imuElements.plot.classList.remove("is-shift-ready");
});
byId("collapse-recording-details").addEventListener("click", () => {
  setRecordingDetailsCollapsed(!byId("analyzer-view").classList.contains("is-details-collapsed"));
});
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

setFolderPanel(true, { returnFocus: false });
window.requestAnimationFrame(() => syncProcessingTabIndicator({ animate: false }));
if (typeof ResizeObserver === "function" && processingElements.tabs) {
  new ResizeObserver(() => syncProcessingTabIndicator({ animate: false })).observe(processingElements.tabs);
}
const initialRoute = parseRoute(window.location.pathname);
if (initialRoute) activateRoute(initialRoute);
else navigate("/", { replace: true });
