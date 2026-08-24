from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Protocol


class ControlSnapshot(Protocol):
    state: str
    control_state: str


class ControlRepository(Protocol):
    def worker_checkpoint(self, job_id: int, phase: str) -> ControlSnapshot: ...

    def acknowledge_pause(self, job_id: int) -> ControlSnapshot: ...

    def enter_publishing(self, job_id: int) -> ControlSnapshot: ...


class JobCanceled(RuntimeError):
    """Raised only after the database still owns a cancellable running attempt."""


@dataclass
class JobControlToken:
    repository: ControlRepository
    job_id: int
    poll_interval_seconds: float = 0.25
    pause_poll_seconds: float = 0.1

    def __post_init__(self) -> None:
        self._last_phase: str | None = None
        self._next_poll = 0.0

    def checkpoint(self, phase: str, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and phase == self._last_phase and now < self._next_poll:
            return
        snapshot = self.repository.worker_checkpoint(self.job_id, phase)
        self._last_phase = phase
        self._next_poll = now + max(0.0, self.poll_interval_seconds)
        self._honor(snapshot, phase)

    def publishing_gate(self) -> None:
        snapshot = self.repository.enter_publishing(self.job_id)
        if snapshot.control_state == "cancel_requested":
            raise JobCanceled(f"Job {self.job_id} was canceled before publication.")
        if snapshot.control_state == "pause_requested":
            self._honor(snapshot, "validating")
            snapshot = self.repository.enter_publishing(self.job_id)
        if snapshot.state != "running" or snapshot.control_state != "none":
            raise RuntimeError("The job cannot enter the publishing phase.")
        self._last_phase = "publishing"

    def _honor(self, snapshot: ControlSnapshot, phase: str) -> None:
        if snapshot.control_state == "cancel_requested":
            raise JobCanceled(f"Job {self.job_id} was canceled.")
        if snapshot.state != "running":
            raise RuntimeError("The worker no longer owns this processing attempt.")
        if snapshot.control_state != "pause_requested":
            return

        snapshot = self.repository.acknowledge_pause(self.job_id)
        while snapshot.state == "running" and snapshot.control_state in {
            "paused",
            "pause_requested",
        }:
            time.sleep(max(0.0, self.pause_poll_seconds))
            snapshot = self.repository.worker_checkpoint(self.job_id, phase)
        if snapshot.control_state == "cancel_requested":
            raise JobCanceled(f"Job {self.job_id} was canceled while paused.")
        if snapshot.state != "running" or snapshot.control_state != "none":
            raise RuntimeError("The paused processing attempt could not resume safely.")
        self._next_poll = time.monotonic() + max(0.0, self.poll_interval_seconds)


__all__ = ["JobCanceled", "JobControlToken"]
