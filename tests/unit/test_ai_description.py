from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import numpy as np
import hashlib
from rosbag_analyser.thumbnail import THUMBNAIL_POLICY, thumbnail_cache_identity, png_bytes, thumbnail_frames

from rosbag_analyser.ai_description import (
    DESCRIPTION_POLICY, DESCRIPTION_PLANNER_IDENTITY, description_cache_identity,
    validate_description_result,
)
from rosbag_analyser.artifact_store import ArtifactStore, ArtifactStoreError
from rosbag_analyser.config import V0_PREVIEW_PROFILE
from rosbag_analyser.persistence.processing_repository import (
    ArtifactRecord, CurrentOutputRecord, JobRecord, PreparationTargetRecord,
)
from rosbag_analyser.processors.ai_description import DescriptionProcessor, DescriptionProcessingError
from rosbag_analyser.worker import SerialWorker


RESULT = {"description": "An indoor area with blocks. No other robots, people, or active movement are visible.", "bunker": True}
NOW = datetime.now(timezone.utc)


def manifest(path, kind, identity, **extra):
    details = path.stat()
    return {"schema_version": 1, "artifact_kind": kind, "cache_identity": identity,
            "output": {"file_name": path.name, "size_bytes": details.st_size,
                       "file_identity": {"device_id": details.st_dev, "inode": details.st_ino,
                                         "mtime_ns": details.st_mtime_ns}}, **extra}


