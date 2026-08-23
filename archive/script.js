const liveRegion = document.querySelector('#live-region');
const searchInput = document.querySelector('#bag-search');
const filterButton = document.querySelector('#filter-button');
const filterMenu = document.querySelector('#filter-menu');
const filterControl = document.querySelector('.filter-control');
const filterOptions = [...document.querySelectorAll('.filter-option')];
const bagRows = [...document.querySelectorAll('.bag-row')];
const bagList = document.querySelector('#bag-list');
const visibleCount = document.querySelector('#visible-count');
const emptyState = document.querySelector('#empty-state');
const breadcrumbCurrent = document.querySelector('#breadcrumb-current');
const homeLink = document.querySelector('#home-link');
const imuChart = document.querySelector('#imu-chart');
const chartReset = document.querySelector('#chart-reset');
const chartZoomOut = document.querySelector('#chart-zoom-out');
const chartZoomIn = document.querySelector('#chart-zoom-in');
const timelinePlay = document.querySelector('#timeline-play');
const globalTimeline = document.querySelector('#global-timeline');
const timelinePosition = document.querySelector('.timeline-position');
const timelineCurrent = document.querySelector('#timeline-current');
const timelineTotal = document.querySelector('#timeline-total');
const timelineVideos = [...document.querySelectorAll('[data-timeline-video]')];
const timelineVideoStates = timelineVideos.map((video) => ({
  video,
  offset: Number(video.dataset.startOffset) || 0,
  label: video.dataset.streamLabel || 'view',
  status: document.getElementById(video.dataset.statusId),
}));
const sensorPicker = document.querySelector('.sensor-picker');
const sensorPickerTrigger = document.querySelector('#sensor-picker-trigger');
const sensorPickerMenu = document.querySelector('#sensor-picker-menu');
const sensorOptions = [...document.querySelectorAll('[data-sensor]')];
const selectedSensorLabel = document.querySelector('#selected-sensor-label');
const analyzerView = document.querySelector('#analyzer-view');
const collapseRecordingDetails = document.querySelector('#collapse-recording-details');
const recordingDetailsPanel = document.querySelector('#recording-details-panel');
const analyzerTelemetryPanel = analyzerView.querySelector('.telemetry-panel');
const homeView = document.querySelector('#home-view');
const workspaceViewStack = document.querySelector('#workspace-view-stack');
const sidebar = document.querySelector('.sidebar');
const archiveViewButton = document.querySelector('#archive-view-button');
const progressionView = document.querySelector('#progression-view');
const experimentsView = document.querySelector('#experiments-view');
const recordingsTableBody = document.querySelector('.rosbag-table tbody');
const sortButtons = [...document.querySelectorAll('.table-sort')];
const selectAllRecordings = document.querySelector('#select-all-recordings');
const selectedCount = document.querySelector('#selected-count');
const selectionContext = document.querySelector('#selection-context');
const prepareSelectedButton = document.querySelector('.prepare-selected-button');
const bulkActionButtons = [...document.querySelectorAll('[data-bulk-action]')];
const previousPage = document.querySelector('#previous-page');
const nextPage = document.querySelector('#next-page');
const pageStatus = document.querySelector('#page-status');
const pageButtons = document.querySelector('#page-buttons');
const tableSearch = document.querySelector('#home-table-search');
const analysisFilter = document.querySelector('#analysis-filter');
const healthFilter = document.querySelector('#health-filter');
const summaryGroupButtons = [...document.querySelectorAll('[data-summary-group]')];
const statusStrip = document.querySelector('.status-strip');
const statusStripIndicator = document.querySelector('.status-strip-indicator');
const clearFilterMenu = document.querySelector('#clear-filter-menu');
const folderPanel = document.querySelector('#folder-panel');
const collapseFolders = document.querySelector('#collapse-folders');
const expandFolders = document.querySelector('#expand-folders');
const folderRevealSlot = document.querySelector('#folder-reveal-slot');
const folderItems = [...document.querySelectorAll('[data-folder]')];
const folderSearch = document.querySelector('#folder-search');
const folderEmpty = document.querySelector('#folder-empty');
const tableEmptyState = document.querySelector('#table-empty-state');
const clearFilters = document.querySelector('#clear-filters');
const rescanArchive = document.querySelector('#rescan-archive');
const lastScanned = document.querySelector('#last-scanned');
const recordingsTable = document.querySelector('.rosbag-table');
const homeTablePanel = document.querySelector('.home-table-panel');
const toolButtons = [...document.querySelectorAll('.tool-button')];
const toolListIndicator = document.querySelector('.tool-list-indicator');
const currentProcessingJob = document.querySelector('[data-current-job]');
const jobFilterButtons = [...document.querySelectorAll('[data-job-filter]')];
const processingTabs = document.querySelector('.processing-tabs');
const processingTabIndicator = document.querySelector('.processing-tab-indicator');
const processingPanels = [...document.querySelectorAll('.processing-view-panel')];
const processingErrorDialog = document.querySelector('#processing-error-dialog');
const processingErrorTitle = document.querySelector('#processing-error-title');
const processingErrorCopy = document.querySelector('#processing-error-copy');
const processingErrorMeta = document.querySelector('#processing-error-meta');
const processingErrorRecovery = document.querySelector('#processing-error-recovery');
const closeProcessingError = document.querySelector('#close-processing-error');
const copyProcessingError = document.querySelector('#copy-processing-error');
const openProcessingRecording = document.querySelector('#open-processing-recording');
const retryProcessingError = document.querySelector('#retry-processing-error');
const processingQueueBody = document.querySelector('#processing-queue-body');
const failureTableBody = document.querySelector('#failure-table-body');
const queueCount = document.querySelector('#queue-count');
const selectAllQueued = document.querySelector('#select-all-queued');
const queueSelectionActions = document.querySelector('#queue-selection-actions');
const queueSelectionFooter = document.querySelector('#queue-selection-footer');
const queueSelectedCount = document.querySelector('#queue-selected-count');
const moveSelectedQueueUp = document.querySelector('#move-selected-queue-up');
const moveSelectedQueueDown = document.querySelector('#move-selected-queue-down');
const cancelSelectedQueue = document.querySelector('#cancel-selected-queue');
const failureCount = document.querySelector('#failure-count');
const selectAllFailures = document.querySelector('#select-all-failures');
const failureSelectionActions = document.querySelector('#failure-selection-actions');
const failureSelectionFooter = document.querySelector('#failure-selection-footer');
const failureSelectedCount = document.querySelector('#failure-selected-count');
const retrySelectedFailures = document.querySelector('#retry-selected-failures');
const openFigure8 = document.querySelector('#open-figure8');
const prepareDialog = document.querySelector('#prepare-dialog');
const prepareForm = document.querySelector('#prepare-form');
const prepareRecordings = document.querySelector('#prepare-recordings');
const prepareSelectionSummary = document.querySelector('#prepare-selection-summary');
const prepareImpact = document.querySelector('#prepare-impact');
const cancelPrepare = document.querySelector('#cancel-prepare');
const operationToast = document.querySelector('#operation-toast');
const operationToastTitle = document.querySelector('#operation-toast-title');
const operationToastCopy = document.querySelector('#operation-toast-copy');
const viewProcessingToast = document.querySelector('#view-processing-toast');
const dismissToast = document.querySelector('#dismiss-toast');
const cancelJobDialog = document.querySelector('#cancel-job-dialog');
const cancelJobTitle = document.querySelector('#cancel-job-title');
const cancelJobCopy = document.querySelector('#cancel-job-copy');
const keepProcessing = document.querySelector('#keep-processing');
const confirmJobCancel = document.querySelector('#confirm-job-cancel');
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

let activeAppView = 'archive';
let workspaceSwitchVersion = 0;
let toolIndicatorAnimation = null;
const transientPanelAnimations = new WeakMap();
let recordingDetailsLayoutAnimations = [];
let recordingDetailsTransitionVersion = 0;
let pendingCancellation = null;

const RECORDING_DETAILS_RESIZE_DURATION = 360;
const RECORDING_DETAILS_GRAPH_DURATION = 520;

function setTransientPanelOpen(panel, open) {
  const runningAnimation = transientPanelAnimations.get(panel);
  runningAnimation?.cancel();

  if (open) panel.hidden = false;
  if (reduceMotion.matches || typeof panel.animate !== 'function') {
    panel.hidden = !open;
    return;
  }

  const animation = panel.animate(open ? [
    { opacity: 0, transform: 'translate3d(0, -4px, 0)' },
    { opacity: 1, transform: 'translate3d(0, 0, 0)' }
  ] : [
    { opacity: 1, transform: 'translate3d(0, 0, 0)' },
    { opacity: 0, transform: 'translate3d(0, -2px, 0)' }
  ], {
    duration: open ? 150 : 100,
    easing: open ? 'cubic-bezier(.16, 1, .3, 1)' : 'cubic-bezier(.4, 0, 1, 1)',
    fill: 'both'
  });

  transientPanelAnimations.set(panel, animation);
  animation.finished.then(() => {
    if (transientPanelAnimations.get(panel) !== animation) return;
    if (!open) panel.hidden = true;
    animation.cancel();
    transientPanelAnimations.delete(panel);
  }).catch(() => {});
}

function setWorkspaceView(nextView) {
  const views = [homeView, analyzerView, progressionView, experimentsView];
  const switchVersion = ++workspaceSwitchVersion;
  workspaceViewStack.classList.add('is-switching');
  workspaceViewStack.classList.remove('is-transitioning');
  views.forEach((view) => {
    view.classList.remove('is-view-entering', 'is-view-leaving');
    view.removeAttribute('aria-hidden');
    view.hidden = view !== nextView;
    view.toggleAttribute('inert', view !== nextView);
  });

  // Keep the content swap completely still. The rail indicator lives outside
  // this stack, so it remains the only animated part of primary navigation.
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
    if (workspaceSwitchVersion === switchVersion) {
      workspaceViewStack.classList.remove('is-switching');
    }
  }));
}

function acknowledgeStateChange(element) {
  if (!element || reduceMotion.matches || typeof element.animate !== 'function') return;
  element.animate([
    { opacity: .64 },
    { opacity: 1 }
  ], {
    duration: 180,
    easing: 'cubic-bezier(.16, 1, .3, 1)'
  });
}

function removeRowWithMotion(row, onRemoved) {
  if (reduceMotion.matches || typeof row.animate !== 'function') {
    row.remove();
    onRemoved();
    return;
  }

  const animation = row.animate([
    { opacity: 1, transform: 'translate3d(0, 0, 0)' },
    { opacity: 0, transform: 'translate3d(4px, 0, 0)' }
  ], {
    duration: 120,
    easing: 'cubic-bezier(.4, 0, 1, 1)'
  });
  animation.finished.then(() => {
    row.remove();
    onRemoved();
  }).catch(() => {});
}
updateFolderPanel(true);

const IMU_BUNDLE_URL = 'figure8/figure8-imu-bundle.json';
const FIGURE8_TIMELINE_DURATION_SECONDS = 152.969297;
const IMU_START_OFFSET_SECONDS = 0.000054;
const DEFAULT_TIMELINE_DURATION = FIGURE8_TIMELINE_DURATION_SECONDS;
const TIMELINE_PREVIEW_SECONDS = FIGURE8_TIMELINE_DURATION_SECONDS;
const IMU_CHART_LEFT_INSET = 28;
const IMU_CHART_RIGHT_INSET = 28;
const MIN_CHART_VIEW_SPAN = 0.04;
const IMU_MARKER_SMOOTHING_MS = 64;
const QUEUE_READY_TIME_FORMATTER = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' });

let activeFilter = 'all';
let selectedDuration = DEFAULT_TIMELINE_DURATION;
let activeSort = { key: 'date', direction: 'descending' };
let tableRows = [];
let rowSelectors = [];
let currentPage = 1;
const rowsPerPage = 20;
let tableQuery = '';
let activeAnalysisFilter = 'all';
let activeHealthFilter = 'all';
let activeSummaryGroup = 'all';
let activeFolder = 'all';
let telemetryPosition = 0;
let displayedImuMarkerSample = null;
let imuMarkerLastTimestamp = 0;
let timelineValue = 0;
let imuScrubbing = false;
let imuSelecting = false;
let chartViewStart = 0;
let chartViewEnd = 1;
let chartSelectionStart = null;
let chartSelectionEnd = null;
let selectedUnixStart = 1785520800.125;
let isTimelinePlaying = false;
let playbackFrame = 0;
let playbackLastTime = 0;
let activeSensor = 'angular_velocity_z';
let selectedRecordingRow = null;
let currentDiagnosticRow = null;

function seededNoise(index) {
  const value = Math.sin(index * 12.9898 + 78.233) * 43758.5453;
  return (value - Math.floor(value)) * 2 - 1;
}

