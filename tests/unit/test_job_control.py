from __future__ import annotations

from dataclasses import dataclass

import pytest

from rosbag_analyser.job_control import JobCanceled, JobControlToken


@dataclass(frozen=True)
class Snapshot:
    state: str = "running"
    control_state: str = "none"


class Repository:
    def __init__(self, snapshots: list[Snapshot]) -> None:
        self.snapshots = snapshots
        self.phases: list[str] = []
        self.pause_acknowledged = 0

    def worker_checkpoint(self, job_id: int, phase: str) -> Snapshot:
        assert job_id == 9
        self.phases.append(phase)
        return self.snapshots.pop(0) if self.snapshots else Snapshot()

    def acknowledge_pause(self, job_id: int) -> Snapshot:
        assert job_id == 9
        self.pause_acknowledged += 1
        return Snapshot(control_state="paused")


def test_control_token_acknowledges_pause_and_resumes_same_attempt() -> None:
    repository = Repository(
        [
            Snapshot(control_state="pause_requested"),
            Snapshot(control_state="paused"),
            Snapshot(control_state="none"),
        ]
    )
    token = JobControlToken(
        repository, 9, poll_interval_seconds=0, pause_poll_seconds=0
    )

    token.checkpoint("processing", force=True)

    assert repository.pause_acknowledged == 1
    assert repository.phases[0] == "processing"


def test_control_token_raises_before_publication_when_cancel_requested() -> None:
    repository = Repository([Snapshot(control_state="cancel_requested")])
    token = JobControlToken(repository, 9, poll_interval_seconds=0)

    with pytest.raises(JobCanceled):
        token.checkpoint("validating", force=True)
