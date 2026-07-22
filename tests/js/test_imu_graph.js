"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const ImuGraph = require("../../src/rosbag_analyser/web/imu_graph.js");

function artifact(overrides = {}) {
  return {
    coverage_start_ns: "100000000",
    coverage_end_ns: "400000000",
    delivered_sample_count: "4",
    finite_sample_count: "3",
    non_finite_sample_count: "1",
    minimum_value: -2,
    maximum_value: 3,
    ...overrides,
  };
}

test("parses ordered decimal nanoseconds and explicit null gaps", () => {
  const parsed = ImuGraph.parseSeries(
    {
      schema_version: 1,
      samples: [
        ["100000000", 1],
        ["200000000", null],
        ["300000000", -2],
        ["400000000", 3],
      ],
    },
    artifact(),
  );

  assert.equal(parsed.coverageStart, 0.1);
  assert.equal(parsed.coverageEnd, 0.4);
  assert.equal(ImuGraph.traceSegments(parsed.samples).length, 2);
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

test("cursor always maps to the global recording duration", () => {
  assert.equal(ImuGraph.cursorFraction(-1, 10), 0);
  assert.equal(ImuGraph.cursorFraction(5, 10), 0.5);
  assert.equal(ImuGraph.cursorFraction(11, 10), 1);
});

test("rejects unordered time, invalid values, and mismatched coverage", () => {
  assert.throws(
    () => ImuGraph.parseSeries(
      { schema_version: 1, samples: [["200000000", 1], ["100000000", 2]] },
      artifact({
        coverage_start_ns: "200000000",
        coverage_end_ns: "100000000",
        delivered_sample_count: "2",
        finite_sample_count: "2",
        non_finite_sample_count: "0",
      }),
    ),
    /not ordered/,
  );
  assert.throws(
    () => ImuGraph.parseSeries(
      { schema_version: 1, samples: [["100000000", "NaN"]] },
      artifact({
        coverage_end_ns: "100000000",
        delivered_sample_count: "1",
        finite_sample_count: "1",
        non_finite_sample_count: "0",
      }),
    ),
    /invalid value/,
  );
});
