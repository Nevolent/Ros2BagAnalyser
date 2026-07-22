"use strict";

const { performance } = require("node:perf_hooks");
const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

const sampleCount = 76_000;
const startNs = 0n;
const periodNs = 10_000_000n;
const samples = Array.from({ length: sampleCount }, (_, index) => [
  String(startNs + BigInt(index) * periodNs),
  index % 997 === 0 ? null : Math.sin(index / 180) * 1.75,
]);
const artifact = {
  delivered_sample_count: String(sampleCount),
  finite_sample_count: String(
    samples.reduce((count, sample) => count + (sample[1] === null ? 0 : 1), 0),
  ),
  non_finite_sample_count: String(
    samples.reduce((count, sample) => count + (sample[1] === null ? 1 : 0), 0),
  ),
  coverage_start_ns: samples[0][0],
  coverage_end_ns: samples.at(-1)[0],
};

const payloadStart = performance.now();
const payload = JSON.stringify({ schema_version: 1, samples });
const payloadMilliseconds = performance.now() - payloadStart;

const parseStart = performance.now();
const series = ImuGraph.parseSeries(JSON.parse(payload), artifact);
const parseMilliseconds = performance.now() - parseStart;

const segmentStart = performance.now();
const segments = ImuGraph.traceSegments(series.samples);
let renderedPoints = 0;
for (const segment of segments) {
  for (const sample of segment) {
    const x = Number(sample.timeNs - startNs) / Number(periodNs * BigInt(sampleCount - 1));
    const y = (sample.value + 1.75) / 3.5;
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new Error("The synthetic render transform produced a non-finite point.");
    }
    renderedPoints += 1;
  }
}
const renderTransformMilliseconds = performance.now() - segmentStart;

const lookupCount = 10_000;
const lookupStart = performance.now();
for (let index = 0; index < lookupCount; index += 1) {
  const target = ((index * 7919) % sampleCount) * Number(periodNs) / 1e9;
  ImuGraph.sampleAtOrBefore(series.samples, target);
}
const lookupMilliseconds = performance.now() - lookupStart;

console.log(
  JSON.stringify({
    sample_count: sampleCount,
    finite_sample_count: renderedPoints,
    trace_segment_count: segments.length,
    payload_bytes: Buffer.byteLength(payload),
    payload_milliseconds: Number(payloadMilliseconds.toFixed(3)),
    parse_milliseconds: Number(parseMilliseconds.toFixed(3)),
    render_transform_milliseconds: Number(renderTransformMilliseconds.toFixed(3)),
    lookup_count: lookupCount,
    lookup_milliseconds: Number(lookupMilliseconds.toFixed(3)),
  }),
);