function createFallbackImuBundle() {
  const angularVelocityZSamples = Array.from({ length: 920 }, (_, index) => {
    const progress = index / 919;
    const t = index / 22;
    const drift = 0.65 * Math.sin(t * 0.31) + 0.42 * Math.sin(t * 0.83) + 0.2 * Math.cos(t * 1.71);
    const texture = seededNoise(index) * 0.72 + seededNoise(index + 330) * 0.28;
    const impactOne = 2.1 * Math.exp(-Math.pow((index - 286) / 7, 2));
    const impactTwo = -2.7 * Math.exp(-Math.pow((index - 612) / 8, 2));
    const impactThree = 1.8 * Math.exp(-Math.pow((index - 852) / 5, 2));
    const edgeEase = Math.min(1, progress * 10, (1 - progress) * 10);
    return Math.max(-5.55, Math.min(4.75, edgeEase * (drift + texture + impactOne + impactTwo + impactThree)));
  });

  return {
    timestamps: angularVelocityZSamples.map((_, index) => FIGURE8_TIMELINE_DURATION_SECONDS * index / 919),
    angularVelocity: {
      x: angularVelocityZSamples.map((sample, index) => 0.68 * Math.sin(index / 31) + sample * 0.38),
      y: angularVelocityZSamples.map((sample, index) => 0.54 * Math.cos(index / 43) - sample * 0.29),
      z: angularVelocityZSamples,
    },
    linearAcceleration: {
      x: angularVelocityZSamples.map((sample, index) => 0.85 * Math.sin(index / 27) + sample * 0.56),
      y: angularVelocityZSamples.map((sample, index) => 0.6 * Math.cos(index / 35) + sample * 0.42),
      z: angularVelocityZSamples.map((sample, index) => 9.81 + 0.48 * Math.sin(index / 24) + sample * 0.16),
    },
  };
}

let imuBundle = createFallbackImuBundle();

const sensorSignals = {
  angular_velocity_x: { label: 'angular_velocity.x', unit: 'rad/s', min: -2.8, max: 2.8, precision: 4, samples: imuBundle.angularVelocity.x },
  angular_velocity_y: { label: 'angular_velocity.y', unit: 'rad/s', min: -2.8, max: 2.8, precision: 4, samples: imuBundle.angularVelocity.y },
  angular_velocity_z: { label: 'angular_velocity.z', unit: 'rad/s', min: -5.55, max: 5.55, precision: 4, samples: imuBundle.angularVelocity.z },
  linear_acceleration_x: { label: 'linear_acceleration.x', unit: 'm/s²', min: -4, max: 4, precision: 4, samples: imuBundle.linearAcceleration.x },
  linear_acceleration_y: { label: 'linear_acceleration.y', unit: 'm/s²', min: -4, max: 4, precision: 4, samples: imuBundle.linearAcceleration.y },
  linear_acceleration_z: { label: 'linear_acceleration.z', unit: 'm/s²', min: -11.1, max: 11.1, precision: 4, samples: imuBundle.linearAcceleration.z },
};

function setSensorSamples(key, samples) {
  const signal = sensorSignals[key];
  if (!signal || !samples.length) return;

  let dataMin = samples[0];
  let dataMax = samples[0];
  samples.forEach((sample) => {
    dataMin = Math.min(dataMin, sample);
    dataMax = Math.max(dataMax, sample);
  });

  const dataRange = Math.max(0.001, dataMax - dataMin);
  const padding = dataRange * 0.05;
  signal.samples = samples;
  signal.min = dataMin < 0 ? dataMin - padding : 0;
  signal.max = dataMax > 0 ? dataMax + padding : 0;
}

function applyImuBundle(payload) {
  const rows = Array.isArray(payload?.samples)
    ? payload.samples
      .map((row) => row.map(Number))
      .filter((row) => row.length >= 7 && row.every((value) => Number.isFinite(value)))
    : [];
  if (rows.length < 2) return false;

  imuBundle = {
    timestamps: rows.map((row) => row[0] / 1e9),
    angularVelocity: {
      x: rows.map((row) => row[1]),
      y: rows.map((row) => row[2]),
      z: rows.map((row) => row[3]),
    },
    linearAcceleration: {
      x: rows.map((row) => row[4]),
      y: rows.map((row) => row[5]),
      z: rows.map((row) => row[6]),
    },
  };

  Object.entries({
    angular_velocity_x: imuBundle.angularVelocity.x,
    angular_velocity_y: imuBundle.angularVelocity.y,
    angular_velocity_z: imuBundle.angularVelocity.z,
    linear_acceleration_x: imuBundle.linearAcceleration.x,
    linear_acceleration_y: imuBundle.linearAcceleration.y,
    linear_acceleration_z: imuBundle.linearAcceleration.z,
  }).forEach(([key, samples]) => {
    setSensorSamples(key, samples);
  });
  return true;
}

const bundledImuPayload = globalThis.FIGURE8_IMU_BUNDLE;
if (bundledImuPayload && applyImuBundle(bundledImuPayload)) {
  delete globalThis.FIGURE8_IMU_BUNDLE;
  setTimelinePosition(timelineValue);
} else {
  fetch(IMU_BUNDLE_URL)
    .then((response) => response.ok ? response.json() : null)
    .then((payload) => {
      if (payload && applyImuBundle(payload)) setTimelinePosition(timelineValue);
    })
    .catch(() => {});
}

function cssColor(variable, fallback, element = imuChart) {
  const colorSource = element || document.documentElement;
  return getComputedStyle(colorSource).getPropertyValue(variable).trim() || fallback;
}

function formatUnixTime(seconds) {
  return Number(seconds).toFixed(3);
}

