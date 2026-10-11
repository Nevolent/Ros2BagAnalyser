function parseDecimalNanoseconds(value) {
  if (typeof value !== 'string' || !/^-?(0|[1-9]\d*)$/.test(value)) {
    throw new Error('The telemetry series contains an invalid timestamp.');
  }
  const nanoseconds = BigInt(value);
  const limit = BigInt(Number.MAX_SAFE_INTEGER);
  if (nanoseconds < -limit || nanoseconds > limit) {
    throw new Error('The telemetry series timestamp is outside the browser range.');
  }
  return nanoseconds;
}

function parseCount(value, label) {
  if (typeof value !== 'string' || !/^\d+$/.test(value)) {
    throw new Error(`The telemetry ${label} count is invalid.`);
  }
  const count = Number(value);
  if (!Number.isSafeInteger(count)) {
    throw new Error(`The telemetry ${label} count is outside the browser range.`);
  }
  return count;
}

function parseSeries(document, artifact) {
  if (
    !document ||
    typeof document !== 'object' ||
    Array.isArray(document) ||
    document.schema_version !== 2 ||
    !Array.isArray(document.samples) ||
    !Array.isArray(artifact.series) ||
    artifact.series.length === 0
  ) {
    throw new Error('The telemetry series format is unsupported.');
  }
  const coverageStartNs = parseDecimalNanoseconds(artifact.coverage_start_ns);
  const coverageEndNs = parseDecimalNanoseconds(artifact.coverage_end_ns);
  const deliveredCount = parseCount(artifact.delivered_sample_count, 'delivered sample');
  if (document.samples.length !== deliveredCount) {
    throw new Error('The telemetry series sample count does not match its metadata.');
  }

  const seenIds = new Set();
  const seenColumns = new Set();
  const series = artifact.series.map((definition) => {
    if (
      !definition ||
      typeof definition !== 'object' ||
      Array.isArray(definition) ||
      typeof definition.id !== 'string' ||
      !/^[a-z][a-z0-9_]*$/.test(definition.id) ||
      seenIds.has(definition.id) ||
      typeof definition.component !== 'string' ||
      typeof definition.display_label !== 'string' ||
      typeof definition.units !== 'string' ||
      !Number.isInteger(definition.column_index) ||
      definition.column_index < 1 ||
      definition.column_index > artifact.series.length ||
      seenColumns.has(definition.column_index) ||
      typeof definition.available !== 'boolean'
    ) {
      throw new Error('The telemetry series definition is invalid.');
    }
    seenIds.add(definition.id);
    seenColumns.add(definition.column_index);
    const finiteCount = parseCount(
      definition.finite_sample_count,
      `${definition.id} finite sample`,
    );
    const nonFiniteCount = parseCount(
      definition.non_finite_sample_count,
      `${definition.id} non-finite sample`,
    );
    if (
      finiteCount + nonFiniteCount !== deliveredCount ||
      definition.available !== finiteCount > 0 ||
      (finiteCount > 0 &&
        (typeof definition.minimum_value !== 'number' ||
          !Number.isFinite(definition.minimum_value) ||
          typeof definition.maximum_value !== 'number' ||
          !Number.isFinite(definition.maximum_value) ||
          definition.minimum_value > definition.maximum_value)) ||
      (finiteCount === 0 &&
        (definition.minimum_value !== null || definition.maximum_value !== null))
    ) {
      throw new Error('The telemetry series definition does not match its samples.');
    }
    return {
      id: definition.id,
      component: definition.component,
      displayLabel: definition.display_label,
      units: definition.units,
      columnIndex: definition.column_index,
      finiteCount,
      nonFiniteCount,
      minimumValue: definition.minimum_value,
      maximumValue: definition.maximum_value,
      available: definition.available,
    };
  });
  if (seenColumns.size !== series.length) {
    throw new Error('The telemetry series columns are invalid.');
  }

  let previousNs = null;
  const actualFinite = series.map(() => 0);
  const actualNonFinite = series.map(() => 0);
  const actualMinimum = series.map(() => null);
  const actualMaximum = series.map(() => null);
  const rows = document.samples.map((sample) => {
    if (!Array.isArray(sample) || sample.length !== series.length + 1) {
      throw new Error('The telemetry series contains an invalid sample.');
    }
    const timeNs = parseDecimalNanoseconds(sample[0]);
    if (previousNs !== null && timeNs < previousNs) {
      throw new Error('The telemetry series timestamps are not ordered.');
    }
    previousNs = timeNs;
    const values = series.map((definition, index) => {
      const value = sample[definition.columnIndex];
      if (value === null) {
        actualNonFinite[index] += 1;
        return null;
      }
      if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error('The telemetry series contains an invalid value.');
      }
      actualFinite[index] += 1;
      actualMinimum[index] =
        actualMinimum[index] === null ? value : Math.min(actualMinimum[index], value);
      actualMaximum[index] =
        actualMaximum[index] === null ? value : Math.max(actualMaximum[index], value);
      return value;
    });
    return {
      timeNs,
      timeSeconds: Number(timeNs) / 1e9,
      values,
    };
  });
  if (
    rows.length === 0 ||
    rows[0].timeNs !== coverageStartNs ||
    rows[rows.length - 1].timeNs !== coverageEndNs ||
    series.some(
      (definition, index) =>
        actualFinite[index] !== definition.finiteCount ||
        actualNonFinite[index] !== definition.nonFiniteCount ||
        actualMinimum[index] !== definition.minimumValue ||
        actualMaximum[index] !== definition.maximumValue,
    )
  ) {
    throw new Error('The telemetry series does not match its declared coverage.');
  }
  const defaultSeries = series.find((definition) => definition.id === artifact.default_series_id);
  if (!defaultSeries?.available) {
    throw new Error('The default telemetry series is unavailable.');
  }
  return {
    rows,
    series,
    defaultSeriesId: defaultSeries.id,
    coverageStart: Number(coverageStartNs) / 1e9,
    coverageEnd: Number(coverageEndNs) / 1e9,
  };
}

