from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import struct
from types import SimpleNamespace

import pytest

from conftest import create_recording, inventory, metadata_document
from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.catalog.metadata import TopicFact
from rosbag_analyser.catalog.scanner import CatalogScanner
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.encoder_series import (
    ENCODER_COMPONENT, ENCODER_MESSAGE_TYPE, ENCODER_SERIES_DEFINITIONS,
    EncoderSourceResolver, EncoderSeriesService,
)
from rosbag_analyser.job_control import JobCanceled
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord, JobRecord, ProcessingComponent, ProcessingSourceRecord, ProcessingState, RequestOutcome,
)
from rosbag_analyser.preparation_planner import PreparationPlanner
from rosbag_analyser.processors.encoder_series import (
    EncoderSeriesProcessor, EncoderSeriesProcessingError, deserialize_encoder_values,
)
from rosbag_analyser.worker import SerialWorker

TOPIC = "/rover/encoders"
START = 1_700_000_000_000_000_000


def encoder_payload(values, *, endian="<", frame="", dimensions=(), offset=0, nanosec=2):
    # Synthetic CDR writer follows the documented nested Header/MultiArray schema.
    data = bytearray(b"\x00\x01\x00\x00" if endian == "<" else b"\x00\x00\x00\x00")
    def scalar(fmt, value, alignment):
        data.extend(b"\x00" * ((-(len(data) - 4)) % alignment))
        data.extend(struct.pack(endian + fmt, value))
    def string(value):
        encoded = value.encode() + b"\x00"
        scalar("I", len(encoded), 4)
        data.extend(encoded)
    scalar("i", 17, 4)
    scalar("I", nanosec, 4)
    string(frame)
    scalar("I", len(dimensions), 4)
    for label, size, stride in dimensions:
        string(label)
        scalar("I", size, 4)
        scalar("I", stride, 4)
    scalar("I", offset, 4)
    scalar("I", len(values), 4)
    for value in values:
        scalar("d", value, 8)
    return bytes(data)


@pytest.mark.parametrize("endian", ["<", ">"])
@pytest.mark.parametrize("frame", ["", "rover", "wheel_frame_with_padding"])
def test_decodes_documented_custom_schema_with_alignment(endian, frame):
    values = [-12.5, 18.25, 3, 4, 5, 6]
    payload = encoder_payload(values, endian=endian, frame=frame, dimensions=[("wheels", 6, 6)])
    assert deserialize_encoder_values(payload) == tuple(values)


@pytest.mark.parametrize("payload", [
    b"", b"\x00\x07\x00\x00", encoder_payload([1] * 5), encoder_payload([1] * 7),
    encoder_payload([1] * 6)[:-1], encoder_payload([1] * 6) + b"garbage",
    encoder_payload([1] * 6, offset=1), encoder_payload([1] * 6, nanosec=1_000_000_000),
    encoder_payload([1] * 6, dimensions=[("bad", 5, 5)]), b"x" * 4097,
])
def test_rejects_truncated_wrong_width_and_unsupported_custom_messages(payload):
    with pytest.raises(ValueError):
        deserialize_encoder_values(payload)


class Repository:
    def __init__(self, source):
        self.source = source
        self.job = None
        self.artifact = None
        self.failures = []
        self.requests = 0
    def get_source(self, recording_id):
        return self.source if recording_id == self.source.id else None
    def get_current_state(self, recording_id, kind, identity):
        artifact = self.artifact
        if artifact and (artifact.kind != kind or artifact.cache_identity != identity):
            artifact = None
        return ProcessingState(artifact=artifact, active_job=self.job, latest_failed_job=None)
    def request_job(self, recording_id, kind, identity, **kwargs):
        self.requests += 1
        self.job = JobRecord(1, recording_id, kind, identity, "queued", datetime.now(timezone.utc), None, None, None, None)
        return RequestOutcome(job=self.job)
    def claim_next_job(self):
        job, self.job = self.job, None
        return None if job is None else replace(job, state="running")
    def complete_job(self, job_id, artifact):
        self.artifact = ArtifactRecord(id=9, **artifact.__dict__, created_at=datetime.now(timezone.utc))
    def fail_job(self, job_id, code, message):
        self.failures.append((code, message))
    def get_current_artifact_for_delivery(self, recording_id, kind, artifact_id, planner_identity):
        a = self.artifact
        return a if a and (a.recording_id, a.kind, a.id, planner_identity) == (recording_id, kind, artifact_id, "f" * 64) else None


