"use strict";

const { performance } = require("node:perf_hooks");
const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

const sampleCount = 76_000;
const startNs = 0n;
const periodNs = 10_000_000n;
const samples = Array.from({ length: sampleCount }, (_, index) => [
  String(startNs + BigInt(index) * periodNs),
  ...Array.from(
    { length: 6 },
    (_, channel) => (
      index % 997 === 0 ? null : Math.sin(index / 180 + channel) * 1.75
    ),
  ),
]);
const finiteCount = samples.reduce(
  (count, sample) => count + (sample[1] === null ? 0 : 1),
  0,
);
const artifact = {
  delivered_sample_count: String(sampleCount),
  coverage_start_ns: samples[0][0],
  coverage_end_ns: samples.at(-1)[0],
  default_series_id: "angular_velocity_z",
  series: [
    ["angular_velocity_x", "angular_velocity.x", "rad/s"],
    ["angular_velocity_y", "angular_velocity.y", "rad/s"],
    ["angular_velocity_z", "angular_velocity.z", "rad/s"],
    ["linear_acceleration_x", "linear_acceleration.x", "m/s²"],
    ["linear_acceleration_y", "linear_acceleration.y", "m/s²"],
    ["linear_acceleration_z", "linear_acceleration.z", "m/s²"],
  ].map(([id, component, units], index) => ({
    id,
    component,
    display_label: `IMU ${component} (${units})`,
    units,
    column_index: index + 1,
    finite_sample_count: String(finiteCount),
    non_finite_sample_count: String(sampleCount - finiteCount),
    minimum_value: Math.min(...samples.filter((sample) => sample[index + 1] !== null).map((sample) => sample[index + 1])),
    maximum_value: Math.max(...samples.filter((sample) => sample[index + 1] !== null).map((sample) => sample[index + 1])),
    available: true,
  })),
};

const payloadStart = performance.now();
const payload = JSON.stringify({ schema_version: 2, samples });
const payloadMilliseconds = performance.now() - payloadStart;

const parseStart = performance.now();
const series = ImuGraph.parseSeries(JSON.parse(payload), artifact);
const parseMilliseconds = performance.now() - parseStart;

const segmentStart = performance.now();
const selected = ImuGraph.selectSeries(series, series.defaultSeriesId);
const segments = ImuGraph.traceSegments(selected.samples);
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
  ImuGraph.sampleAtOrBefore(selected.samples, target);
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