function formatElapsedTime(seconds, { compact = false } = {}) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const wholeSeconds = Math.floor(safeSeconds);
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const secondsPart = wholeSeconds % 60;
  const milliseconds = Math.floor((safeSeconds - wholeSeconds) * 1000);
  const clock = hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secondsPart).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(secondsPart).padStart(2, '0')}`;
  return compact ? clock : `${clock}.${String(milliseconds).padStart(3, '0')}`;
}

function valueAtTimelineTime(samples, seconds) {
  const timestamps = imuBundle.timestamps;
  if (!samples.length || !timestamps.length) return 0;
  const timelineSeconds = Math.max(IMU_START_OFFSET_SECONDS, Number(seconds) || 0);
  if (timelineSeconds <= timestamps[0]) return samples[0];
  if (timelineSeconds >= timestamps[timestamps.length - 1]) return samples[samples.length - 1];

  let low = 0;
  let high = timestamps.length - 1;
  while (high - low > 1) {
    const middle = Math.floor((low + high) / 2);
    if (timestamps[middle] <= timelineSeconds) low = middle;
    else high = middle;
  }

  const span = timestamps[high] - timestamps[low] || 1;
  const ratio = (timelineSeconds - timestamps[low]) / span;
  return samples[low] + (samples[high] - samples[low]) * ratio;
}

function setPlaybackState(playing) {
  isTimelinePlaying = playing;
  timelinePlay.classList.toggle('is-playing', playing);
  timelinePlay.setAttribute('aria-pressed', String(playing));
  timelinePlay.setAttribute('aria-label', playing ? 'Pause timeline' : 'Play timeline');
  timelinePlay.title = playing ? 'Pause timeline' : 'Play timeline';
  syncTimelineVideos(playing);
}

function setTimelineVideoPlaybackRate(video) {
  video.playbackRate = Math.max(0.0625, Math.min(16, selectedDuration / TIMELINE_PREVIEW_SECONDS));
}

function setTimelineVideoStatus(state, active) {
  if (!state.status) return;
  state.status.classList.toggle('is-waiting', !active);
  state.status.textContent = active
    ? (isTimelinePlaying ? 'Playing' : 'Ready')
    : `Waiting for ${state.label} to start`;
}

function requestTimelineVideoPlay(video) {
  const playRequest = video.play();
  if (playRequest?.catch) playRequest.catch(() => {});
}

function setTimelineVideoPosition(position, { force = !isTimelinePlaying } = {}) {
  const progress = Math.max(0, Math.min(1, Number(position) || 0));
  const globalTime = selectedDuration * progress;
  timelineVideoStates.forEach((state) => {
    const { video } = state;
    const active = globalTime >= state.offset;
    setTimelineVideoStatus(state, active);
    if (video.readyState < 1) return;

    if (!active) {
      video.pause();
      if (force || video.currentTime > 0.05) video.currentTime = 0;
      return;
    }

    setTimelineVideoPlaybackRate(video);
    const target = Math.max(0, Math.min(video.duration || Number.MAX_SAFE_INTEGER, globalTime - state.offset));
    if (force || Math.abs(video.currentTime - target) > 0.35) video.currentTime = target;
    if (isTimelinePlaying && video.paused) requestTimelineVideoPlay(video);
    if (!isTimelinePlaying) video.pause();
  });
}

function syncTimelineVideos() {
  setTimelineVideoPosition(telemetryPosition, { force: true });
}

timelineVideos.forEach((video) => {
  video.addEventListener('loadedmetadata', () => {
    setTimelineVideoPlaybackRate(video);
    setTimelineVideoPosition(telemetryPosition, { force: true });
  });
});

function stopTimelinePlayback() {
  setPlaybackState(false);
  playbackLastTime = 0;
  if (playbackFrame) window.cancelAnimationFrame(playbackFrame);
  playbackFrame = 0;
  displayedImuMarkerSample = null;
  drawImuChart();
}

function advanceTimeline(timestamp) {
  if (!isTimelinePlaying) return;
  if (!playbackLastTime) playbackLastTime = timestamp;
  const deltaSeconds = Math.min(0.25, (timestamp - playbackLastTime) / 1000);
  playbackLastTime = timestamp;
  const nextValue = timelineValue + (deltaSeconds / TIMELINE_PREVIEW_SECONDS) * 1000;

  if (nextValue >= 1000) {
    globalTimeline.value = '1000';
    setTimelinePosition(1000);
    stopTimelinePlayback();
    announce('Timeline playback complete');
    return;
  }

  globalTimeline.value = String(nextValue);
  setTimelinePosition(nextValue);
  playbackFrame = window.requestAnimationFrame(advanceTimeline);
}

function toggleTimelinePlayback() {
  if (timelinePlay.disabled) return;
  if (isTimelinePlaying) {
    stopTimelinePlayback();
    announce('Timeline paused');
    return;
  }

  if (timelineValue >= 1000) {
    globalTimeline.value = '0';
    setTimelinePosition(0);
  }
  setPlaybackState(true);
  // If playback starts outside the selected zoom window, cut to the matching page immediately.
  setTimelinePosition(timelineValue);
  playbackLastTime = 0;
  playbackFrame = window.requestAnimationFrame(advanceTimeline);
  announce('Timeline playing');
}

function updateChartZoomControls() {
  const disabled = globalTimeline.disabled;
  const viewSpan = chartViewEnd - chartViewStart;
  if (chartReset) chartReset.disabled = disabled || (chartViewStart <= .0001 && chartViewEnd >= .9999);
  if (chartZoomOut) chartZoomOut.disabled = disabled || viewSpan >= .9999;
  if (chartZoomIn) chartZoomIn.disabled = disabled || viewSpan <= MIN_CHART_VIEW_SPAN + .0001;
}

function setChartView(start, end, { announceChange = false } = {}) {
  const numericStart = Number(start);
  const numericEnd = Number(end);
  let nextStart = Math.max(0, Math.min(1, Number.isFinite(numericStart) ? numericStart : 0));
  let nextEnd = Math.max(0, Math.min(1, Number.isFinite(numericEnd) ? numericEnd : 1));
  if (nextEnd < nextStart) [nextStart, nextEnd] = [nextEnd, nextStart];
  if (nextEnd - nextStart < MIN_CHART_VIEW_SPAN) {
    const center = (nextStart + nextEnd) / 2;
    nextStart = center - MIN_CHART_VIEW_SPAN / 2;
    nextEnd = center + MIN_CHART_VIEW_SPAN / 2;
  }
  if (nextStart < 0) {
    nextEnd -= nextStart;
    nextStart = 0;
  }
  if (nextEnd > 1) {
    nextStart -= nextEnd - 1;
    nextEnd = 1;
  }
  chartViewStart = Math.max(0, nextStart);
  chartViewEnd = Math.min(1, nextEnd);
  timelineTotal.textContent = formatUnixTime(selectedUnixStart + selectedDuration * chartViewEnd);
  updateChartZoomControls();
  drawImuChart();
  if (announceChange) {
    const startTime = formatUnixTime(selectedUnixStart + selectedDuration * chartViewStart);
    const endTime = formatUnixTime(selectedUnixStart + selectedDuration * chartViewEnd);
    announce(`Chart zoomed to Unix time ${startTime} through ${endTime}`);
  }
}

function zoomChart(scale) {
  if (globalTimeline.disabled) return;
  if (isTimelinePlaying) stopTimelinePlayback();
  const viewSpan = chartViewEnd - chartViewStart;
  const nextSpan = Math.max(MIN_CHART_VIEW_SPAN, Math.min(1, viewSpan * scale));
  const anchor = telemetryPosition >= chartViewStart && telemetryPosition <= chartViewEnd
    ? telemetryPosition
    : (chartViewStart + chartViewEnd) / 2;
  const anchorRatio = viewSpan > 0 ? (anchor - chartViewStart) / viewSpan : .5;
  let nextStart = anchor - nextSpan * anchorRatio;
  let nextEnd = nextStart + nextSpan;
  if (nextStart < 0) {
    nextEnd -= nextStart;
    nextStart = 0;
  }
  if (nextEnd > 1) {
    nextStart -= nextEnd - 1;
    nextEnd = 1;
  }
  setChartView(nextStart, nextEnd, { announceChange: true });
}

function pageChartViewToPlayback(position) {
  const viewSpan = chartViewEnd - chartViewStart;
  if (viewSpan >= .9999) return;

  const playbackPosition = Math.max(0, Math.min(1, Number(position) || 0));
  let nextStart = chartViewStart;

  if (playbackPosition < chartViewStart) {
    nextStart = playbackPosition;
  } else if (playbackPosition >= chartViewEnd && chartViewEnd < 1) {
    const pagesAhead = Math.max(1, Math.floor((playbackPosition - chartViewStart) / viewSpan));
    nextStart = chartViewStart + pagesAhead * viewSpan;
  } else {
    return;
  }

  nextStart = Math.max(0, Math.min(1 - viewSpan, nextStart));
  chartViewStart = nextStart;
  chartViewEnd = nextStart + viewSpan;
}

function drawImuChart(position = telemetryPosition) {
  if (!imuChart) return;
  telemetryPosition = Math.max(0, Math.min(1, Number(position) || 0));
  const rect = imuChart.getBoundingClientRect();
  if (!rect.width || !rect.height) return;

  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(rect.width * pixelRatio);
  const height = Math.round(rect.height * pixelRatio);
  if (imuChart.width !== width || imuChart.height !== height) {
    imuChart.width = width;
    imuChart.height = height;
  }

  const context = imuChart.getContext('2d');
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);

  const plot = {
    left: IMU_CHART_LEFT_INSET,
    right: rect.width - IMU_CHART_RIGHT_INSET,
    top: 30,
    bottom: rect.height - 30,
  };
  const plotWidth = Math.max(1, plot.right - plot.left);
  const plotHeight = Math.max(1, plot.bottom - plot.top);
  const lineColor = cssColor('--chart-line', '#202224');
  const strongLineColor = cssColor('--chart-line-strong', '#303235');
  const mutedColor = cssColor('--chart-text-dim', '#717277');
  const accentColor = cssColor('--chart-accent', '#f4f4f5');
  const trackerColor = cssColor('--chart-text', '#dfdfdf');
  const panelColor = cssColor('--chart-panel', '#0b0c0d');
  const chartDuration = selectedDuration;
  const viewStartTime = chartDuration * chartViewStart;
  const viewEndTime = chartDuration * chartViewEnd;
  const viewDuration = Math.max(.001, viewEndTime - viewStartTime);
  const currentUnixTime = selectedUnixStart + chartDuration * telemetryPosition;
  const currentElapsedTime = chartDuration * telemetryPosition;

  context.lineWidth = 1;
  context.font = '9px ui-monospace, SFMono-Regular, Menlo, monospace';
  context.textBaseline = 'top';
  context.textAlign = 'left';
  context.fillStyle = accentColor;
  context.globalAlpha = .9;
  context.fillText(formatUnixTime(currentUnixTime), plot.left, plot.bottom + 10);
  context.globalAlpha = 1;
  context.textAlign = 'right';
  context.fillStyle = mutedColor;
  context.fillText(formatUnixTime(selectedUnixStart + viewEndTime), plot.right, plot.bottom + 10);

  const signal = sensorSignals[activeSensor];
  const samples = signal.samples;
  const currentSample = valueAtTimelineTime(samples, chartDuration * telemetryPosition);
  const shouldSmoothMarker = isTimelinePlaying || imuScrubbing;
  const markerTimestamp = performance.now();
  if (!shouldSmoothMarker || displayedImuMarkerSample === null) {
    displayedImuMarkerSample = currentSample;
  } else {
    const elapsed = Math.min(50, Math.max(0, markerTimestamp - imuMarkerLastTimestamp));
    const smoothing = 1 - Math.exp(-elapsed / IMU_MARKER_SMOOTHING_MS);
    displayedImuMarkerSample += (currentSample - displayedImuMarkerSample) * smoothing;
  }
  imuMarkerLastTimestamp = markerTimestamp;
  const timeToX = (time) => plot.left + ((time - viewStartTime) / viewDuration) * plotWidth;
  const visiblePoints = [{ time: viewStartTime, value: valueAtTimelineTime(samples, viewStartTime) }];
  samples.forEach((sample, index) => {
    const sampleTime = imuBundle.timestamps[index] ?? (index / Math.max(1, samples.length - 1)) * chartDuration;
    if (sampleTime > viewStartTime && sampleTime < viewEndTime) visiblePoints.push({ time: sampleTime, value: sample });
  });
  visiblePoints.push({ time: viewEndTime, value: valueAtTimelineTime(samples, viewEndTime) });
  const valueRange = Math.max(.001, (signal.max || 1) - (signal.min || 0));
  const valueToY = (value) => plot.bottom - ((value - signal.min) / valueRange) * plotHeight;
  const horizontalValues = [...new Set([signal.max, 0, signal.min])];
  horizontalValues.forEach((value) => {
    const y = valueToY(value);
    const isZero = value === 0;
    const isBoundary = value === signal.min || value === signal.max;
    const isInteriorZero = isZero && !isBoundary;
    context.beginPath();
    context.moveTo(plot.left, y + 0.5);
    context.lineTo(plot.right, y + 0.5);
    context.strokeStyle = isInteriorZero ? strongLineColor : lineColor;
    context.lineWidth = isInteriorZero ? 1.75 : 1;
    context.stroke();
    if (!isZero) {
      context.fillStyle = mutedColor;
      context.font = '9px ui-monospace, SFMono-Regular, Menlo, monospace';
      context.textAlign = 'left';
      context.textBaseline = 'bottom';
      context.fillText(value.toFixed(2), plot.left, y - 4);
    }
  });
  context.fillStyle = mutedColor;
  context.font = '9px ui-monospace, SFMono-Regular, Menlo, monospace';
  context.textAlign = 'right';
  context.textBaseline = 'bottom';
  context.fillText(`${currentSample.toFixed(signal.precision)} ${signal.unit}`, plot.right, plot.top - 4);

    context.beginPath();
    visiblePoints.forEach((point, index) => {
      const x = timeToX(point.time);
      const y = valueToY(point.value);
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.lineTo(plot.right, plot.bottom);
    context.lineTo(plot.left, plot.bottom);
    context.closePath();
    const fill = context.createLinearGradient(0, plot.top, 0, plot.bottom);
    fill.addColorStop(0, `${accentColor}38`);
    fill.addColorStop(1, `${accentColor}03`);
    context.fillStyle = fill;
    context.fill();

    context.beginPath();
    visiblePoints.forEach((point, index) => {
      const x = timeToX(point.time);
      const y = valueToY(point.value);
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    context.strokeStyle = accentColor;
    context.globalAlpha = 0.88;
    context.lineWidth = 1.05;
    context.lineJoin = 'round';
    context.lineCap = 'round';
    context.stroke();
    context.globalAlpha = 1;

  if (chartSelectionStart !== null && chartSelectionEnd !== null) {
    const selectionStart = Math.max(chartViewStart, Math.min(chartSelectionStart, chartSelectionEnd));
    const selectionEnd = Math.min(chartViewEnd, Math.max(chartSelectionStart, chartSelectionEnd));
    const selectionLeft = plot.left + ((selectionStart - chartViewStart) / (chartViewEnd - chartViewStart)) * plotWidth;
    const selectionRight = plot.left + ((selectionEnd - chartViewStart) / (chartViewEnd - chartViewStart)) * plotWidth;
    context.fillStyle = `${accentColor}18`;
    context.fillRect(selectionLeft, plot.top, Math.max(1, selectionRight - selectionLeft), plotHeight);
    context.strokeStyle = `${accentColor}b8`;
    context.lineWidth = 1;
    [selectionLeft, selectionRight].forEach((x) => {
      context.beginPath();
      context.moveTo(x + .5, plot.top);
      context.lineTo(x + .5, plot.bottom);
      context.stroke();
    });
    context.fillStyle = accentColor;
    context.font = '9px ui-monospace, SFMono-Regular, Menlo, monospace';
    context.textBaseline = 'top';
    const selectionStartLabel = formatUnixTime(selectedUnixStart + selectedDuration * selectionStart);
    const selectionEndLabel = formatUnixTime(selectedUnixStart + selectedDuration * selectionEnd);
    const selectionStartLabelWidth = context.measureText(selectionStartLabel).width;
    const selectionEndLabelWidth = context.measureText(selectionEndLabel).width;
    const selectionStartX = Math.max(plot.left + 5, Math.min(plot.right - selectionStartLabelWidth - 5, selectionLeft + 5));
    const selectionEndX = Math.max(plot.left + selectionEndLabelWidth + 5, Math.min(plot.right - 5, selectionRight - 5));

    context.fillStyle = trackerColor;
    context.textAlign = 'left';
    context.fillText(selectionStartLabel, selectionStartX, plot.top + 6);

    context.fillStyle = trackerColor;
    context.textAlign = 'right';
    context.fillText(selectionEndLabel, selectionEndX, plot.bottom - 17);
  }

  if (telemetryPosition >= chartViewStart && telemetryPosition <= chartViewEnd) {
    const playheadX = plot.left + ((telemetryPosition - chartViewStart) / (chartViewEnd - chartViewStart)) * plotWidth;
    const playheadCenterX = playheadX;

    context.save();
    context.lineCap = 'round';

    // Keep every playhead element on the same pixel axis so the handle and line connect cleanly.
    context.beginPath();
    context.moveTo(playheadCenterX, plot.top + 1);
    context.lineTo(playheadCenterX, plot.bottom);
    context.strokeStyle = `${accentColor}d6`;
    context.lineWidth = 1;
    context.stroke();

    // The triangular top handle is the grab point and primary playhead cue.
    context.beginPath();
    context.moveTo(playheadCenterX - 4, plot.top);
    context.lineTo(playheadCenterX + 4, plot.top);
    context.lineTo(playheadCenterX, plot.top + 6);
    context.closePath();
    context.fillStyle = accentColor;
    context.fill();

    if (!isTimelinePlaying || imuScrubbing) {
      context.beginPath();
      context.arc(playheadCenterX, valueToY(displayedImuMarkerSample), 3.5, 0, Math.PI * 2);
      context.fillStyle = panelColor;
      context.fill();
      context.lineWidth = 1.5;
      context.strokeStyle = trackerColor;
      context.stroke();
    }
    context.restore();
  }

  imuChart.setAttribute('aria-valuenow', String(Math.round(telemetryPosition * 1000)));
  imuChart.setAttribute('aria-valuetext', `${signal.label}, Unix time ${formatUnixTime(currentUnixTime)}, ${formatElapsedTime(currentElapsedTime)} elapsed, ${currentSample.toFixed(signal.precision)} ${signal.unit}`);
}

function closeSensorPicker({ returnFocus = false } = {}) {
  if (sensorPickerMenu.hidden && sensorPickerTrigger.getAttribute('aria-expanded') !== 'true') return;
  setTransientPanelOpen(sensorPickerMenu, false);
  sensorPickerTrigger.setAttribute('aria-expanded', 'false');
  if (returnFocus) sensorPickerTrigger.focus();
}

function selectSensor(sensor) {
  if (!sensorSignals[sensor]) return;
  activeSensor = sensor;
  displayedImuMarkerSample = null;
  const signal = sensorSignals[sensor];
  selectedSensorLabel.textContent = signal.label;
  sensorOptions.forEach((option) => {
    const selected = option.dataset.sensor === sensor;
    option.classList.toggle('is-selected', selected);
    option.setAttribute('aria-checked', String(selected));
  });
  drawImuChart();
  closeSensorPicker();
  announce(`${signal.label} shown on timeline`);
}

timelinePlay.addEventListener('click', toggleTimelinePlayback);
sensorPickerTrigger.addEventListener('click', () => {
  const willOpen = sensorPickerTrigger.getAttribute('aria-expanded') !== 'true';
  setTransientPanelOpen(sensorPickerMenu, willOpen);
  sensorPickerTrigger.setAttribute('aria-expanded', String(willOpen));
});
sensorOptions.forEach((option) => option.addEventListener('click', () => selectSensor(option.dataset.sensor)));

function chartPositionFromClientX(clientX) {
  const rect = imuChart.getBoundingClientRect();
  const plotLeft = rect.left + IMU_CHART_LEFT_INSET;
  const plotRight = rect.right - IMU_CHART_RIGHT_INSET;
  const localPosition = Math.max(0, Math.min(1, (clientX - plotLeft) / Math.max(1, plotRight - plotLeft)));
  return chartViewStart + localPosition * (chartViewEnd - chartViewStart);
}

function scrubTelemetry(clientX) {
  const position = chartPositionFromClientX(clientX);
  setTimelinePosition(position * 1000);
}

imuChart.addEventListener('pointerdown', (event) => {
  if (globalTimeline.disabled) return;
  if (isTimelinePlaying) stopTimelinePlayback();
  imuChart.setPointerCapture(event.pointerId);
  imuChart.focus({ preventScroll: true });
  if (event.shiftKey) {
    imuSelecting = true;
    chartSelectionStart = chartPositionFromClientX(event.clientX);
    chartSelectionEnd = chartSelectionStart;
    imuChart.classList.add('is-selecting');
    drawImuChart();
    return;
  }
  imuScrubbing = true;
  imuChart.classList.add('is-scrubbing');
  scrubTelemetry(event.clientX);
});

imuChart.addEventListener('pointermove', (event) => {
  if (imuSelecting) {
    chartSelectionEnd = chartPositionFromClientX(event.clientX);
    drawImuChart();
    return;
  }
  if (imuScrubbing) scrubTelemetry(event.clientX);
});

function stopTelemetryInteraction(event, { cancelled = false } = {}) {
  if (!imuScrubbing && !imuSelecting) return;
  if (imuChart.hasPointerCapture(event.pointerId)) imuChart.releasePointerCapture(event.pointerId);
  if (imuSelecting) {
    const selectionStart = chartSelectionStart;
    const selectionEnd = chartSelectionEnd;
    const rect = imuChart.getBoundingClientRect();
    const plotWidth = rect.width - IMU_CHART_LEFT_INSET - IMU_CHART_RIGHT_INSET;
    const minimumSpan = (chartViewEnd - chartViewStart) * (8 / Math.max(1, plotWidth));
    imuSelecting = false;
    imuChart.classList.remove('is-selecting');
    if (!event.shiftKey) imuChart.classList.remove('is-shift-ready');
    chartSelectionStart = null;
    chartSelectionEnd = null;
    if (!cancelled && Math.abs(selectionEnd - selectionStart) >= minimumSpan) {
      setChartView(selectionStart, selectionEnd, { announceChange: true });
    } else {
      drawImuChart();
    }
    return;
  }
  imuScrubbing = false;
  imuChart.classList.remove('is-scrubbing');
  displayedImuMarkerSample = null;
  drawImuChart();
  announce(`Timeline set to ${timelineCurrent.textContent}`);
}

imuChart.addEventListener('pointerup', (event) => stopTelemetryInteraction(event));
imuChart.addEventListener('pointercancel', (event) => stopTelemetryInteraction(event, { cancelled: true }));
chartReset?.addEventListener('click', () => {
  if (isTimelinePlaying) stopTimelinePlayback();
  setChartView(0, 1, { announceChange: true });
});
chartZoomOut?.addEventListener('click', () => zoomChart(1.6));
chartZoomIn?.addEventListener('click', () => zoomChart(.625));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Shift' && !analyzerView.hidden && !globalTimeline.disabled) imuChart.classList.add('is-shift-ready');
});
document.addEventListener('keyup', (event) => {
  if (event.key === 'Shift' && !imuSelecting) imuChart.classList.remove('is-shift-ready');
});
window.addEventListener('blur', () => {
  if (!imuSelecting) imuChart.classList.remove('is-shift-ready');
});
imuChart.addEventListener('wheel', (event) => {
  if (globalTimeline.disabled) return;
  event.preventDefault();
  if (isTimelinePlaying) stopTimelinePlayback();
  const direction = Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
  const nextValue = timelineValue + Math.sign(direction) * Math.max(5, Math.min(40, Math.abs(direction) * 0.2));
  setTimelinePosition(nextValue);
}, { passive: false });

function handleTimelineKeyboard(event) {
  if (globalTimeline.disabled) return;
  const steps = { ArrowLeft: -10, ArrowDown: -10, ArrowRight: 10, ArrowUp: 10, PageDown: -100, PageUp: 100 };
  if (event.key === '+' || event.key === '=') {
    event.preventDefault();
    zoomChart(.625);
    return;
  }
  if (event.key === '-' || event.key === '_') {
    event.preventDefault();
    zoomChart(1.6);
    return;
  }
  if (event.key === ' ' || event.key.toLocaleLowerCase() === 'k') {
    event.preventDefault();
    toggleTimelinePlayback();
    return;
  }
  let nextValue = timelineValue;
  if (event.key === 'Home') nextValue = 0;
  else if (event.key === 'End') nextValue = 1000;
  else if (event.key in steps) nextValue += steps[event.key];
  else return;
  event.preventDefault();
  if (isTimelinePlaying) stopTimelinePlayback();
  setTimelinePosition(nextValue);
}

imuChart.addEventListener('keydown', handleTimelineKeyboard);

document.addEventListener('keydown', (event) => {
  const target = event.target;
  const isEditing = target instanceof HTMLElement && target.matches('input, textarea, select, button, [contenteditable="true"]');
  if (analyzerView.hidden || isEditing || target === imuChart || !sensorPickerMenu.hidden) return;
  handleTimelineKeyboard(event);
});

if (imuChart && 'ResizeObserver' in window) {
  new ResizeObserver(() => drawImuChart()).observe(imuChart);
} else {
  window.addEventListener('resize', () => drawImuChart());
}

const sortRanks = {
  status: { ready: 1, processing: 2, queued: 3, 'not-planned': 4, failed: 5 },
  health: { readable: 1, unreadable: 2 },
};

const recordingNames = [
  'Figure 8', 'Robot Testing', 'Lunar Rover Terrain Validation — Sector B', 'Warehouse Navigation — Night Shift',
  'Docking Trial', 'Autonomy Regression 042', 'Tallinn Snow Route', 'Field Test — East Perimeter',
  'Manipulator Calibration', 'Perception Benchmark 017', 'Campus Loop — Morning', 'Obstacle Course Alpha',
  'Loading Bay Mapping', 'Coastal Survey 006', 'Indoor Localization Test', 'Highway Merge Simulation',
  'Forklift Interaction Study', 'Stairwell Mapping Run', 'Visual SLAM Benchmark', 'Rainy Day Drive',
  'Payload Delivery Trial', 'Charging Station Alignment', 'Construction Site Patrol', 'Stereo Camera Validation',
  'Emergency Stop Validation', 'Lidar Occlusion Test', 'Crosswalk Detection 021', 'Agriculture Row Following',
  'Tunnel Navigation', 'Night Vision Calibration', 'Dynamic Obstacle Set', 'Robot Arm Reachability',
  'Precision Docking 014', 'Mapping Sprint — West', 'Multi-Robot Handoff', 'Curb Detection Trial',
  'GPS Denied Route', 'Delivery Route 118', 'Sensor Fusion Baseline', 'Warehouse Aisle Recovery',
  'Terrain Grade Assessment', 'Object Tracking Review', 'Sidewalk Survey — North', 'Platform Lift Test',
  'Roundabout Scenario', 'Autonomy Stress Test', 'Battery Endurance Cycle', 'Urban Canyon Recording',
  'Pallet Pickup Sequence', 'Localization Drift Check', 'Loading Dock Sweep', 'Pedestrian Yield Test',
  'Camera Exposure Sweep', 'Navigation Recovery 005', 'Parking Lot Mapping', 'Rough Terrain Endurance',
  'Intersection Takeover', 'Signal Timing Capture', 'Final Acceptance Run', 'Depot Return Sequence',
];

function formatRecordingDate(date) {
  const day = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }).format(date);
  return `<time datetime="${date.toISOString()}"><span>${day}</span><span>${time}</span></time>`;
}

function recordingFilename(name, date) {
  const datePrefix = date.toISOString().slice(0, 10).replaceAll('-', '_');
  const stem = name
    .toLocaleLowerCase()
    .replaceAll('—', ' ')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return `${datePrefix}_${stem}`;
}

function formatRecordingLength(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}m ${String(seconds).padStart(2, '0')}s`;
}