def source_fixture(tmp_path, payloads=None):
    archive = tmp_path / "archive"
    derived = tmp_path / "derived"
    archive.mkdir()
    derived.mkdir()
    payloads = payloads or [encoder_payload([8, 18, 8, 18, 8, 18]),
                            encoder_payload([-2, 4, math.nan, 6, 7, 8]),
                            encoder_payload([11, 12, 13, 14, 15, 16])]
    document = metadata_document("run_0.db3")["rosbag2_bagfile_information"]
    document["topics_with_message_count"] = [{"topic_metadata": {"name": TOPIC, "type": ENCODER_MESSAGE_TYPE,
        "serialization_format": "cdr", "offered_qos_profiles": ""}, "message_count": len(payloads)}]
    recording = create_recording(archive, "run", metadata_overrides=document)
    database = recording / "run_0.db3"
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO topics VALUES (1, ?, ?, 'cdr', '')", (TOPIC, ENCODER_MESSAGE_TYPE))
        connection.executemany("INSERT INTO messages VALUES (?, 1, ?, ?)",
            [(i + 1, START + [100, 100, 300][i], p) for i, p in enumerate(payloads)])
    metadata = recording / "metadata.yaml"
    def component(p):
        stat = p.stat()
        return ProcessingComponent(str(p.relative_to(archive)), stat.st_size, stat.st_mtime_ns, "readable")
    source = ProcessingSourceRecord(11, "run", START, 2_500_000_000, "readable", component(metadata), component(database))
    repository = Repository(source)
    resolver = EncoderSourceResolver(archive, repository)
    store = ArtifactStore(derived, Path("/usr/bin/ffmpeg"), Path("/usr/bin/ffprobe"), "encoder_series")
    return archive, repository, resolver, store


def test_encoder_job_preserves_six_wheels_nulls_duplicates_and_source_inventory(tmp_path):
    archive, repository, resolver, store = source_fixture(tmp_path)
    before = inventory(archive)
    service = EncoderSeriesService(resolver, repository, store, "f" * 64)
    assert service.get_state(11).state == "not_requested"
    assert repository.requests == 0
    assert service.request(11).state == "queued"
    worker = SerialWorker(repository, None, None, store, "", "test", encoder_resolver=resolver,
                          encoder_processor=EncoderSeriesProcessor(), encoder_artifact_store=store)
    assert worker.run_once()
    assert not repository.failures
    artifact = repository.artifact
    assert artifact.kind == "encoder_series"
    assert artifact.manifest["processor_version"] == "encoder-series-v1"
    assert artifact.manifest["source"]["default_component"] == ENCODER_COMPONENT
    assert artifact.manifest["source"]["message_type"] == ENCODER_MESSAGE_TYPE
    assert [s["component"] for s in artifact.manifest["series"]] == [d.component for d in ENCODER_SERIES_DEFINITIONS]
    assert [s["units"] for s in artifact.manifest["series"]] == ["RPM"] * 6
    assert artifact.manifest["samples"]["duplicate_timestamps"] == 1
    assert artifact.manifest["timing"]["timestamp_provenance"] == "ros_record_timestamp"
    document = json.loads((store.derived_root / artifact.output_relative_path).read_text())
    assert document["samples"] == [["100", 8, 18, 8, 18, 8, 18], ["100", -2, 4, None, 6, 7, 8], ["300", 11, 12, 13, 14, 15, 16]]
    assert service.get_state(11).state == "ready"
    assert service.request(11).state == "ready"
    assert repository.requests == 1
    assert service.resolve_series(11, 999) is None
    opened, _ = service.resolve_series(11, artifact.id)
    import os
    os.close(opened.descriptor)
    assert inventory(archive) == before


