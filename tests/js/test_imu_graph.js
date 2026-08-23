"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

const definitions = [
  ["angular_velocity_x", "angular_velocity.x", "IMU angular_velocity.x (rad/s)", "rad/s"],
  ["angular_velocity_y", "angular_velocity.y", "IMU angular_velocity.y (rad/s)", "rad/s"],
  ["angular_velocity_z", "angular_velocity.z", "IMU angular_velocity.z (rad/s)", "rad/s"],
  ["linear_acceleration_x", "linear_acceleration.x", "IMU linear_acceleration.x (m/s²)", "m/s²"],
  ["linear_acceleration_y", "linear_acceleration.y", "IMU linear_acceleration.y (m/s²)", "m/s²"],
  ["linear_acceleration_z", "linear_acceleration.z", "IMU linear_acceleration.z (m/s²)", "m/s²"],
];

function artifact(samples, overrides = {}) {
  return {
    coverage_start_ns: samples[0][0],
    coverage_end_ns: samples.at(-1)[0],
    delivered_sample_count: String(samples.length),
    default_series_id: "angular_velocity_z",
    series: definitions.map(([id, component, displayLabel, units], index) => {
      const values = samples.map((sample) => sample[index + 1]);
      const finite = values.filter((value) => value !== null);
      return {
        id,
        component,
        display_label: displayLabel,
        units,
        column_index: index + 1,
        finite_sample_count: String(finite.length),
        non_finite_sample_count: String(values.length - finite.length),
        minimum_value: finite.length ? Math.min(...finite) : null,
        maximum_value: finite.length ? Math.max(...finite) : null,
        available: finite.length > 0,
      };
    }),
    ...overrides,
  };
}

function payload(samples) {
  return { schema_version: 2, samples };
}

test("parses the fixed bundle and preserves explicit gaps per selected channel", () => {
  const samples = [
    ["100000000", 10, 20, 1, 40, 50, 60],
    ["200000000", 11, 21, null, 41, 51, 61],
    ["300000000", 12, 22, -2, 42, 52, 62],
    ["400000000", 13, 23, 3, 43, 53, 63],
  ];
  const parsed = ImuGraph.parseSeries(payload(samples), artifact(samples));
  const selected = ImuGraph.selectSeries(parsed, "angular_velocity_z");

  assert.equal(parsed.coverageStart, 0.1);
  assert.equal(parsed.coverageEnd, 0.4);
  assert.equal(parsed.series.length, 6);
  assert.deepEqual(selected.samples.map((sample) => sample.value), [1, null, -2, 3]);
  assert.equal(ImuGraph.traceSegments(selected.samples).length, 2);
});

test("selecting another channel uses the same timestamps without reparsing", () => {
  const samples = [
    ["100000000", 1, 2, 3, 4, 5, 6],
    ["200000000", 7, 8, 9, 10, 11, 12],
  ];
  const parsed = ImuGraph.parseSeries(payload(samples), artifact(samples));
  const selected = ImuGraph.selectSeries(parsed, "linear_acceleration_y");

  assert.equal(selected.component, "linear_acceleration.y");
  assert.equal(selected.units, "m/s²");
  assert.deepEqual(selected.samples.map((sample) => sample.value), [5, 11]);
  assert.throws(
    () => ImuGraph.selectSeries(parsed, "orientation_x"),
    /unavailable/,
  );
});

test("current lookup uses the last duplicate at or before global time", () => {
  const samples = [
    { timeSeconds: 0.1, value: 1 },
    { timeSeconds: 0.2, value: 2 },
    { timeSeconds: 0.2, value: 3 },
    { timeSeconds: 0.4, value: 4 },
  ];

  assert.equal(ImuGraph.sampleAtOrBefore(samples, 0.05), null);
  assert.equal(ImuGraph.sampleAtOrBefore(samples, 0.2).value, 3);
  assert.equal(ImuGraph.sampleAtOrBefore(samples, 0.35).value, 3);
  assert.equal(ImuGraph.sampleAtOrBefore(samples, 0.4).value, 4);
});

test("global cursor and graph pointer positions clamp and pixel-snap", () => {
  assert.equal(ImuGraph.cursorFraction(-1, 10), 0);
  assert.equal(ImuGraph.cursorFraction(5, 10), 0.5);
  assert.equal(ImuGraph.cursorFraction(11, 10), 1);
  assert.equal(ImuGraph.timeFromPlotPosition(25, 0, 100, 20), 5);
  assert.equal(ImuGraph.timeFromPlotPosition(-10, 0, 100, 20), 0);
  assert.equal(ImuGraph.timeFromPlotPosition(110, 0, 100, 20), 20);
  assert.equal(ImuGraph.snappedCursorPosition(5, 10, 10, 101, 2), 60.5);
});

test("rejects unordered time, invalid values, and mismatched channel metadata", () => {
  const unordered = [
    ["200000000", 1, 1, 1, 1, 1, 1],
    ["100000000", 2, 2, 2, 2, 2, 2],
  ];
  assert.throws(
    () => ImuGraph.parseSeries(payload(unordered), artifact(unordered)),
    /not ordered/,
  );

  const invalid = [["100000000", 1, 1, "NaN", 1, 1, 1]];
  const invalidArtifact = artifact(
    [["100000000", 1, 1, 1, 1, 1, 1]],
  );
  assert.throws(
    () => ImuGraph.parseSeries(payload(invalid), invalidArtifact),
    /invalid value/,
  );

  const valid = [["100000000", 1, 2, 3, 4, 5, 6]];
  const mismatched = artifact(valid);
  mismatched.series[0].maximum_value = 99;
  assert.throws(
    () => ImuGraph.parseSeries(payload(valid), mismatched),
    /declared coverage/,
  );
});