function statusMarkup(status, index) {
  const labels = { ready: 'Ready', processing: 'Processing', queued: 'Queued', 'not-planned': 'Not planned', failed: 'Failed' };
  const processingSteps = ['Front preview', 'Top-down view', 'IMU stream'];
  const activeStep = processingSteps[index % processingSteps.length];
  const icons = { ready: 'icon-status-check', processing: 'icon-analysis-processing', queued: 'icon-queue', 'not-planned': 'icon-clock', failed: 'icon-status-alert' };
  const details = {
    ready: '<span>Front camera · processed</span><span>Top-down view · processed</span><span>IMU stream · processed</span>',
    processing: `<span>${activeStep} · processing now</span><span>Other sources are ready or queued</span>`,
    queued: '<span>Waiting to prepare front camera, top-down view and IMU stream</span>',
    'not-planned': '<span>Analysis has not been scheduled for this recording</span><span>It will remain outside the worker queue until selected</span>',
    failed: `<span>${activeStep} · failed</span><span>Open processing details for the error log</span>`,
  };
  const ariaLabel = status === 'processing' ? `Processing: ${activeStep} is processing now` : labels[status];
  const tooltipId = `analysis-status-${index}-tooltip`;
  return `<span class="status-indicator table-status--${status}" tabindex="0" aria-label="${ariaLabel}" aria-describedby="${tooltipId}"><span class="status-glyph" aria-hidden="true"><svg><use href="#${icons[status]}" /></svg></span><span class="status-label">${labels[status]}</span><span class="status-tooltip" id="${tooltipId}" role="tooltip"><strong>${labels[status]}</strong>${details[status]}</span></span>`;
}

function healthMarkup(health, index) {
  const label = health === 'readable' ? 'Readable' : 'Damaged';
  const detail = health === 'readable'
    ? '<span>Source file and message index validated</span>'
    : `<span>${index % 2 ? 'Metadata index is incomplete' : 'Two source chunks could not be read'}</span><span>Open source details for diagnostics</span>`;
  const icon = health === 'readable' ? 'icon-status-check' : 'icon-status-x';
  const tooltipId = `ros-health-${index}-tooltip`;
  return `<span class="status-indicator table-health--${health}" tabindex="0" aria-label="${label}" aria-describedby="${tooltipId}"><span class="status-glyph" aria-hidden="true"><svg><use href="#${icon}" /></svg></span><span class="status-label">${label}</span><span class="status-tooltip" id="${tooltipId}" role="tooltip"><strong>${label}</strong>${detail}</span></span>`;
}

const recordingThumbnails = [
  'assets/previews/recording-01.png',
  'assets/previews/recording-02.png',
  'assets/previews/recording-03.png',
  'assets/previews/recording-04.png',
  'assets/previews/recording-05.png',
];

function thumbnailMarkup(recordingName) {
  const thumbnailIndex = [...recordingName].reduce(
    (hash, character) => ((hash * 31) + character.codePointAt(0)) >>> 0,
    7,
  ) % recordingThumbnails.length;
  return `<span class="recording-thumbnail" aria-hidden="true"><img src="${recordingThumbnails[thumbnailIndex]}" alt="" loading="lazy" /></span>`;
}

function buildMockRecordings() {
  const statusCycle = ['ready', 'ready', 'processing', 'ready', 'failed', 'ready', 'queued', 'ready', 'not-planned', 'processing'];
  recordingsTableBody.innerHTML = '';
  tableRows = recordingNames.map((name, index) => {
    const status = statusCycle[index % statusCycle.length];
    const health = index % 20 === 9 ? 'unreadable' : 'readable';
    const size = index === 0 ? 10.1 : Number((1.2 + ((index * 1.37) % 9.1)).toFixed(1));
    const length = index === 0 ? Math.round(FIGURE8_TIMELINE_DURATION_SECONDS) : 300 + ((index * 137) % 2600);
    const folder = index < 18
      ? '2026-july-10'
      : index < 39
        ? '2026-july-25'
        : index < 53
          ? '2026-july-31'
          : index < 56
            ? '2025-july-10'
            : '2025-july-25';
    const is2026 = folder.startsWith('2026');
    const folderIndex = is2026 ? index : index - 53;
    const folderDay = Number(folder.slice(-2));
    const dateObject = new Date(Date.UTC(
      is2026 ? 2026 : 2025,
      6,
      folderDay,
      15 - ((folderIndex * 3) % 12),
      (folderIndex * 7) % 60,
    ));
    const date = dateObject.toISOString();
    const row = document.createElement('tr');

    row.dataset.name = name;
    row.dataset.date = date;
    row.dataset.status = status;
    row.dataset.health = health;
    row.dataset.folder = folder;
    row.dataset.size = String(size);
    row.dataset.length = String(length);
    const filename = recordingFilename(name, dateObject);
    row.dataset.filename = filename;
    row.innerHTML = `<td class="selection-column"><input class="row-select" type="checkbox" aria-label="Select ${name}" /></td><td><div class="recording-cell-layout">${thumbnailMarkup(name)}<span class="recording-copy"><a class="recording-link" href="#" data-open-recording>${name}</a><span class="cell-sublabel">${filename}</span></span></div></td><td class="date-cell">${formatRecordingDate(dateObject)}</td><td>${formatRecordingLength(length)}</td><td>${size.toFixed(1)} GB</td><td class="status-cell">${healthMarkup(health, index)}</td><td class="status-cell">${statusMarkup(status, index)}</td>`;
    recordingsTableBody.append(row);
    return row;
  });
  rowSelectors = [...document.querySelectorAll('.row-select')];
}