@pytest.fixture
def prepared(tmp_path):
    derived = tmp_path / "derived"
    derived.mkdir()
    front_store = ArtifactStore(derived, Path("ffmpeg"), Path("ffprobe"), "thumbnail")
    description_store = ArtifactStore(derived, Path("ffmpeg"), Path("ffprobe"), "ai_description")
    workspace = front_store.create_workspace(1)
    path = workspace / "thumbnail.png"
    pixels = np.zeros((2, 12, 3), dtype=np.uint8)
    for index in range(6):
        pixels[:, index * 2:(index + 1) * 2] = index * 30
    path.write_bytes(png_bytes(pixels))
    identity = thumbnail_cache_identity("a" * 64)
    front_manifest = manifest(path, "thumbnail", identity,
        processor_version=THUMBNAIL_POLICY, front_source_identity="a" * 64,
        source={"record_timestamps_ns": [str(i) for i in range(6)], "frame_times_seconds": list(range(6))})
    front_manifest['schema_version'] = 2
    front_manifest['output'].update(mime_type="image/png", width=12, height=2, frame_width=2, frame_count=6,
                                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    published = front_store.publish_thumbnail(workspace, 1, identity, front_manifest)
    front = ArtifactRecord(1, 7, "thumbnail", identity, published.output_relative_path,
                           "image/png", published.size_bytes, 0, 100, front_manifest, NOW)
    job = JobRecord(2, 7, "ai_description", description_cache_identity("a" * 64),
                    "running", NOW, NOW, None, None, None)
    target = PreparationTargetRecord(7, "thumbnail", 1, "b" * 64,
                                     "available", front.cache_identity, None, None, 10)

    class Repository:
        current = front
        completed = []
        failures = []

        def get_current_outputs(self, ids):
            assert ids == (7,)
            return (CurrentOutputRecord(target, artifact=self.current),)

        def get_current_artifact_for_delivery(self, recording_id, kind, artifact_id, planner):
            assert (recording_id, kind, artifact_id) == (7, "thumbnail", 1)
            assert len(planner) == 64
            return self.current

        def complete_job(self, job_id, artifact):
            self.completed.append((job_id, artifact))

        def fail_job(self, job_id, code, message):
            self.failures.append((job_id, code, message))

    class Inference:
        calls = 0
        result = RESULT
        replace_front = False

        def process(self, descriptor, output_path, *, control, thumbnail_manifest):
            self.calls += 1
            assert os.pread(descriptor, 8, 0) == b"\x89PNG\r\n\x1a\n"
            images, times = thumbnail_frames(descriptor, thumbnail_manifest)
            assert len(images) == 6 and times == list(range(6))
            output_path.write_text(json.dumps(self.result))
            if self.replace_front:
                repository.current = None
            return self.result

    repository = Repository()
    inference = Inference()
    worker = SerialWorker(repository, None, SimpleNamespace(profile=V0_PREVIEW_PROFILE),
                          front_store, "", "encoder", description_processor=inference,
                          description_artifact_store=description_store, thumbnail_artifact_store=front_store)
    return SimpleNamespace(derived=derived, front=front, front_store=front_store,
                           store=description_store, job=job, worker=worker,
                           repository=repository, inference=inference)


def test_description_job_reads_shared_thumbnails_and_publishes_identity_bound_json(prepared):
    original = (prepared.derived / prepared.front.output_relative_path).stat()
    prepared.worker._run_job(prepared.job)
    assert not prepared.repository.failures
    assert prepared.inference.calls == 1
    _, artifact = prepared.repository.completed[0]
    assert artifact.manifest["result"] == RESULT
    assert artifact.manifest["visual_source_identity"] == "a" * 64
    assert artifact.manifest["thumbnail_identity"] == prepared.front.cache_identity
    assert (artifact.coverage_start_ns, artifact.coverage_end_ns) == (0, 100)
    prepared.store.validate_description_artifact(artifact.output_relative_path, artifact.size_bytes,
                                                 artifact.cache_identity, artifact.manifest)
    assert (prepared.derived / prepared.front.output_relative_path).stat() == original
    assert not list(prepared.store.work_root.iterdir())


def test_changed_thumbnails_prevent_description_publication(prepared):
    prepared.inference.replace_front = True
    prepared.worker._run_job(prepared.job)
    assert not prepared.repository.completed
    assert prepared.repository.failures[0][1] == "ai_thumbnail_unavailable"
    assert not list(prepared.store.artifacts_root.rglob("description.json"))
    assert not list(prepared.store.work_root.iterdir())


def test_missing_thumbnails_do_not_invoke_model(prepared):
    prepared.repository.current = None
    prepared.worker._run_job(prepared.job)
    assert prepared.inference.calls == 0
    assert prepared.repository.failures[0][1] == "ai_thumbnail_unavailable"


def test_invalid_replacement_preserves_valid_description_and_front_video(prepared):
    prepared.worker._run_job(prepared.job)
    _, artifact = prepared.repository.completed[0]
    path = prepared.derived / artifact.output_relative_path
    original = path.read_bytes(), path.stat()
    prepared.inference.result = {"description": "Malformed result.", "bunker": "true"}
    prepared.worker._run_job(prepared.job)
    assert prepared.repository.failures[-1][1] == "ai_description_invalid"
    assert (path.read_bytes(), path.stat()) == original
    prepared.front_store.validate_thumbnail_artifact(prepared.front.output_relative_path, prepared.front.size_bytes,
                                         prepared.front.cache_identity, prepared.front.manifest)


def test_description_file_and_manifest_result_must_match(prepared):
    prepared.worker._run_job(prepared.job)
    _, artifact = prepared.repository.completed[0]
    path = prepared.derived / artifact.output_relative_path
    value = path.read_text().replace("indoor", "outdoor")
    before = path.stat()
    path.write_text(value)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    with pytest.raises(ArtifactStoreError, match="invalid"):
        prepared.store.validate_description_artifact(artifact.output_relative_path, artifact.size_bytes,
                                                     artifact.cache_identity, artifact.manifest)


def test_missing_description_is_partial_and_ready_requires_both_outputs(prepared):
    from rosbag_analyser.preparation import _aggregate_state
    assert _aggregate_state({"front_preview": "ready", "ai_description": "not_requested"}) == "partially_prepared"
    assert _aggregate_state({"front_preview": "ready", "ai_description": "ready", "imu_series": "unavailable"}) == "ready"
    assert _aggregate_state({"front_preview": "ready", "ai_description": "queued"}) == "queued"
    assert _aggregate_state({"front_preview": "ready", "ai_description": "failed"}) == "failed"


def test_historical_migration_remains_pinned_and_shared_frame_policy_has_a_new_identity():
    sql = (Path(__file__).parents[2] / "src/rosbag_analyser/persistence/migrations/0012_q8_ai_description.sql").read_text()
    assert "ai-description-v2" in sql and DESCRIPTION_POLICY not in sql
    assert "3171b7da6256dc536d89a1cebfdb3d544677f5e68dd259260b8e709eb4bd3278" in sql
    assert "ai-description-v3" in DESCRIPTION_POLICY and THUMBNAIL_POLICY in DESCRIPTION_POLICY
    assert "INSERT INTO jobs" not in sql
    assert description_cache_identity("a" * 64) != description_cache_identity("b" * 64)
    legacy = (Path(__file__).parents[2] / "src/rosbag_analyser/persistence/migrations/0010_ai_description.sql").read_text()
    assert "ai-description-v1" in legacy and DESCRIPTION_POLICY not in legacy


def test_pause_excludes_wait_time_and_stops_native_descendant(tmp_path, monkeypatch):
    import subprocess
    import time
    from rosbag_analyser.processors import ai_description
    children = []
    original_popen = subprocess.Popen
    descendant_pid = tmp_path / "native.pid"
    command = ("import subprocess,sys,time,json,signal; "
               "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
               f"open({str(descendant_pid)!r},'w').write(str(child.pid)); "
               "signal.signal(signal.SIGTERM, lambda *a: (child.terminate(),child.wait(),sys.exit())); "
               f"time.sleep(0.4); open({str(tmp_path / 'description.json')!r},'w').write({json.dumps(RESULT)!r})")
    def start(_, **kwargs):
        child = original_popen([sys.executable, "-c", command], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(ai_description.subprocess, "Popen", start)
    monkeypatch.setattr(ai_description, "validate_runtime", lambda _: {})
    class Pause:
        paused = False
        def checkpoint(self, phase, **kwargs):
            if phase == "processing" and not self.paused:
                self.paused = True
                native = int(descendant_pid.read_text())
                time.sleep(0.02)
                assert Path(f"/proc/{native}/stat").read_text().split()[2] == "T"
                time.sleep(0.6)
    pause = Pause()
    result = DescriptionProcessor(tmp_path, Path("ffmpeg"), Path("ffprobe"), timeout_seconds=0.55).process(
        0, tmp_path / "description.json", control=pause)
    assert result == RESULT and pause.paused
    native = int(descendant_pid.read_text())
    deadline = time.monotonic() + 2
    while Path(f"/proc/{native}/stat").exists() and time.monotonic() < deadline:
        if Path(f"/proc/{native}/stat").read_text().split()[2] == "Z":
            break
        time.sleep(0.02)
    assert not Path(f"/proc/{native}/stat").exists() or Path(f"/proc/{native}/stat").read_text().split()[2] == "Z"


@pytest.mark.parametrize("value", [None, {}, {"description": "", "bunker": False},
    {"description": "valid", "bunker": "false"}, {**RESULT, "extra": True},
    {"description": "line\nbreak", "bunker": True}, {"description": "x" * 1001, "bunker": False}])
def test_invalid_result_contract_is_rejected(value):
    with pytest.raises(ValueError):
        validate_description_result(value)


def test_model_environment_absence_fails_truthfully(tmp_path):
    processor = DescriptionProcessor(None, Path("ffmpeg"), Path("ffprobe"))
    with pytest.raises(DescriptionProcessingError) as error:
        processor.process(0, tmp_path / "description.json")
    assert error.value.code == "ai_model_unavailable"


@pytest.mark.parametrize("cancel", [True, False])
def test_cancellation_and_timeout_terminate_inference_processes(tmp_path, monkeypatch, cancel):
    import subprocess
    from rosbag_analyser.job_control import JobCanceled
    from rosbag_analyser.processors import ai_description
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"stand-in model")
    original_popen = subprocess.Popen
    children = []

    def stand_in(command, **kwargs):
        child = original_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(ai_description.subprocess, "Popen", stand_in)
    monkeypatch.setattr(ai_description, "validate_runtime", lambda _: {})

    class Cancel:
        def checkpoint(self, phase):
            assert phase == "processing"
            # Inference is stopped while the control checkpoint is in progress.
            assert Path(f"/proc/{children[0].pid}/stat").read_text().split()[2] == "T"
            raise JobCanceled("Synthetic cancellation")

    processor = DescriptionProcessor(model, Path("ffmpeg"), Path("ffprobe"),
                                     timeout_seconds=0.05)
    with pytest.raises(JobCanceled if cancel else DescriptionProcessingError) as error:
        processor.process(0, tmp_path / "description.json", control=Cancel() if cancel else None)
    if not cancel:
        assert error.value.code == "ai_description_timeout"
    assert len(children) == 1 and children[0].poll() is not None
    assert not (tmp_path / "description.json").exists()
