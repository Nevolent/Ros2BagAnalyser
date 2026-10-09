from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

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
    front_store = ArtifactStore(derived, Path("ffmpeg"), Path("ffprobe"))
    description_store = ArtifactStore(derived, Path("ffmpeg"), Path("ffprobe"), "ai_description")
    workspace = front_store.create_workspace(1)
    path = workspace / "preview.mp4"
    path.write_bytes(b"synthetic prepared video")
    front_manifest = manifest(path, "front_preview", "a" * 64)
    published = front_store.publish(workspace, 1, "a" * 64, front_manifest)
    front = ArtifactRecord(1, 7, "front_preview", "a" * 64, published.output_relative_path,
                           "video/mp4", published.size_bytes, 0, 100, front_manifest, NOW)
    job = JobRecord(2, 7, "ai_description", description_cache_identity(front.cache_identity),
                    "running", NOW, NOW, None, None, None)
    target = PreparationTargetRecord(7, "front_preview", 1, "b" * 64,
                                     "available", front.cache_identity, None, None, 10)

    class Repository:
        current = front
        completed = []
        failures = []

        def get_current_outputs(self, ids):
            assert ids == (7,)
            return (CurrentOutputRecord(target, artifact=self.current),)

        def get_current_artifact_for_delivery(self, recording_id, kind, artifact_id, planner):
            assert (recording_id, kind, artifact_id) == (7, "front_preview", 1)
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

        def process(self, descriptor, output_path, *, control):
            self.calls += 1
            assert os.pread(descriptor, 100, 0) == b"synthetic prepared video"
            output_path.write_text(json.dumps(self.result))
            if self.replace_front:
                repository.current = None
            return self.result

    repository = Repository()
    inference = Inference()
    worker = SerialWorker(repository, None, SimpleNamespace(profile=V0_PREVIEW_PROFILE),
                          front_store, "", "encoder", description_processor=inference,
                          description_artifact_store=description_store)
    return SimpleNamespace(derived=derived, front=front, front_store=front_store,
                           store=description_store, job=job, worker=worker,
                           repository=repository, inference=inference)


def test_description_job_reads_only_prepared_preview_and_publishes_identity_bound_json(prepared):
    original = (prepared.derived / prepared.front.output_relative_path).stat()
    prepared.worker._run_job(prepared.job)
    assert not prepared.repository.failures
    assert prepared.inference.calls == 1
    _, artifact = prepared.repository.completed[0]
    assert artifact.manifest["result"] == RESULT
    assert artifact.manifest["front_preview_identity"] == prepared.front.cache_identity
    assert (artifact.coverage_start_ns, artifact.coverage_end_ns) == (0, 100)
    prepared.store.validate_description_artifact(artifact.output_relative_path, artifact.size_bytes,
                                                 artifact.cache_identity, artifact.manifest)
    assert (prepared.derived / prepared.front.output_relative_path).stat() == original
    assert not list(prepared.store.work_root.iterdir())


def test_changed_front_preview_prevents_description_publication(prepared):
    prepared.inference.replace_front = True
    prepared.worker._run_job(prepared.job)
    assert not prepared.repository.completed
    assert prepared.repository.failures[0][1] == "ai_front_preview_unavailable"
    assert not list(prepared.store.artifacts_root.rglob("description.json"))
    assert not list(prepared.store.work_root.iterdir())


def test_missing_front_preview_does_not_invoke_model(prepared):
    prepared.repository.current = None
    prepared.worker._run_job(prepared.job)
    assert prepared.inference.calls == 0
    assert prepared.repository.failures[0][1] == "ai_front_preview_unavailable"


def test_invalid_replacement_preserves_valid_description_and_front_video(prepared):
    prepared.worker._run_job(prepared.job)
    _, artifact = prepared.repository.completed[0]
    path = prepared.derived / artifact.output_relative_path
    original = path.read_bytes(), path.stat()
    prepared.inference.result = {"description": "Malformed result.", "bunker": "true"}
    prepared.worker._run_job(prepared.job)
    assert prepared.repository.failures[-1][1] == "ai_description_invalid"
    assert (path.read_bytes(), path.stat()) == original
    prepared.front_store.validate_media(prepared.front.output_relative_path, prepared.front.size_bytes,
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


def test_migration_backfill_uses_the_runtime_identity_policy():
    sql = (Path(__file__).parents[2] / "src/rosbag_analyser/persistence/migrations/0010_ai_description.sql").read_text()
    assert DESCRIPTION_POLICY in sql
    assert DESCRIPTION_PLANNER_IDENTITY in sql
    assert "INSERT INTO jobs" not in sql
    assert description_cache_identity("a" * 64) != description_cache_identity("b" * 64)


@pytest.mark.parametrize("value", [None, {}, {"description": "", "bunker": False},
    {"description": "valid", "bunker": "false"}, {**RESULT, "extra": True},
    {"description": "line\nbreak", "bunker": True}, {"description": "x" * 1001, "bunker": False}])
def test_invalid_result_contract_is_rejected(value):
    with pytest.raises(ValueError):
        validate_description_result(value)


def test_model_environment_absence_fails_truthfully(tmp_path):
    processor = DescriptionProcessor(None, None, Path("ffmpeg"), Path("ffprobe"))
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

    class Cancel:
        def checkpoint(self, phase):
            assert phase == "processing"
            # Inference is stopped while the control checkpoint is in progress.
            assert Path(f"/proc/{children[0].pid}/stat").read_text().split()[2] == "T"
            raise JobCanceled("Synthetic cancellation")

    processor = DescriptionProcessor(Path(sys.executable), model, Path("ffmpeg"), Path("ffprobe"),
                                     timeout_seconds=0.05)
    with pytest.raises(JobCanceled if cancel else DescriptionProcessingError) as error:
        processor.process(0, tmp_path / "description.json", control=Cancel() if cancel else None)
    if not cancel:
        assert error.value.code == "ai_description_timeout"
    assert len(children) == 1 and children[0].poll() is not None
    assert not (tmp_path / "description.json").exists()