async function parseSeriesStream(body, artifact) {
  const reader = body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const samples = [];
  let pending = '';
  let state = 'prefix';
  let first = true;
  const consume = () => {
    while (true) {
      pending = pending.trimStart();
      if (state === 'prefix') {
        const match = /^\{\s*"schema_version"\s*:\s*2\s*,\s*"samples"\s*:\s*\[/.exec(pending);
        if (!match) {
          if (pending.length > 1024) throw new Error('The telemetry series format is unsupported.');
          return;
        }
        pending = pending.slice(match[0].length);
        state = 'row';
      }
      if (state === 'row') {
        pending = pending.trimStart();
        if (!pending) return;
        if (pending[0] === ']') {
          if (!first) throw new Error('The telemetry series contains a trailing separator.');
          pending = pending.slice(1);
          state = 'suffix';
          continue;
        }
        if (pending[0] !== '[') throw new Error('The telemetry series contains an invalid sample.');
        let depth = 0;
        let quoted = false;
        let escaped = false;
        let end = -1;
        for (let index = 0; index < pending.length; index += 1) {
          const character = pending[index];
          if (escaped) {
            escaped = false;
            continue;
          }
          if (quoted && character === '\\') {
            escaped = true;
            continue;
          }
          if (character === '"') {
            quoted = !quoted;
            continue;
          }
          if (quoted) continue;
          if (character === '[') depth += 1;
          if (character === ']' && --depth === 0) {
            end = index + 1;
            break;
          }
        }
        if (end < 0) {
          if (pending.length > 2 * 1024 * 1024)
            throw new Error('The telemetry series sample is too large.');
          return;
        }
        samples.push(JSON.parse(pending.slice(0, end)));
        pending = pending.slice(end);
        first = false;
        state = 'separator';
      }
      if (state === 'separator') {
        pending = pending.trimStart();
        if (!pending) return;
        if (pending[0] === ',') {
          pending = pending.slice(1);
          state = 'row';
          continue;
        }
        if (pending[0] === ']') {
          pending = pending.slice(1);
          state = 'suffix';
          continue;
        }
        throw new Error('The telemetry series contains an invalid separator.');
      }
      if (state === 'suffix') {
        pending = pending.trimStart();
        if (!pending) return;
        if (pending[0] !== '}') throw new Error('The telemetry series format is unsupported.');
        pending = pending.slice(1);
        state = 'done';
      }
      if (state === 'done') {
        if (pending.trim()) throw new Error('The telemetry series contains trailing data.');
        pending = '';
        return;
      }
    }
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      consume();
    }
    pending += decoder.decode();
    consume();
    if (state !== 'done') throw new Error('The telemetry series is incomplete.');
    return parseSeries({ schema_version: 2, samples }, artifact);
  } finally {
    reader.releaseLock();
  }
}

function selectSeries(parsed, seriesId) {
  const definition = parsed.series.find((candidate) => candidate.id === seriesId);
  if (!definition?.available) {
    throw new Error('The selected telemetry series is unavailable.');
  }
  const seriesIndex = parsed.series.indexOf(definition);
  return {
    ...definition,
    samples: parsed.rows.map((row) => ({
      timeNs: row.timeNs,
      timeSeconds: row.timeSeconds,
      value: row.values[seriesIndex],
    })),
  };
}

function sampleAtOrBefore(samples, globalTimeSeconds) {
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (samples[middle].timeSeconds <= globalTimeSeconds) {
      low = middle + 1;
    } else {
      high = middle;
    }
  }
  return low === 0 ? null : samples[low - 1];
}

