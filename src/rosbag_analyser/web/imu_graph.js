"use strict";

function parseDecimalNanoseconds(value) {
  if (typeof value !== "string" || !/^-?(0|[1-9]\d*)$/.test(value)) {
    throw new Error("The IMU series contains an invalid timestamp.");
  }
  const nanoseconds = BigInt(value);
  const limit = BigInt(Number.MAX_SAFE_INTEGER);
  if (nanoseconds < -limit || nanoseconds > limit) {
    throw new Error("The IMU series timestamp is outside the browser range.");
  }
  return nanoseconds;
}

function parseCount(value, label) {
  if (typeof value !== "string" || !/^\d+$/.test(value)) {
    throw new Error(`The IMU ${label} count is invalid.`);
  }
  const count = Number(value);
  if (!Number.isSafeInteger(count)) {
    throw new Error(`The IMU ${label} count is outside the browser range.`);
  }
  return count;
}

function parseSeries(document, artifact) {
  if (
    !document
    || typeof document !== "object"
    || Array.isArray(document)
    || document.schema_version !== 2
    || !Array.isArray(document.samples)
    || !Array.isArray(artifact.series)
    || artifact.series.length === 0
  ) {
    throw new Error("The IMU series format is unsupported.");
  }
  const coverageStartNs = parseDecimalNanoseconds(artifact.coverage_start_ns);
  const coverageEndNs = parseDecimalNanoseconds(artifact.coverage_end_ns);
  const deliveredCount = parseCount(artifact.delivered_sample_count, "delivered sample");
  if (document.samples.length !== deliveredCount) {
    throw new Error("The IMU series sample count does not match its metadata.");
  }

  const seenIds = new Set();
  const seenColumns = new Set();
  const series = artifact.series.map((definition) => {
    if (
      !definition
      || typeof definition !== "object"
      || Array.isArray(definition)
      || typeof definition.id !== "string"
      || !/^[a-z][a-z0-9_]*$/.test(definition.id)
      || seenIds.has(definition.id)
      || typeof definition.component !== "string"
      || typeof definition.display_label !== "string"
      || typeof definition.units !== "string"
      || !Number.isInteger(definition.column_index)
      || definition.column_index < 1
      || definition.column_index > artifact.series.length
      || seenColumns.has(definition.column_index)
      || typeof definition.available !== "boolean"
    ) {
      throw new Error("The IMU series definition is invalid.");
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
      finiteCount + nonFiniteCount !== deliveredCount
      || definition.available !== (finiteCount > 0)
      || (
        finiteCount > 0
        && (
          typeof definition.minimum_value !== "number"
          || !Number.isFinite(definition.minimum_value)
          || typeof definition.maximum_value !== "number"
          || !Number.isFinite(definition.maximum_value)
          || definition.minimum_value > definition.maximum_value
        )
      )
      || (
        finiteCount === 0
        && (definition.minimum_value !== null || definition.maximum_value !== null)
      )
    ) {
      throw new Error("The IMU series definition does not match its samples.");
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
    throw new Error("The IMU series columns are invalid.");
  }

  let previousNs = null;
  const actualFinite = series.map(() => 0);
  const actualNonFinite = series.map(() => 0);
  const actualMinimum = series.map(() => null);
  const actualMaximum = series.map(() => null);
  const rows = document.samples.map((sample) => {
    if (!Array.isArray(sample) || sample.length !== series.length + 1) {
      throw new Error("The IMU series contains an invalid sample.");
    }
    const timeNs = parseDecimalNanoseconds(sample[0]);
    if (previousNs !== null && timeNs < previousNs) {
      throw new Error("The IMU series timestamps are not ordered.");
    }
    previousNs = timeNs;
    const values = series.map((definition, index) => {
      const value = sample[definition.columnIndex];
      if (value === null) {
        actualNonFinite[index] += 1;
        return null;
      }
      if (typeof value !== "number" || !Number.isFinite(value)) {
        throw new Error("The IMU series contains an invalid value.");
      }
      actualFinite[index] += 1;
      actualMinimum[index] = actualMinimum[index] === null
        ? value
        : Math.min(actualMinimum[index], value);
      actualMaximum[index] = actualMaximum[index] === null
        ? value
        : Math.max(actualMaximum[index], value);
      return value;
    });
    return {
      timeNs,
      timeSeconds: Number(timeNs) / 1e9,
      values,
    };
  });
  if (
    rows.length === 0
    || rows[0].timeNs !== coverageStartNs
    || rows[rows.length - 1].timeNs !== coverageEndNs
    || series.some((definition, index) => (
      actualFinite[index] !== definition.finiteCount
      || actualNonFinite[index] !== definition.nonFiniteCount
      || actualMinimum[index] !== definition.minimumValue
      || actualMaximum[index] !== definition.maximumValue
    ))
  ) {
    throw new Error("The IMU series does not match its declared coverage.");
  }
  const defaultSeries = series.find(
    (definition) => definition.id === artifact.default_series_id,
  );
  if (!defaultSeries?.available) {
    throw new Error("The default IMU series is unavailable.");
  }
  return {
    rows,
    series,
    defaultSeriesId: defaultSeries.id,
    coverageStart: Number(coverageStartNs) / 1e9,
    coverageEnd: Number(coverageEndNs) / 1e9,
  };
}

function selectSeries(parsed, seriesId) {
  const definition = parsed.series.find((candidate) => candidate.id === seriesId);
  if (!definition?.available) {
    throw new Error("The selected IMU series is unavailable.");
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

const ImuGraph = Object.freeze({
  parseSeries,
  selectSeries,
  sampleAtOrBefore,
  cursorFraction,
  timeFromPlotPosition,
  snappedCursorPosition,
  traceSegments,
});

if (typeof window !== "undefined") window.ImuGraph = ImuGraph;
if (typeof module !== "undefined" && module.exports) module.exports = ImuGraph;