function showView(view) {
  const normalizedView = view === 'recordings' ? 'analyzer' : view === 'home' ? 'archive' : view;
  const previousView = activeAppView;
  activeAppView = normalizedView;
  const isAnalyzer = normalizedView === 'analyzer';
  const isProgression = normalizedView === 'progression';
  const isExperiments = normalizedView === 'experiments';
  const activeView = isAnalyzer ? analyzerView : isProgression ? progressionView : isExperiments ? experimentsView : homeView;

  const applyView = () => {
    toolButtons.forEach((button) => {
      const active = button.dataset.view === normalizedView;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    // Re-selecting the active tab should not enter the workspace swap state.
    // That state intentionally disables descendant transitions and made the
    // archive button's folder toggle close instantly.
    if (previousView !== normalizedView) setWorkspaceView(activeView);
    syncFolderReveal();
  };

  const shouldAnimateIndicator = previousView !== normalizedView && !reduceMotion.matches && toolListIndicator && typeof toolListIndicator.animate === 'function';
  const previousIndicatorTransform = shouldAnimateIndicator ? getComputedStyle(toolListIndicator).transform : '';
  toolIndicatorAnimation?.cancel();
  if (shouldAnimateIndicator) toolListIndicator.style.transition = 'none';
  applyView();

  if (shouldAnimateIndicator) {
    const nextIndicatorTransform = getComputedStyle(toolListIndicator).transform;
    toolListIndicator.style.removeProperty('transition');
    toolIndicatorAnimation = toolListIndicator.animate([
      { transform: previousIndicatorTransform },
      { transform: nextIndicatorTransform }
    ], {
      duration: 280,
      easing: 'cubic-bezier(.16, 1, .3, 1)'
    });
    toolIndicatorAnimation.finished.then(() => { toolIndicatorAnimation = null; }).catch(() => {});
  }
}

function announce(message) {
  liveRegion.textContent = '';
  window.requestAnimationFrame(() => {
    liveRegion.textContent = message;
  });
}

function updateSelectionState() {
  const selectedRows = rowSelectors.filter((checkbox) => checkbox.checked);
  const selectedTotal = selectedRows.length;
  const visibleSelectors = tableRows
    .filter((row) => !row.hidden)
    .map((row) => row.querySelector('.row-select'));
  const visibleSelectedTotal = visibleSelectors.filter((checkbox) => checkbox.checked).length;
  tableRows.forEach((row) => {
    row.classList.toggle('is-selected', row.querySelector('.row-select').checked);
  });

  selectAllRecordings.checked = visibleSelectors.length > 0 && visibleSelectedTotal === visibleSelectors.length;
  selectAllRecordings.indeterminate = visibleSelectedTotal > 0 && visibleSelectedTotal < visibleSelectors.length;
  selectedCount.textContent = String(selectedTotal);
  selectionContext.hidden = selectedTotal === 0;
  setPrepareSelectedVisible(selectedTotal > 0);
  bulkActionButtons.forEach((button) => {
    button.disabled = selectedTotal === 0;
  });
}

function setPrepareSelectedVisible(visible) {
  document.querySelector('.table-filter-bar').classList.toggle('has-selection', visible);
  prepareSelectedButton.setAttribute('aria-hidden', String(!visible));
  prepareSelectedButton.tabIndex = visible ? 0 : -1;
}

function clearTableSelection() {
  rowSelectors.forEach((checkbox) => {
    checkbox.checked = false;
  });
  updateSelectionState();
}

function filteredTableRows() {
  return tableRows.filter((row) => {
    const matchesSearch = row.dataset.name.toLocaleLowerCase().includes(tableQuery);
    const matchesAnalysis = activeAnalysisFilter === 'all' || row.dataset.status === activeAnalysisFilter;
    const matchesHealth = activeHealthFilter === 'all' || row.dataset.health === activeHealthFilter;
    const matchesSummary = activeSummaryGroup === 'all'
      || (activeSummaryGroup === 'ready' && row.dataset.status === 'ready' && row.dataset.health === 'readable')
      || (activeSummaryGroup === 'active' && row.dataset.status === 'processing')
      || (activeSummaryGroup === 'queue' && row.dataset.status === 'queued')
      || (activeSummaryGroup === 'attention' && (row.dataset.status === 'failed' || row.dataset.health === 'unreadable'));
    const matchesFolder = activeFolder === 'all'
      || row.dataset.folder === activeFolder
      || row.dataset.folder.startsWith(`${activeFolder}-`);
    return matchesSearch && matchesAnalysis && matchesHealth && matchesSummary && matchesFolder;
  });
}

function renderTablePage() {
  const matchingRows = filteredTableRows();
  const totalPages = Math.max(1, Math.ceil(matchingRows.length / rowsPerPage));
  currentPage = Math.min(currentPage, totalPages);
  const start = (currentPage - 1) * rowsPerPage;
  const end = start + rowsPerPage;
  const visibleRows = matchingRows.slice(start, end);
  const pageRows = new Set(visibleRows);

  tableRows.forEach((row) => {
    row.hidden = !pageRows.has(row);
    row.classList.toggle('is-first-visible', row === visibleRows[0]);
    row.classList.toggle('is-last-visible', row === visibleRows[visibleRows.length - 1]);
    recordingsTableBody.append(row);
  });

  pageStatus.textContent = `Page ${currentPage} of ${totalPages}`;
  tableEmptyState.hidden = matchingRows.length !== 0;
  updateSelectionState();
  previousPage.disabled = currentPage === 1;
  nextPage.disabled = currentPage === totalPages;
  pageButtons.innerHTML = Array.from({ length: totalPages }, (_, index) => {
    const page = index + 1;
    return `<button type="button" class="${page === currentPage ? 'is-active' : ''}" aria-label="Page ${page}" aria-current="${page === currentPage ? 'page' : 'false'}" data-page="${page}">${page}</button>`;
  }).join('');
}

function sortRecordings(key) {
  const direction = activeSort.key === key && activeSort.direction === 'ascending' ? 'descending' : 'ascending';
  activeSort = { key, direction };

  const sortedRows = [...tableRows].sort((first, second) => {
    const firstValue = sortRanks[key] ? sortRanks[key][first.dataset[key]] : first.dataset[key];
    const secondValue = sortRanks[key] ? sortRanks[key][second.dataset[key]] : second.dataset[key];
    const numericSort = ['size', 'length'].includes(key);
    const comparison = numericSort
      ? Number(firstValue) - Number(secondValue)
      : String(firstValue).localeCompare(String(secondValue));
    return direction === 'ascending' ? comparison : -comparison;
  });

  tableRows = sortedRows;
  sortButtons.forEach((button) => {
    button.setAttribute('aria-sort', button.dataset.sort === key ? direction : 'none');
  });
  currentPage = 1;
  renderTablePage();
  announce(`Recordings sorted by ${key}, ${direction}`);
}

function setTimelinePosition(value) {
  const position = Math.max(0, Math.min(1000, Number(value) || 0));
  timelineValue = position;
  globalTimeline.value = String(position);
  const normalizedPosition = position / 1000;
  if (isTimelinePlaying) pageChartViewToPlayback(normalizedPosition);
  const elapsedSeconds = selectedDuration * normalizedPosition;
  const unixCurrent = selectedUnixStart + elapsedSeconds;

  timelineCurrent.textContent = formatUnixTime(unixCurrent);
  timelineTotal.textContent = formatUnixTime(selectedUnixStart + selectedDuration * chartViewEnd);
  timelinePosition.removeAttribute('title');
  timelinePosition.setAttribute('aria-label', `Unix time ${formatUnixTime(unixCurrent)}; visible range ends ${formatUnixTime(selectedUnixStart + selectedDuration * chartViewEnd)}`);
  globalTimeline.setAttribute('aria-valuetext', `Unix time ${formatUnixTime(unixCurrent)}, ${formatElapsedTime(elapsedSeconds)} elapsed of ${formatElapsedTime(selectedDuration)}`);
  drawImuChart(normalizedPosition);
  setTimelineVideoPosition(normalizedPosition);
}

function unixStartForBag(row) {
  const recordingDate = row.querySelector('time')?.getAttribute('datetime') || '2026-07-31';
  const nameOffset = [...row.dataset.name].reduce((total, character) => total + character.codePointAt(0), 0) % 21600;
  return Date.parse(`${recordingDate.slice(0, 10)}T08:00:00Z`) / 1000 + nameOffset + 0.125;
}

function formatAnalyzerRecorded(row) {
  const date = new Date(row.dataset.date);
  const day = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
  const time = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }).format(date);
  return `${day} · ${time}`;
}

function setAnalyzerRecording(row, { announceChange = false } = {}) {
  if (!row) return;
  stopTimelinePlayback();
  selectedRecordingRow = row;
  const name = row.dataset.name;
  selectedDuration = name === 'Figure 8'
    ? FIGURE8_TIMELINE_DURATION_SECONDS
    : Number(row.dataset.length) || DEFAULT_TIMELINE_DURATION;
  selectedUnixStart = unixStartForBag(row);
  globalTimeline.value = '0';
  globalTimeline.disabled = false;
  timelinePlay.disabled = false;
  chartViewStart = 0;
  chartViewEnd = 1;
  chartSelectionStart = null;
  chartSelectionEnd = null;
  updateChartZoomControls();
  setTimelinePosition(0);

  if (announceChange) {
    announce(`${name} opened in Analyzer. Shared timeline ready.`);
  }
}

function resetWorkspace({ announceChange = false } = {}) {
  const fallback = selectedRecordingRow || tableRows.find((row) => row.dataset.name === 'Figure 8') || tableRows[0];
  setAnalyzerRecording(fallback, { announceChange });
}

function setRecordingDetailsCollapsed(collapsed, { returnFocus = false } = {}) {
  const transitionVersion = ++recordingDetailsTransitionVersion;
  const detailsBefore = recordingDetailsPanel.getBoundingClientRect();
  const telemetryBefore = analyzerTelemetryPanel.getBoundingClientRect();
  const layoutWasCollapsed = analyzerView.classList.contains('is-details-collapsed');

  recordingDetailsLayoutAnimations.forEach((animation) => animation.cancel());
  recordingDetailsLayoutAnimations = [];
  recordingDetailsPanel.style.removeProperty('height');
  analyzerTelemetryPanel.style.removeProperty('width');

  // Measure the destination without letting the browser paint that layout early.
  analyzerView.classList.toggle('is-details-collapsed', collapsed);
  const detailsAfter = recordingDetailsPanel.getBoundingClientRect();
  const telemetryAfter = analyzerTelemetryPanel.getBoundingClientRect();
  analyzerView.classList.toggle('is-details-collapsed', layoutWasCollapsed);

  collapseRecordingDetails.setAttribute('aria-expanded', String(!collapsed));
  collapseRecordingDetails.setAttribute('aria-label', collapsed ? 'Expand recording details' : 'Compact recording details');
  collapseRecordingDetails.title = collapsed ? 'Expand recording details' : 'Compact recording details';

  recordingDetailsPanel.style.height = `${detailsBefore.height}px`;
  analyzerTelemetryPanel.style.width = `${telemetryBefore.width}px`;

  const finishLayout = () => window.requestAnimationFrame(() => {
    if (recordingDetailsTransitionVersion !== transitionVersion) return;
    analyzerView.classList.toggle('is-details-collapsed', collapsed);
    recordingDetailsPanel.style.removeProperty('height');
    analyzerTelemetryPanel.style.removeProperty('width');
    drawImuChart();
    if (returnFocus) collapseRecordingDetails.focus();
  });

  if (reduceMotion.matches || typeof recordingDetailsPanel.animate !== 'function') {
    finishLayout();
  } else {
    const runPhase = async (element, property, from, to, duration) => {
      const animation = element.animate([
        { [property]: `${from}px` },
        { [property]: `${to}px` }
      ], {
        duration,
        easing: 'cubic-bezier(.16, 1, .3, 1)',
        fill: 'forwards'
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
        // Close details completely, switch layout, then let the graph travel right.
        if (!await runPhase(recordingDetailsPanel, 'height', detailsBefore.height, detailsAfter.height, RECORDING_DETAILS_RESIZE_DURATION)) return;
        analyzerView.classList.add('is-details-collapsed');
        if (!await runPhase(analyzerTelemetryPanel, 'width', telemetryBefore.width, telemetryAfter.width, RECORDING_DETAILS_GRAPH_DURATION)) return;
      } else {
        // Exact reverse: graph travels left first, then details opens downward.
        if (!await runPhase(analyzerTelemetryPanel, 'width', telemetryBefore.width, telemetryAfter.width, RECORDING_DETAILS_GRAPH_DURATION)) return;
        analyzerView.classList.remove('is-details-collapsed');
        if (!await runPhase(recordingDetailsPanel, 'height', detailsBefore.height, detailsAfter.height, RECORDING_DETAILS_RESIZE_DURATION)) return;
      }
      finishLayout();
    };

    runTransition();
  }

  announce(collapsed ? 'Recording details compacted' : 'Recording details expanded');
}

function closeFilterMenu({ returnFocus = false } = {}) {
  setTransientPanelOpen(filterMenu, false);
  filterButton.setAttribute('aria-expanded', 'false');

  if (returnFocus) {
    filterButton.focus();
  }
}

function openFilterMenu() {
  setTransientPanelOpen(filterMenu, true);
  filterButton.setAttribute('aria-expanded', 'true');
}

function applyFilters() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  let shown = 0;

  bagRows.forEach((row) => {
    const matchesSearch = row.dataset.name.toLocaleLowerCase().includes(query);
    const matchesStatus = activeFilter === 'all' || row.dataset.status === activeFilter;
    const isVisible = matchesSearch && matchesStatus;

    row.closest('li').hidden = !isVisible;
    shown += Number(isVisible);
  });

  visibleCount.textContent = `${shown} shown`;
  bagList.hidden = shown === 0;
  emptyState.hidden = shown !== 0;
}

buildMockRecordings();
tableRows.sort((first, second) => second.dataset.date.localeCompare(first.dataset.date));
renderTablePage();
bagRows.forEach((row) => {
  row.addEventListener('click', () => {
    const matchingRecording = tableRows.find((tableRow) => tableRow.dataset.name === row.dataset.name);
    if (matchingRecording) setAnalyzerRecording(matchingRecording, { announceChange: true });
  });
});

sortButtons.forEach((button) => {
  button.addEventListener('click', () => sortRecordings(button.dataset.sort));
});

rowSelectors.forEach((checkbox) => {
  checkbox.addEventListener('change', () => {
    updateSelectionState();
  });
  checkbox.addEventListener('click', (event) => event.stopPropagation());
});

function openRecording(row) {
  setAnalyzerRecording(row);
  showView('analyzer');
  announce(row.dataset.name === 'Figure 8'
    ? `${row.dataset.name} opened in Analyzer. Synchronized evidence ready.`
    : `${row.dataset.name} opened in Analyzer. Bundled synchronized evidence is unavailable in this static build.`);
}

tableRows.forEach((row) => {
  row.addEventListener('click', (event) => {
    if (event.target.closest('input, button, .row-menu, .status-indicator')) return;
    event.preventDefault();
    openRecording(row);
  });
});

selectAllRecordings.addEventListener('change', () => {
  const shouldSelect = selectAllRecordings.checked;
  tableRows.filter((row) => !row.hidden).forEach((row) => {
    row.querySelector('.row-select').checked = shouldSelect;
  });
  updateSelectionState();
  announce(shouldSelect ? 'All visible recordings selected' : 'Visible recording selection cleared');
});

previousPage.addEventListener('click', () => {
  currentPage -= 1;
  renderTablePageWithHeightTransition();
});

nextPage.addEventListener('click', () => {
  currentPage += 1;
  renderTablePageWithHeightTransition();
});