function cursorFraction(globalTimeSeconds, durationSeconds) {
  if (!(durationSeconds > 0)) return 0;
  return Math.min(Math.max(globalTimeSeconds / durationSeconds, 0), 1);
}

function timeFromPlotPosition(clientX, plotLeft, plotWidth, durationSeconds) {
  if (!(plotWidth > 0) || !(durationSeconds > 0)) return 0;
  const fraction = Math.min(Math.max((clientX - plotLeft) / plotWidth, 0), 1);
  return fraction * durationSeconds;
}

function snappedCursorPosition(
  globalTimeSeconds,
  durationSeconds,
  plotLeft,
  plotWidth,
  devicePixelRatio,
) {
  const ratio = devicePixelRatio > 0 ? devicePixelRatio : 1;
  const raw = plotLeft + cursorFraction(globalTimeSeconds, durationSeconds) * plotWidth;
  return Math.round(raw * ratio) / ratio;
}

function traceSegments(samples) {
  const segments = [];
  let current = [];
  samples.forEach((sample) => {
    if (sample.value === null) {
      if (current.length) segments.push(current);
      current = [];
      return;
    }
    current.push(sample);
  });
  if (current.length) segments.push(current);
  return segments;
}

// Break the displayed trace across observed timestamp pauses; preserve all
// recorded points. The same conservative cadence rule is used by catalog scans.
function timestampGapSamples(samples) {
  const intervals = [];
  for (let i = 1; i < samples.length && intervals.length < 1024; i++) {
    const delta = samples[i].timeSeconds - samples[i - 1].timeSeconds;
    if (delta > 0) intervals.push(delta);
  }
  if (intervals.length < 20) return samples;
  intervals.sort((a, b) => a - b);
  const middle = Math.floor(intervals.length / 2);
  const cadence =
    intervals.length % 2 ? intervals[middle] : (intervals[middle - 1] + intervals[middle]) / 2;
  const threshold = Math.max(1, cadence * 20);
  let display = null;
  for (let i = 1; i < samples.length; i++) {
    if (samples[i].timeSeconds - samples[i - 1].timeSeconds >= threshold) {
      if (!display) display = samples.slice(0, i);
      display.push({
        timeNs: samples[i - 1].timeNs + 1n,
        timeSeconds: samples[i - 1].timeSeconds + 1e-9,
        value: null,
      });
    }
    if (display) display.push(samples[i]);
  }
  return display ?? samples;
}

// A display-only, conservative envelope: brief excursions at least ten times
// the usual magnitude/range become gaps. Keep the original samples for inspection.
function extremeSpikeGaps(samples) {
  const reference = [];
  const stride = Math.max(1, Math.ceil(samples.length / 4096));
  for (let index = 0; index < samples.length; index += stride) {
    if (samples[index].value !== null) reference.push(samples[index].value);
  }
  if (reference.length < 20) return { samples, spikes: [], gaps: [] };
  reference.sort((a, b) => a - b);
  const low = reference[Math.floor((reference.length - 1) * 0.1)];
  const high = reference[Math.ceil((reference.length - 1) * 0.9)];
  const margin = Math.max(high - low, Math.abs(low), Math.abs(high), 0.001) * 10;
  const outside = (sample) =>
    sample.value !== null && (sample.value < low - margin || sample.value > high + margin);
  const spikes = [];
  const gaps = [];
  let display = samples;
  for (let index = 0; index < samples.length; index += 1) {
    if (!outside(samples[index])) continue;
    const first = index;
    while (index + 1 < samples.length && outside(samples[index + 1])) index += 1;
    const next = samples[index + 1];
    const previous = samples[first - 1];
    // Require nearby ordinary finite data. Sustained changes and
    // excursions bordering missing data remain visible as recorded.
    if (
      (previous && previous.value === null) ||
      (next && next.value === null) ||
      (!previous && !next) ||
      (!next && samples[index].timeSeconds - previous.timeSeconds > 1) ||
      (next ?? samples[index]).timeSeconds - samples[first].timeSeconds > 1
    )
      continue;
    if (display === samples) display = samples.slice();
    for (let spike = first; spike <= index; spike += 1) {
      spikes.push(samples[spike]);
      display[spike] = { ...samples[spike], value: null };
    }
    gaps.push({
      start: (previous ?? samples[first]).timeSeconds,
      end: (next ?? samples[index]).timeSeconds,
      spikes: samples.slice(first, index + 1),
    });
  }
  return { samples: display, spikes, gaps };
}

