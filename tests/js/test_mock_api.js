"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "../../src/rosbag_analyser/web/mock_api.js"),
  "utf8",
);

function installMock(scenario) {
  const listeners = new Map();
  const window = {
    location: {
      href: `http://test.invalid/?mock=${scenario}`,
      origin: "http://test.invalid",
      assign() {},
    },
    fetch: async () => { throw new Error("Unexpected real request"); },
  };
  const document = {
    readyState: "loading",
    addEventListener(name, callback) { listeners.set(name, callback); },
  };
  vm.runInNewContext(source, {
    window,
    document,
    URL,
    Date,
    Math,
    Array,
    Object,
    Set,
    JSON,
  });
  return window;
}

test("all-ready mock follows catalog, detail, and IMU response shapes", async () => {
  const window = installMock("all-ready");
  const catalog = await (await window.fetch("/api/v1/catalog")).json();
  const recording = catalog.recordings[0];
  assert.equal(recording.outputs.map((output) => output.state).join(","), "ready,ready,ready");

  const detail = await (await window.fetch("/api/v1/recordings/101")).json();
  const imu = await (await window.fetch("/api/recordings/101/imu-series")).json();
  const payload = await (await window.fetch(imu.artifact.data_url)).json();
  assert.equal(detail.analysis_state, "ready");
  assert.equal(imu.artifact.series.length, 6);
  assert.equal(payload.schema_version, 2);
});

test("prepare creates in-memory queued work that is visible in the overview", async () => {
  const window = installMock("all-ready");
  const prepared = await (await window.fetch("/api/v1/recordings/prepare", {
    method: "POST",
    body: JSON.stringify({ recording_ids: [102], output_kinds: ["front_preview"] }),
  })).json();
  const overview = await (await window.fetch("/api/v1/processing/overview")).json();
  assert.equal(prepared.recordings[0].outputs[0].outcome, "queued");
  assert.equal(overview.queued_count, 1);
});

test("unavailable and processing scenarios expose their required states", async () => {
  const unavailable = installMock("topdown-unavailable");
  const unavailableCatalog = await (await unavailable.fetch("/api/v1/catalog")).json();
  assert.equal(unavailableCatalog.recordings[0].outputs[1].state, "unavailable");

  const processing = installMock("processing");
  const overview = await (await processing.fetch("/api/v1/processing/overview")).json();
  assert.equal(overview.current.state, "running");
  assert.equal(overview.current.estimate.status, "available");
});