pageButtons.addEventListener('click', (event) => {
  const pageButton = event.target.closest('[data-page]');
  if (!pageButton) return;

  const nextPageNumber = Number(pageButton.dataset.page);
  currentPage = nextPageNumber;
  renderTablePageWithHeightTransition();
});

tableSearch.addEventListener('input', () => {
  tableQuery = tableSearch.value.trim().toLocaleLowerCase();
  currentPage = 1;
  renderTablePage();
});

let clearFilterAnimation;
let clearFilterShouldShow = false;
function setClearFilterVisible(visible) {
  if (visible === clearFilterShouldShow) return;
  clearFilterShouldShow = visible;
  clearFilterAnimation?.cancel();

  if (visible) clearFilterMenu.hidden = false;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || typeof clearFilterMenu.animate !== 'function') {
    clearFilterMenu.hidden = !visible;
    return;
  }

  const controlWidth = clearFilterMenu.scrollWidth;
  const animation = clearFilterMenu.animate(visible ? [
    { width: '0px', opacity: 0, paddingInline: '0px' },
    { width: `${controlWidth}px`, opacity: 1, paddingInline: '7px' }
  ] : [
    { width: `${controlWidth}px`, opacity: 1, paddingInline: '7px' },
    { width: '0px', opacity: 0, paddingInline: '0px' }
  ], {
    duration: visible ? 180 : 140,
    easing: 'cubic-bezier(.22, 1, .36, 1)'
  });
  clearFilterAnimation = animation;
  animation.addEventListener('finish', () => {
    if (!clearFilterShouldShow) clearFilterMenu.hidden = true;
    if (clearFilterAnimation === animation) clearFilterAnimation = null;
  }, { once: true });
  animation.addEventListener('cancel', () => {
    if (clearFilterAnimation === animation) clearFilterAnimation = null;
  }, { once: true });
}

function syncSummaryButtons() {
  summaryGroupButtons.forEach((button) => {
    const active = button.dataset.summaryGroup === activeSummaryGroup;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  const count = Number(activeAnalysisFilter !== 'all') + Number(activeHealthFilter !== 'all');
  setClearFilterVisible(count > 0);
}

function syncSummaryIndicator({ animate = true } = {}) {
  const activeButton = summaryGroupButtons.find((button) => button.classList.contains('is-active'));
  const targetButton = activeButton;
  if (!targetButton || !statusStripIndicator) return;
  const stripRect = statusStrip.getBoundingClientRect();
  const targetRect = targetButton.getBoundingClientRect();
  const indicatorLeft = targetRect.left - stripRect.left + statusStrip.scrollLeft;
  statusStripIndicator.classList.toggle('is-positioning', !animate);
  statusStripIndicator.style.width = `${targetRect.width}px`;
  statusStripIndicator.style.transform = `translate3d(${indicatorLeft}px, 0, 0)`;
  if (!animate) requestAnimationFrame(() => statusStripIndicator.classList.remove('is-positioning'));
}

let tableHeightAnimation;
function renderTablePageWithHeightTransition() {
  const startHeight = homeTablePanel.getBoundingClientRect().height;
  tableHeightAnimation?.cancel();
  renderTablePage();
  const endHeight = homeTablePanel.getBoundingClientRect().height;

  if (Math.abs(startHeight - endHeight) < 1
    || window.matchMedia('(prefers-reduced-motion: reduce)').matches
    || typeof homeTablePanel.animate !== 'function') return;

  const animation = homeTablePanel.animate([
    { height: `${startHeight}px` },
    { height: `${endHeight}px` }
  ], {
    duration: 340,
    easing: 'cubic-bezier(.22, 1, .36, 1)'
  });
  tableHeightAnimation = animation;
  const clearAnimation = () => {
    if (tableHeightAnimation === animation) tableHeightAnimation = null;
  };
  animation.addEventListener('finish', clearAnimation, { once: true });
  animation.addEventListener('cancel', clearAnimation, { once: true });
}

function applyTableControls() {
  activeAnalysisFilter = analysisFilter.value;
  activeHealthFilter = healthFilter.value;
  currentPage = 1;
  syncSummaryButtons();
  renderTablePageWithHeightTransition();
}

[analysisFilter, healthFilter].forEach((control) => control.addEventListener('change', () => {
  activeSummaryGroup = 'all';
  applyTableControls();
}));

summaryGroupButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const previousIndex = summaryGroupButtons.findIndex((item) => item.classList.contains('is-active'));
    const nextIndex = summaryGroupButtons.indexOf(button);
    if (previousIndex === nextIndex) return;
    activeSummaryGroup = button.dataset.summaryGroup;
    currentPage = 1;
    syncSummaryButtons();
    renderTablePageWithHeightTransition();
    syncSummaryIndicator();
    announce(`${button.textContent.trim()} recordings shown`);
  });
});

requestAnimationFrame(() => syncSummaryIndicator({ animate: false }));
if (statusStrip) new ResizeObserver(() => syncSummaryIndicator({ animate: false })).observe(statusStrip);

function selectFolder(button) {
  activeFolder = button.dataset.folder;
  folderItems.forEach((item) => {
    const active = item === button;
    item.classList.toggle('is-active', active);
    item.setAttribute('aria-pressed', String(active));
  });
  currentPage = 1;
  renderTablePage();
}

function setFolderBranchExpanded(branch, expanded) {
  branch.hidden = !expanded;
}

function syncFolderIcon(button) {
  const iconUse = button.querySelector('.folder-icon use');
  if (!iconUse) return;
  const isExpandedParent = button.classList.contains('folder-parent') && button.getAttribute('aria-expanded') === 'true';
  iconUse.setAttribute('href', isExpandedParent ? '#icon-folder-open' : '#icon-folder');
}

folderItems.forEach((button) => {
  syncFolderIcon(button);
  button.addEventListener('click', () => {
    selectFolder(button);
    if (button.classList.contains('folder-parent')) {
      const expanded = button.getAttribute('aria-expanded') === 'true';
      button.setAttribute('aria-expanded', String(!expanded));
      setFolderBranchExpanded(button.nextElementSibling, !expanded);
      syncFolderIcon(button);
    }
    announce(`${button.querySelector('.folder-label').textContent} folder selected`);
  });
});

function folderLabel(button) {
  return button.querySelector('.folder-label')?.textContent.trim().toLocaleLowerCase() || '';
}

function filterFolderNode(node, query, ancestorMatches = false) {
  const button = node.querySelector(':scope > .folder-item, :scope > .folder-parent');
  const children = node.querySelector(':scope > .folder-children');
  const ownMatch = ancestorMatches || folderLabel(button).includes(query);
  let descendantMatch = false;

  if (children) {
    [...children.children].forEach((child) => {
      if (!child.classList.contains('folder-node')) return;
      descendantMatch = filterFolderNode(child, query, ownMatch) || descendantMatch;
    });
  }

  const visible = ownMatch || descendantMatch;
  node.hidden = !visible;
  if (children) children.hidden = query ? !visible : button.getAttribute('aria-expanded') !== 'true';
  return visible;
}

function applyFolderSearch() {
  const query = folderSearch.value.trim().toLocaleLowerCase();
  const allRecordings = document.querySelector('.folder-all');
  const allVisible = !query || folderLabel(allRecordings).includes(query);
  allRecordings.hidden = !allVisible;
  let anyVisible = allVisible;

  document.querySelectorAll('.folder-root-children > .folder-node').forEach((node) => {
    anyVisible = filterFolderNode(node, query) || anyVisible;
  });

  folderEmpty.hidden = anyVisible;
}

folderSearch.addEventListener('input', applyFolderSearch);

function syncFolderReveal() {
  const shouldReserve = homeView.classList.contains('is-folders-collapsed');
  const shouldShow = activeAppView === 'archive' && shouldReserve;

  folderRevealSlot.setAttribute('aria-hidden', String(!shouldShow));
  folderRevealSlot.toggleAttribute('inert', !shouldShow);
  expandFolders.tabIndex = shouldShow ? 0 : -1;

  folderRevealSlot.classList.toggle('is-reserved', shouldReserve);
  folderRevealSlot.classList.toggle('is-visible', shouldShow);
  sidebar.classList.toggle('has-folder-reveal', shouldShow);
  sidebar.classList.toggle('has-folder-slot', shouldShow);
}

function updateFolderPanel(open) {
  homeView.classList.toggle('is-folders-collapsed', !open);
  folderPanel.classList.toggle('is-collapsed', !open);
  archiveViewButton.setAttribute('aria-expanded', String(open));
  archiveViewButton.setAttribute('aria-controls', 'folder-panel');
  if (open) folderPanel.removeAttribute('aria-hidden');
  else folderPanel.setAttribute('aria-hidden', 'true');
  folderPanel.toggleAttribute('inert', !open);
  syncFolderReveal();
}

const FOLDER_PANEL_DURATION = 260;
const FOLDER_PANEL_EASING = 'cubic-bezier(.4, 0, .2, 1)';
let folderPanelTransitionVersion = 0;
let folderPanelAnimations = [];

function transitionFolderPanel(open, { returnFocus = true, focusTarget = null } = {}) {
  if (
    homeView.classList.contains('is-folders-collapsed') === !open
    && !folderPanelAnimations.length
  ) return;

  const transitionVersion = ++folderPanelTransitionVersion;
  document.documentElement.classList.add('is-folder-view-transition');

  const oldGridColumns = getComputedStyle(homeView).gridTemplateColumns;
  const oldPanelStyle = getComputedStyle(folderPanel);
  const oldPanelOpacity = oldPanelStyle.opacity;
  const oldPanelTransform = oldPanelStyle.transform === 'none'
    ? 'translate3d(0, 0, 0)'
    : oldPanelStyle.transform;

  if (!open && folderPanel.contains(document.activeElement) && document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }

  folderPanelAnimations.forEach((animation) => animation.cancel());
  folderPanelAnimations = [];

  const finish = () => {
    if (folderPanelTransitionVersion !== transitionVersion) return;
    folderPanelAnimations.forEach((animation) => animation.cancel());
    folderPanelAnimations = [];
    document.documentElement.classList.remove('is-folder-view-transition');
    if (focusTarget) {
      focusTarget.focus();
    } else if (returnFocus) {
      (open ? collapseFolders : expandFolders).focus();
    }
    announce(open ? 'Folders shown' : 'Folders hidden');
  };

  if (reduceMotion.matches || typeof homeView.animate !== 'function') {
    updateFolderPanel(open);
    finish();
    return;
  }

  updateFolderPanel(open);
  const newGridColumns = getComputedStyle(homeView).gridTemplateColumns;
  const nextAnimations = [];

  if (oldGridColumns !== newGridColumns) {
    nextAnimations.push(homeView.animate([
      { gridTemplateColumns: oldGridColumns },
      { gridTemplateColumns: newGridColumns }
    ], {
      duration: FOLDER_PANEL_DURATION,
      easing: FOLDER_PANEL_EASING,
      fill: 'both'
    }));
  }

  nextAnimations.push(folderPanel.animate([
    { opacity: oldPanelOpacity, transform: oldPanelTransform },
    {
      opacity: open ? 1 : 0,
      transform: open ? 'translate3d(0, 0, 0)' : 'translate3d(-100%, 0, 0)'
    }
  ], {
    duration: FOLDER_PANEL_DURATION,
    easing: FOLDER_PANEL_EASING,
    fill: 'both'
  }));

  folderPanelAnimations = nextAnimations;
  Promise.allSettled(folderPanelAnimations.map((animation) => animation.finished)).then(finish);
}

collapseFolders.addEventListener('click', (event) => transitionFolderPanel(false, { returnFocus: event.detail === 0 }));

function showFolders(event) { transitionFolderPanel(true, { returnFocus: event?.detail === 0 }); }

function toggleFoldersFromDatabase() {
  transitionFolderPanel(homeView.classList.contains('is-folders-collapsed'), {
    returnFocus: false
  });
}

clearFilters.addEventListener('click', () => {
  tableSearch.value = '';
  tableQuery = '';
  analysisFilter.value = 'all';
  healthFilter.value = 'all';
  activeSummaryGroup = 'all';
  activeFolder = 'all';
  folderItems.forEach((item) => {
    const active = item.dataset.folder === 'all';
    item.classList.toggle('is-active', active);
    item.setAttribute('aria-pressed', String(active));
  });
  applyTableControls();
});

clearFilterMenu.addEventListener('click', () => {
  analysisFilter.value = 'all';
  healthFilter.value = 'all';
  activeSummaryGroup = 'all';
  applyTableControls();
  announce('Recording filters cleared');
});

rescanArchive?.addEventListener('click', () => {
  rescanArchive.disabled = true;
  rescanArchive.classList.add('is-scanning');
  rescanArchive.setAttribute('aria-label', 'Scanning archive');
  rescanArchive.setAttribute('title', 'Scanning archive');
  homeTablePanel.setAttribute('aria-busy', 'true');
  lastScanned.textContent = 'Scanning archive';
  window.setTimeout(() => {
    rescanArchive.disabled = false;
    rescanArchive.classList.remove('is-scanning');
    rescanArchive.setAttribute('aria-label', 'Rescan archive');
    rescanArchive.setAttribute('title', 'Rescan archive');
    homeTablePanel.setAttribute('aria-busy', 'false');
    lastScanned.textContent = 'Last scanned just now';
    acknowledgeStateChange(lastScanned);
    announce('Archive scan complete. 60 recordings found.');
  }, 1100);
});

function selectedRecordingRows() {
  return tableRows.filter((row) => row.querySelector('.row-select').checked);
}