function visibleSpikes(spikes, start, end, pixelWidth) {
  if (!(end > start)) return [];
  const buckets = new Map();
  const width = Math.max(1, Math.ceil(pixelWidth));
  let low = 0;
  let high = spikes.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (spikes[middle].timeSeconds < start) low = middle + 1;
    else high = middle;
  }
  for (let index = low; index < spikes.length; index += 1) {
    const spike = spikes[index];
    if (spike.timeSeconds > end) break;
    const column = Math.min(
      width - 1,
      Math.floor(((spike.timeSeconds - start) / (end - start)) * width),
    );
    const previous = buckets.get(column);
    if (!previous || Math.abs(spike.value) > Math.abs(previous.value)) buckets.set(column, spike);
  }
  return [...buckets.values()];
}

function visibleTraceSegments(samples, start, end, pixelWidth) {
  if (
    !samples.length ||
    !(end > start) ||
    samples[0].timeSeconds > end ||
    samples.at(-1).timeSeconds < start
  )
    return [];
  let low = 0;
  let high = samples.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (samples[middle].timeSeconds < start) low = middle + 1;
    else high = middle;
  }
  const first = Math.max(0, low - 1);
  low = first;
  high = samples.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (samples[middle].timeSeconds <= end) low = middle + 1;
    else high = middle;
  }
  const last = Math.min(samples.length, low + 1);
  const width = Math.max(1, Math.ceil(pixelWidth));
  const segments = [];
  const smallSegments = new Map();
  let segment = [];
  let bucket = null;
  const columnFor = (sample) =>
    Math.min(
      width - 1,
      Math.max(0, Math.floor(((sample.timeSeconds - start) / (end - start)) * width)),
    );
  const flushBucket = () => {
    if (!bucket) return;
    const points = [bucket.first, bucket.minimum, bucket.maximum, bucket.last];
    points.sort((left, right) => left.index - right.index);
    for (const point of points) {
      if (segment.at(-1) !== point.sample) segment.push(point.sample);
    }
    bucket = null;
  };
  const finishSegment = () => {
    flushBucket();
    if (segment.length) {
      const column = columnFor(segment[0]);
      if (column === columnFor(segment.at(-1))) {
        const prior = smallSegments.get(column);
        if (prior?.count >= 2) {
          // Keep two distinct runs per pixel, then retain later extremes without
          // creating one SVG path or circle for every subpixel gap.
          const points = segments[prior.index].concat(segment);
          let minimum = 0;
          let maximum = 0;
          for (let i = 1; i < points.length; i += 1) {
            if (points[i].value < points[minimum].value) minimum = i;
            if (points[i].value > points[maximum].value) maximum = i;
          }
          const indices = [...new Set([0, minimum, maximum, points.length - 1])].sort(
            (a, b) => a - b,
          );
          segments[prior.index] = indices.map((index) => points[index]);
        } else {
          segments.push(segment);
          smallSegments.set(column, { count: (prior?.count ?? 0) + 1, index: segments.length - 1 });
        }
      } else {
        segments.push(segment);
      }
    }
    segment = [];
  };
  for (let index = first; index < last; index += 1) {
    const sample = samples[index];
    if (sample.value === null) {
      finishSegment();
      continue;
    }
    const column = columnFor(sample);
    const point = { index, sample };
    if (bucket && bucket.column !== column) flushBucket();
    if (!bucket) {
      bucket = { column, first: point, minimum: point, maximum: point, last: point };
    } else {
      bucket.last = point;
      if (sample.value < bucket.minimum.sample.value) bucket.minimum = point;
      if (sample.value > bucket.maximum.sample.value) bucket.maximum = point;
    }
  }
  finishSegment();
  return segments;
}

export default Object.freeze({
  parseSeries,
  parseSeriesStream,
  selectSeries,
  sampleAtOrBefore,
  cursorFraction,
  timeFromPlotPosition,
  snappedCursorPosition,
  traceSegments,
  timestampGapSamples,
  extremeSpikeGaps,
  visibleSpikes,
  visibleTraceSegments,
});