def test_malformed_encoder_job_is_failed_and_never_published(tmp_path):
    archive, repository, resolver, store = source_fixture(tmp_path, [encoder_payload([1] * 5)])
    before = inventory(archive)
    EncoderSeriesService(resolver, repository, store, "f" * 64).request(11)
    worker = SerialWorker(repository, None, None, store, "", "test", encoder_resolver=resolver,
                          encoder_processor=EncoderSeriesProcessor(), encoder_artifact_store=store)
    assert worker.run_once()
    assert repository.artifact is None
    assert repository.failures[0][0] == "encoder_deserialization_failed"
    assert not list(store.work_root.glob("*"))
    assert inventory(archive) == before


def test_encoder_control_cancels_before_publication(tmp_path):
    archive, repository, resolver, store = source_fixture(tmp_path)
    class Cancel:
        def checkpoint(self, *args, **kwargs): raise JobCanceled("test")
    before = inventory(archive)
    with pytest.raises(JobCanceled):
        EncoderSeriesProcessor().process(resolver.resolve(11).descriptor, store.derived_root / "canceled.json", control=Cancel())
    assert inventory(archive) == before


def test_encoder_ambiguity_is_optional_and_configuration_only_changes_encoder_identity(tmp_path):
    archive, repository, resolver, store = source_fixture(tmp_path)
    recording = CatalogScanner(archive).scan().recordings[0]
    def planner(preference=""):
        return PreparationPlanner(front_topic="", imu_topic="", imu_component="angular_velocity.z",
            profile=V0_PREVIEW_PROFILE, encoder_identity="test", encoder_topic=preference)
    first, second = planner(), planner(TOPIC)
    for kind in ["front_preview", "topdown_preview", "imu_series", "ai_description"]:
        assert first.planner_identity(kind) == second.planner_identity(kind)
    assert first.planner_identity("encoder_series") != second.planner_identity("encoder_series")
    target = {t.kind: t for t in first.plan_recording(11, recording)}["encoder_series"]
    assert target.target_state == "available"
    assert target.cache_identity == resolver.resolve(11).descriptor.cache_identity
    facts = recording.preparation_facts
    other = TopicFact("/other/encoders", ENCODER_MESSAGE_TYPE, "cdr", 10)
    ambiguous = replace(recording, preparation_facts=replace(facts, metadata=replace(facts.metadata, topics=(*facts.metadata.topics, other))))
    target = {t.kind: t for t in first.plan_recording(11, ambiguous)}["encoder_series"]
    assert target.target_state == "unavailable"
    assert target.diagnostic.code == "encoder_topic_unavailable"
    assert {t.kind: t for t in second.plan_recording(11, ambiguous)}["encoder_series"].target_state == "available"


def test_source_change_and_symlink_are_rejected(tmp_path):
    archive, repository, resolver, store = source_fixture(tmp_path)
    database = archive / "run/run_0.db3"
    descriptor = resolver.resolve(11).descriptor
    with database.open("ab") as file: file.write(b"changed")
    with pytest.raises(EncoderSeriesProcessingError, match="changed"):
        EncoderSeriesProcessor().process(descriptor, store.derived_root / "changed.json")
    assert resolver.resolve(11).descriptor is None
    replacement = tmp_path / "external.db3"
    database.rename(replacement)
    database.symlink_to(replacement)
    assert resolver.resolve(11).descriptor is None


def test_malformed_derived_encoder_data_has_encoder_diagnostic(tmp_path):
    from rosbag_analyser.artifact_store import SeriesColumnExpectation
    store = ArtifactStore(tmp_path, Path("/usr/bin/ffmpeg"), Path("/usr/bin/ffprobe"), "encoder_series")
    path = tmp_path / "bad-series.json"
    path.write_text('{"schema_version":2,"samples":[bad]}')
    with pytest.raises(ArtifactStoreError) as raised:
        store.validate_series(path, expected_schema_version=2, expected_sample_count=1,
            expected_columns=tuple(SeriesColumnExpectation(d.id, 1, 0, 1, 1) for d in ENCODER_SERIES_DEFINITIONS),
            expected_coverage_start_ns=0, expected_coverage_end_ns=0)
    assert raised.value.code == "encoder_series_validation_failed"