function selectedArtifacts() {
  return [...prepareForm.querySelectorAll('input[name="artifact"]:checked')].map((input) => input.value);
}

function updatePrepareImpact() {
  const recordingTotal = selectedRecordingRows().length;
  const artifactTotal = selectedArtifacts().length;
  const jobTotal = recordingTotal * artifactTotal;
  prepareImpact.textContent = jobTotal
    ? `${jobTotal} ${jobTotal === 1 ? 'job' : 'jobs'} will be added to the serial queue.`
    : 'Select at least one output to continue.';
  document.querySelector('#confirm-prepare').disabled = jobTotal === 0;
}

function openPrepareDialog() {
  const rows = selectedRecordingRows();
  prepareSelectionSummary.textContent = `${rows.length} ${rows.length === 1 ? 'recording' : 'recordings'} selected`;
  prepareRecordings.innerHTML = rows.map((row) => `<span><strong>${row.dataset.name}</strong><small>${row.dataset.filename}</small></span>`).join('');
  updatePrepareImpact();
  prepareDialog.showModal();
}

function addQueuedArtifact(recordingName, artifact, queuedLabel = 'just now') {
  const row = document.createElement('tr');
  const recordingId = findRecordingRow(recordingName)?.dataset.filename
    || recordingName.toLocaleLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  row.dataset.jobState = 'queued';
  row.dataset.recordingName = recordingName;
  row.dataset.recordingId = recordingId;
  row.dataset.artifact = artifact;
  row.dataset.estimateMinutes = '5';
  row.innerHTML = `<td class="selection-column"><input class="queue-row-select" type="checkbox" aria-label="Select ${artifact} for ${recordingName}" /></td><td class="queue-recording"><strong>${recordingName}</strong><span class="cell-sublabel">${recordingId}</span></td><td class="queue-artifact">${artifact}</td><td>${queuedLabel}</td><td class="queue-estimate"><strong data-queue-estimate></strong><span data-queue-ready></span></td><td><div class="queue-controls"><button class="queue-move queue-move--up" type="button" data-processing-action="move-up" aria-label="Move ${artifact} earlier" title="Move earlier"><svg aria-hidden="true"><use href="#icon-chevron" /></svg></button><button class="queue-move queue-move--down" type="button" data-processing-action="move-down" aria-label="Move ${artifact} later" title="Move later"><svg aria-hidden="true"><use href="#icon-chevron" /></svg></button><button class="queue-cancel" type="button" data-processing-action="cancel-queued" aria-label="Cancel ${artifact}" title="Cancel"><svg aria-hidden="true"><use href="#icon-status-x" /></svg></button></div></td>`;
  processingQueueBody.append(row);
  acknowledgeStateChange(row);
}

function showOperationToast(title, copy) {
  operationToastTitle.textContent = title;
  operationToastCopy.textContent = copy;
  operationToast.hidden = false;
  acknowledgeStateChange(operationToast);
}

bulkActionButtons.forEach((button) => {
  button.addEventListener('click', () => {
    if (button.dataset.bulkAction === 'prepare') openPrepareDialog();
  });
});

prepareForm.querySelectorAll('input[name="artifact"]').forEach((input) => input.addEventListener('change', updatePrepareImpact));
cancelPrepare.addEventListener('click', () => prepareDialog.close());
prepareForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const rows = selectedRecordingRows();
  const artifacts = selectedArtifacts();
  if (!rows.length || !artifacts.length) return;

  rows.forEach((row) => {
    row.dataset.status = 'queued';
    const index = recordingNames.indexOf(row.dataset.name);
    row.querySelector('td:last-child').innerHTML = statusMarkup('queued', index);
    artifacts.forEach((artifact) => addQueuedArtifact(row.dataset.name, artifact));
  });
  const jobTotal = rows.length * artifacts.length;
  prepareDialog.close();
  clearTableSelection();
  updateProcessingCounts();
  renderTablePage();
  showOperationToast('Jobs added to processing', `${jobTotal} ${jobTotal === 1 ? 'artifact' : 'artifacts'} queued from ${rows.length} ${rows.length === 1 ? 'recording' : 'recordings'}.`);
  announce(`${jobTotal} processing jobs created`);
});

viewProcessingToast.addEventListener('click', () => {
  operationToast.hidden = true;
  showView('progression');
  setJobFilter('queue');
});
dismissToast.addEventListener('click', () => { operationToast.hidden = true; });

homeLink.addEventListener('click', (event) => {
  event.preventDefault();
  showView('archive');
  announce('Recordings selected');
});

globalTimeline.addEventListener('input', () => {
  setTimelinePosition(globalTimeline.value);
});

globalTimeline.addEventListener('change', () => {
  announce(`Timeline set to ${timelineCurrent.textContent}`);
});

searchInput.addEventListener('input', applyFilters);

filterButton.addEventListener('click', () => {
  const isOpen = filterButton.getAttribute('aria-expanded') === 'true';

  if (isOpen) {
    closeFilterMenu();
  } else {
    openFilterMenu();
  }
});

filterButton.addEventListener('keydown', (event) => {
  if (event.key !== 'ArrowDown') return;

  event.preventDefault();
  openFilterMenu();
  filterOptions.find((option) => option.classList.contains('is-active'))?.focus();
});

filterOptions.forEach((option, optionIndex) => {
  option.addEventListener('click', () => {
    activeFilter = option.dataset.filter;

    filterOptions.forEach((item) => {
      const active = item === option;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-pressed', String(active));
    });

    const filterLabel = option.textContent.trim();
    const hasFilter = activeFilter !== 'all';
    filterButton.classList.toggle('has-filter', hasFilter);
    filterButton.setAttribute('aria-label', hasFilter ? `Filter ROSbags: ${filterLabel}` : 'Filter ROSbags');

    applyFilters();
    closeFilterMenu({ returnFocus: true });
    announce(`${filterLabel} filter selected. ${visibleCount.textContent}.`);
  });

  option.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeFilterMenu({ returnFocus: true });
      return;
    }

    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;

    event.preventDefault();
    const direction = event.key === 'ArrowDown' ? 1 : -1;
    const nextIndex = (optionIndex + direction + filterOptions.length) % filterOptions.length;
    filterOptions[nextIndex].focus();
  });
});

document.addEventListener('click', (event) => {
  if (!filterMenu.hidden && !filterControl.contains(event.target)) {
    closeFilterMenu();
  }
  if (!event.target.closest('.row-menu')) {
    document.querySelectorAll('.row-menu').forEach((menu) => menu.remove());
  }
  if (!sensorPicker.contains(event.target)) closeSensorPicker();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !filterMenu.hidden) {
    closeFilterMenu({ returnFocus: true });
  }
  if (event.key === 'Escape' && !sensorPickerMenu.hidden) closeSensorPicker({ returnFocus: true });
});

toolButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const shouldToggleFolders = button === archiveViewButton && activeAppView === 'archive';
    if (button.dataset.view === 'analyzer' && !selectedRecordingRow) resetWorkspace();
    showView(button.dataset.view);
    if (shouldToggleFolders) toggleFoldersFromDatabase();

    announce(`${button.getAttribute('aria-label')} selected`);
  });
});

expandFolders.addEventListener('click', showFolders);
collapseRecordingDetails.addEventListener('click', () => {
  setRecordingDetailsCollapsed(!analyzerView.classList.contains('is-details-collapsed'), { returnFocus: true });
});
openFigure8?.addEventListener('click', () => {
  const figure8Row = tableRows.find((row) => row.dataset.name === 'Figure 8');
  setAnalyzerRecording(figure8Row, { announceChange: true });
});

function syncProcessingTabIndicator({ animate = true } = {}) {
  const activeButton = jobFilterButtons.find((button) => button.classList.contains('is-active'));
  if (!activeButton || !processingTabs || !processingTabIndicator) return;
  const tabsRect = processingTabs.getBoundingClientRect();
  const buttonRect = activeButton.getBoundingClientRect();
  processingTabIndicator.classList.toggle('is-positioning', !animate);
  processingTabIndicator.style.width = `${buttonRect.width}px`;
  processingTabIndicator.style.transform = `translate3d(${buttonRect.left - tabsRect.left + processingTabs.scrollLeft}px, 0, 0)`;
  if (!animate) requestAnimationFrame(() => processingTabIndicator.classList.remove('is-positioning'));
}

function setJobFilter(filter) {
  jobFilterButtons.forEach((button) => {
    const active = button.dataset.jobFilter === filter;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
    button.tabIndex = active ? 0 : -1;
  });
  processingPanels.forEach((panel) => {
    const active = panel.id === `processing-${filter === 'failed' ? 'failures' : filter}-panel`;
    panel.hidden = !active;
  });
  syncQueueSelection();
  syncFailureSelection();
  syncProcessingTabIndicator();
}

requestAnimationFrame(() => syncProcessingTabIndicator({ animate: false }));
new ResizeObserver(() => syncProcessingTabIndicator({ animate: false })).observe(processingTabs);

function refreshProcessingView({ advanceElapsed = false } = {}) {
  if (currentProcessingJob && currentProcessingJob.dataset.jobState === 'running') {
    const elapsed = Math.min(Number(currentProcessingJob.dataset.estimatedTotal) - 1, Number(currentProcessingJob.dataset.elapsed) + Number(advanceElapsed));
    const estimatedTotal = Number(currentProcessingJob.dataset.estimatedTotal);
    const percent = Math.min(99, Math.round((elapsed / estimatedTotal) * 100));
    currentProcessingJob.dataset.elapsed = String(elapsed);
    currentProcessingJob.querySelector('[data-current-elapsed]').textContent = formatElapsedTime(elapsed, { compact: true });
    currentProcessingJob.querySelector('[data-current-percent]').textContent = String(percent);
    currentProcessingJob.querySelector('[data-current-progress]').style.width = `${percent}%`;
    const progress = currentProcessingJob.querySelector('[role="progressbar"]');
    progress.setAttribute('aria-valuenow', String(percent));
  }
}

function updateProcessingCounts() {
  const queueRows = [...processingQueueBody.querySelectorAll('tr')];
  const currentRemainingSeconds = currentProcessingJob
    ? Math.max(0, Number(currentProcessingJob.dataset.estimatedTotal) - Number(currentProcessingJob.dataset.elapsed))
    : 0;
  let minutesUntilReady = Math.max(1, Math.ceil(currentRemainingSeconds / 60));

  queueRows.forEach((row, index) => {
    minutesUntilReady += Number(row.dataset.estimateMinutes) || 5;
    const readyTime = new Date(Date.now() + (minutesUntilReady * 60 * 1000));
    row.querySelector('[data-queue-estimate]').textContent = `${minutesUntilReady} min`;
    row.querySelector('[data-queue-ready]').textContent = `Ready ${QUEUE_READY_TIME_FORMATTER.format(readyTime)}`;
    const up = row.querySelector('[data-processing-action="move-up"]');
    const down = row.querySelector('[data-processing-action="move-down"]');
    if (up) up.disabled = index === 0;
    if (down) down.disabled = index === queueRows.length - 1;
  });
  const failedRows = [...failureTableBody.querySelectorAll('tr[data-job-state="failed"]')];
  queueCount.textContent = String(queueRows.length);
  failureCount.textContent = String(failedRows.length);
  syncQueueSelection();
  syncFailureSelection();
}

function syncQueueSelection() {
  const selectors = [...processingQueueBody.querySelectorAll('.queue-row-select')];
  const selectedSelectors = selectors.filter((checkbox) => checkbox.checked);
  const selectedTotal = selectedSelectors.length;
  const selectedRows = selectedSelectors.map((checkbox) => checkbox.closest('tr'));
  const selectedSet = new Set(selectedRows);
  selectAllQueued.checked = selectors.length > 0 && selectedTotal === selectors.length;
  selectAllQueued.indeterminate = selectedTotal > 0 && selectedTotal < selectors.length;
  processingQueueBody.querySelectorAll('tr').forEach((row) => {
    row.classList.toggle('is-selected', selectedSet.has(row));
  });

  const queueTabActive = jobFilterButtons.some((button) => button.dataset.jobFilter === 'queue' && button.classList.contains('is-active'));
  const selectionVisible = queueTabActive && selectedTotal > 0;
  queueSelectionActions.hidden = !selectionVisible;
  queueSelectionFooter.hidden = selectedTotal === 0;
  queueSelectedCount.textContent = String(selectedTotal);
  cancelSelectedQueue.querySelector('span').textContent = selectedTotal === 1 ? 'Cancel selected' : `Cancel ${selectedTotal} selected`;
  moveSelectedQueueUp.disabled = !selectedRows.some((row) => row.previousElementSibling && !selectedSet.has(row.previousElementSibling));
  moveSelectedQueueDown.disabled = !selectedRows.some((row) => row.nextElementSibling && !selectedSet.has(row.nextElementSibling));
}

selectAllQueued.addEventListener('change', () => {
  processingQueueBody.querySelectorAll('.queue-row-select').forEach((checkbox) => {
    checkbox.checked = selectAllQueued.checked;
  });
  syncQueueSelection();
});

processingQueueBody.addEventListener('change', (event) => {
  if (event.target.matches('.queue-row-select')) syncQueueSelection();
});

