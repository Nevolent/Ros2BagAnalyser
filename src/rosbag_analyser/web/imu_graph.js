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
    || document.schema_version !== 1
    || !Array.isArray(document.samples)
  ) {
    throw new Error("The IMU series format is unsupported.");
  }
  const coverageStartNs = parseDecimalNanoseconds(artifact.coverage_start_ns);
  const coverageEndNs = parseDecimalNanoseconds(artifact.coverage_end_ns);
  const deliveredCount = parseCount(artifact.delivered_sample_count, "delivered sample");
  const finiteCount = parseCount(artifact.finite_sample_count, "finite sample");
  const nonFiniteCount = parseCount(
    artifact.non_finite_sample_count,
    "non-finite sample",
  );
  if (document.samples.length !== deliveredCount) {
    throw new Error("The IMU series sample count does not match its metadata.");
  }

  let previousNs = null;
  let actualFinite = 0;
  let actualNonFinite = 0;
  const samples = document.samples.map((sample) => {
    if (!Array.isArray(sample) || sample.length !== 2) {
      throw new Error("The IMU series contains an invalid sample.");
    }
    const timeNs = parseDecimalNanoseconds(sample[0]);
    if (previousNs !== null && timeNs < previousNs) {
      throw new Error("The IMU series timestamps are not ordered.");
    }
    previousNs = timeNs;
    const value = sample[1];
    if (value === null) {
      actualNonFinite += 1;
    } else if (typeof value === "number" && Number.isFinite(value)) {
      actualFinite += 1;
    } else {
      throw new Error("The IMU series contains an invalid value.");
    }
    return {
      timeNs,
      timeSeconds: Number(timeNs) / 1e9,
      value,
    };
  });
  if (
    samples.length === 0
    || samples[0].timeNs !== coverageStartNs
    || samples[samples.length - 1].timeNs !== coverageEndNs
    || actualFinite !== finiteCount
    || actualNonFinite !== nonFiniteCount
  ) {
    throw new Error("The IMU series does not match its declared coverage.");
  }
  return {
    samples,
    coverageStart: Number(coverageStartNs) / 1e9,
    coverageEnd: Number(coverageEndNs) / 1e9,
    minimumValue: artifact.minimum_value,
    maximumValue: artifact.maximum_value,
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
  sampleAtOrBefore,
  cursorFraction,
  traceSegments,
});

if (typeof window !== "undefined") window.ImuGraph = ImuGraph;
if (typeof module !== "undefined" && module.exports) module.exports = ImuGraph;