function syncFailureSelection() {
  const selectors = [...failureTableBody.querySelectorAll('tr[data-job-state="failed"] .failure-row-select')];
  const selected = selectors.filter((checkbox) => checkbox.checked);
  const selectedTotal = selected.length;
  const allSelected = selectors.length > 0 && selectedTotal === selectors.length;
  selectAllFailures.checked = allSelected;
  selectAllFailures.indeterminate = selectedTotal > 0 && !allSelected;
  failureTableBody.querySelectorAll('tr').forEach((row) => {
    row.classList.toggle('is-selected', row.querySelector('.failure-row-select')?.checked === true);
  });

  const failuresTabActive = jobFilterButtons.some((button) => button.dataset.jobFilter === 'failed' && button.classList.contains('is-active'));
  failureSelectionActions.hidden = !failuresTabActive || selectedTotal === 0;
  failureSelectionFooter.hidden = selectedTotal === 0;
  failureSelectedCount.textContent = String(selectedTotal);

  retrySelectedFailures.querySelector('span').textContent = selectedTotal === 1 ? 'Retry selected' : `Retry ${selectedTotal} selected`;
  retrySelectedFailures.setAttribute('aria-label', `Retry ${selectedTotal} selected ${selectedTotal === 1 ? 'failure' : 'failures'}`);
}

selectAllFailures.addEventListener('change', () => {
  failureTableBody.querySelectorAll('tr[data-job-state="failed"] .failure-row-select').forEach((checkbox) => {
    checkbox.checked = selectAllFailures.checked;
  });
  syncFailureSelection();
});

failureTableBody.addEventListener('change', (event) => {
  if (event.target.matches('.failure-row-select')) syncFailureSelection();
});

function animateQueueReorder(row, sibling, processingAction) {
  const affectedRows = [row, sibling];
  const previousPositions = new Map(affectedRows.map((item) => [item, item.getBoundingClientRect().top]));

  if (processingAction === 'move-up') processingQueueBody.insertBefore(row, sibling);
  else processingQueueBody.insertBefore(sibling, row);
  updateProcessingCounts();

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || typeof row.animate !== 'function') return;
  const movedOffset = previousPositions.get(row) - row.getBoundingClientRect().top;
  const siblingOffset = previousPositions.get(sibling) - sibling.getBoundingClientRect().top;
  sibling.animate([
    { transform: `translate3d(0, ${siblingOffset}px, 0)` },
    { transform: 'translate3d(0, 0, 0)' },
  ], {
    duration: 320,
    easing: 'cubic-bezier(.22, 1, .36, 1)',
  });
  row.animate([
    { transform: `translate3d(0, ${movedOffset}px, 0) scale(.985)`, filter: 'brightness(1)' },
    { offset: .55, transform: 'translate3d(0, 0, 0) scale(.985)', filter: 'brightness(1.18)' },
    { transform: 'translate3d(0, 0, 0) scale(1)', filter: 'brightness(1)' },
  ], {
    duration: 420,
    easing: 'cubic-bezier(.16, 1, .3, 1)',
  });
}

function moveSelectedQueueRows(direction) {
  const rows = [...processingQueueBody.querySelectorAll('tr')];
  const selectedRows = rows.filter((row) => row.querySelector('.queue-row-select')?.checked);
  const selectedSet = new Set(selectedRows);
  const previousPositions = new Map(rows.map((row) => [row, row.getBoundingClientRect().top]));

  if (direction === 'up') {
    selectedRows.forEach((row) => {
      const previous = row.previousElementSibling;
      if (previous && !selectedSet.has(previous)) processingQueueBody.insertBefore(row, previous);
    });
  } else {
    [...selectedRows].reverse().forEach((row) => {
      const next = row.nextElementSibling;
      if (next && !selectedSet.has(next)) next.after(row);
    });
  }

  updateProcessingCounts();
  if (reduceMotion.matches) return;
  rows.forEach((row) => {
    const offset = previousPositions.get(row) - row.getBoundingClientRect().top;
    if (!offset) return;
    row.animate([
      { transform: `translate3d(0, ${offset}px, 0)` },
      { transform: 'translate3d(0, 0, 0)' }
    ], {
      duration: 320,
      easing: 'cubic-bezier(.16, 1, .3, 1)'
    });
  });
  announce(`${selectedRows.length} selected ${selectedRows.length === 1 ? 'job' : 'jobs'} moved ${direction === 'up' ? 'earlier' : 'later'}`);
}

function openCancellationDialog({ title, copy, confirmLabel, onConfirm }) {
  pendingCancellation = onConfirm;
  cancelJobTitle.textContent = title;
  cancelJobCopy.textContent = copy;
  confirmJobCancel.textContent = confirmLabel;
  cancelJobDialog.showModal();
}

async function removeSelectedQueueRows(rows) {
  if (!reduceMotion.matches) {
    const animations = rows.map((row) => row.animate([
      { opacity: 1, transform: 'translate3d(0, 0, 0)' },
      { opacity: 0, transform: 'translate3d(5px, 0, 0)' }
    ], {
      duration: 140,
      easing: 'cubic-bezier(.4, 0, 1, 1)',
      fill: 'forwards'
    }));
    await Promise.allSettled(animations.map((animation) => animation.finished));
  }
  rows.forEach((row) => row.remove());
  updateProcessingCounts();
}

moveSelectedQueueUp.addEventListener('click', () => moveSelectedQueueRows('up'));
moveSelectedQueueDown.addEventListener('click', () => moveSelectedQueueRows('down'));
cancelSelectedQueue.addEventListener('click', () => {
  const rows = [...processingQueueBody.querySelectorAll('tr')].filter((row) => row.querySelector('.queue-row-select')?.checked);
  if (!rows.length) return;
  const total = rows.length;
  openCancellationDialog({
    title: `Cancel ${total} selected ${total === 1 ? 'job' : 'jobs'}?`,
    copy: 'The selected jobs will be removed from the queue. Their source recordings will not be deleted.',
    confirmLabel: total === 1 ? 'Cancel job' : `Cancel ${total} jobs`,
    onConfirm: async () => {
      await removeSelectedQueueRows(rows);
      showOperationToast('Queue updated', `${total} selected ${total === 1 ? 'job was' : 'jobs were'} cancelled.`);
      announce(`${total} selected ${total === 1 ? 'job' : 'jobs'} cancelled`);
    }
  });
});

keepProcessing.addEventListener('click', () => cancelJobDialog.close());
confirmJobCancel.addEventListener('click', () => {
  const cancellation = pendingCancellation;
  cancelJobDialog.close();
  pendingCancellation = null;
  cancellation?.();
});
cancelJobDialog.addEventListener('close', () => { pendingCancellation = null; });
cancelJobDialog.addEventListener('click', (event) => {
  if (event.target === cancelJobDialog) cancelJobDialog.close();
});

function findRecordingRow(name) {
  return tableRows.find((row) => row.dataset.name === name) || null;
}

function openProcessingRecordingByName(name) {
  const row = findRecordingRow(name);
  if (!row) {
    showOperationToast('Recording not found', `${name} is no longer present in this archive view.`);
    return;
  }
  setAnalyzerRecording(row);
  showView('analyzer');
  announce(`${name} opened from Processing`);
}

function queueFailureRow(row) {
  if (!row || row.dataset.jobState !== 'failed') return;
  const recordingName = row.dataset.recordingName;
  const artifact = row.dataset.artifact;
  row.dataset.jobState = 'queued';
  const selector = row.querySelector('.failure-row-select');
  if (selector) {
    selector.checked = false;
    selector.disabled = true;
  }
  const actionCell = row.querySelector('.processing-row-actions');
  actionCell.innerHTML = '<span class="retry-state">Queued</span>';
  acknowledgeStateChange(actionCell);
  addQueuedArtifact(recordingName, artifact, 'retry · just now');
  updateProcessingCounts();
  showOperationToast('Retry queued', `${artifact} for ${recordingName} was added to the queue.`);
  announce(`Retry queued for ${artifact} in ${recordingName}`);
}

function openProcessingDiagnostic(row) {
  currentDiagnosticRow = row;
  const recording = row.dataset.recordingName;
  const artifact = row.dataset.artifact;
  processingErrorTitle.textContent = `${artifact} · ${recording}`;
  processingErrorCopy.textContent = row.dataset.error;
  processingErrorRecovery.textContent = row.dataset.recovery;
  processingErrorMeta.innerHTML = `
    <div><dt>ROS topic</dt><dd><code>${row.dataset.topic}</code></dd></div>
    <div><dt>Source file</dt><dd>${row.dataset.sourceFile}</dd></div>
    <div><dt>Expected</dt><dd>${row.dataset.expected}</dd></div>
    <div><dt>Actual</dt><dd>${row.dataset.actual}</dd></div>`;
  processingErrorDialog.showModal();
}

jobFilterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    setJobFilter(button.dataset.jobFilter);
    announce(`${button.textContent.trim()} processing view shown`);
  });
});

progressionView.addEventListener('click', (event) => {
  const action = event.target.closest('[data-processing-action]');
  if (!action) return;

  const row = action.closest('tr');
  const recording = action.dataset.recordingName || row?.dataset.recordingName || action.closest('[data-recording-name]')?.dataset.recordingName || 'recording';
  const artifact = row?.dataset.artifact || action.closest('[data-artifact]')?.dataset.artifact || 'artifact';
  const processingAction = action.dataset.processingAction;

  if (processingAction === 'open') {
    openProcessingRecordingByName(recording);
    return;
  }

  if (processingAction === 'move-up' || processingAction === 'move-down') {
    const sibling = processingAction === 'move-up' ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    animateQueueReorder(row, sibling, processingAction);
    action.focus();
    announce(`${artifact} moved ${processingAction === 'move-up' ? 'earlier' : 'later'} in the queue`);
    return;
  }

  if (processingAction === 'cancel-queued') {
    if (action.dataset.confirming !== 'true') {
      action.dataset.confirming = 'true';
      action.setAttribute('aria-label', `Confirm cancel ${artifact}`);
      action.title = 'Confirm cancel';
      window.setTimeout(() => {
        if (!action.isConnected) return;
        action.dataset.confirming = 'false';
        action.setAttribute('aria-label', `Cancel ${artifact}`);
        action.title = 'Cancel';
      }, 4000);
      announce(`Confirm cancellation for ${artifact}`);
      return;
    }
    removeRowWithMotion(row, () => {
      updateProcessingCounts();
      announce(`${artifact} removed from the processing queue`);
    });
    return;
  }

  if (processingAction === 'pause') {
    const paused = currentProcessingJob.dataset.jobState === 'paused';
    currentProcessingJob.dataset.jobState = paused ? 'running' : 'paused';
    const nextLabel = paused ? 'Pause current job' : 'Resume current job';
    action.setAttribute('aria-label', nextLabel);
    action.title = nextLabel;
    action.querySelector('use').setAttribute('href', paused ? '#icon-pause' : '#icon-play');
    action.querySelector('span').textContent = paused ? 'Pause' : 'Resume';
    acknowledgeStateChange(currentProcessingJob.querySelector('.current-job-body'));
    announce(paused ? 'Current processing job resumed' : 'Current processing job paused');
    return;
  }

  if (processingAction === 'cancel-current') {
    openCancellationDialog({
      title: 'Cancel current job?',
      copy: `${artifact} for ${recording} will stop processing. The source recording will not be deleted.`,
      confirmLabel: 'Cancel job',
      onConfirm: () => {
        currentProcessingJob.dataset.jobState = 'cancelled';
        currentProcessingJob.querySelectorAll('.current-job-actions button').forEach((button) => { button.disabled = true; });
        acknowledgeStateChange(currentProcessingJob.querySelector('.current-job-body'));
        showOperationToast('Current job cancelled', `${artifact} for ${recording} stopped without deleting its source data.`);
        announce('Current processing job cancelled');
      }
    });
    return;
  }

  if (processingAction === 'retry') {
    queueFailureRow(row);
    return;
  }

  if (processingAction === 'error') openProcessingDiagnostic(row);
});

progressionView.addEventListener('keydown', (event) => {
  const historyRow = event.target.closest('.history-table tr[data-processing-action="open"]');
  if (!historyRow || (event.key !== 'Enter' && event.key !== ' ')) return;
  event.preventDefault();
  openProcessingRecordingByName(historyRow.dataset.recordingName);
});

retrySelectedFailures.addEventListener('click', () => {
  const failedRows = [...failureTableBody.querySelectorAll('tr[data-job-state="failed"]')];
  const rowsToRetry = failedRows.filter((row) => row.querySelector('.failure-row-select')?.checked);
  rowsToRetry.forEach(queueFailureRow);
  setJobFilter('queue');
});

closeProcessingError.addEventListener('click', () => processingErrorDialog.close());
copyProcessingError.addEventListener('click', async () => {
  if (!currentDiagnosticRow) return;
  const text = `${processingErrorTitle.textContent}\n${processingErrorCopy.textContent}\nTopic: ${currentDiagnosticRow.dataset.topic}\nExpected: ${currentDiagnosticRow.dataset.expected}\nActual: ${currentDiagnosticRow.dataset.actual}\nRecovery: ${currentDiagnosticRow.dataset.recovery}`;
  try {
    await navigator.clipboard.writeText(text);
    copyProcessingError.textContent = 'Copied';
  } catch (_) {
    copyProcessingError.textContent = 'Copy unavailable';
  }
});
openProcessingRecording.addEventListener('click', () => {
  if (!currentDiagnosticRow) return;
  const name = currentDiagnosticRow.dataset.recordingName;
  processingErrorDialog.close();
  openProcessingRecordingByName(name);
});
retryProcessingError.addEventListener('click', () => {
  if (!currentDiagnosticRow) return;
  queueFailureRow(currentDiagnosticRow);
  processingErrorDialog.close();
  setJobFilter('queue');
});

processingErrorDialog.addEventListener('click', (event) => {
  if (event.target === processingErrorDialog) processingErrorDialog.close();
});

setJobFilter('queue');
updateProcessingCounts();

window.setInterval(() => {
  refreshProcessingView({ advanceElapsed: true });
}, 1000);

resetWorkspace();
