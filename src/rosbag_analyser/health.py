from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from rosbag_analyser.deployment import ProcessingAdmissionGuard


@dataclass(frozen=True)
class Capability:
    available: bool
    code: str | None = None
    state: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"available": self.available}
        if self.code is not None:
            result["code"] = self.code
        if self.state is not None:
            result["state"] = self.state
        return result


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    release_id: str
    capabilities: Mapping[str, Capability]
    platform_support_end: str = "2027-05"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "not_ready",
            "release_id": self.release_id,
            "platform_support_end": self.platform_support_end,
            "capabilities": {
                name: capability.as_dict()
                for name, capability in self.capabilities.items()
            },
        }


class HealthService:
    def __init__(self, release_id: str) -> None:
        self.release_id = release_id

    def liveness(self) -> dict[str, str]:
        return {"status": "alive", "release_id": self.release_id}

    def readiness(self) -> ReadinessReport:
        capabilities = {
            "database": Capability(True),
            "catalog": Capability(True),
            "artifact_delivery": Capability(True),
            "source_access": Capability(True),
            "new_preparation": Capability(True),
            "worker_observation": Capability(True, state="unknown"),
        }
        return ReadinessReport(True, self.release_id, capabilities)


class ApplicationHealthService(HealthService):
    def __init__(
        self,
        release_id: str,
        *,
        database_check: Callable[[], None],
        admission_guard: ProcessingAdmissionGuard,
        worker_online: Callable[[], bool],
    ) -> None:
        super().__init__(release_id)
        self.database_check = database_check
        self.admission_guard = admission_guard
        self.worker_online = worker_online

    def readiness(self) -> ReadinessReport:
        database = Capability(True)
        try:
            self.database_check()
        except Exception:
            database = Capability(False, "database_or_schema_unavailable")

        source_diagnostic = self.admission_guard.source_diagnostic()
        source = (
            Capability(True)
            if source_diagnostic is None
            else Capability(False, source_diagnostic.code)
        )
        derived_availability_diagnostic = (
            None
            if self.admission_guard.derived_guard is None
            else self.admission_guard.derived_guard.availability_diagnostic()
        )
        derived = (
            Capability(True)
            if derived_availability_diagnostic is None
            else Capability(False, derived_availability_diagnostic.code)
        )
        derived_preparation_diagnostic = (
            None
            if self.admission_guard.derived_guard is None
            else self.admission_guard.derived_guard.diagnostic()
        )
        preparation_diagnostic = source_diagnostic or derived_preparation_diagnostic
        new_preparation = (
            Capability(True)
            if database.available and preparation_diagnostic is None
            else Capability(
                False,
                (
                    database.code
                    if not database.available
                    else preparation_diagnostic.code  # type: ignore[union-attr]
                ),
            )
        )
        worker = Capability(False, "database_or_schema_unavailable")
        if database.available:
            try:
                worker = Capability(
                    True,
                    state="online" if self.worker_online() else "offline",
                )
            except Exception:
                worker = Capability(False, "worker_observation_unavailable")
        capabilities = {
            "database": database,
            "catalog": Capability(database.available, database.code),
            "artifact_delivery": Capability(
                database.available and derived.available,
                database.code if not database.available else derived.code,
            ),
            "source_access": source,
            "new_preparation": new_preparation,
            "worker_observation": worker,
        }
        return ReadinessReport(
            database.available and derived.available,
            self.release_id,
            capabilities,
        )


__all__ = [
    "ApplicationHealthService",
    "Capability",
    "HealthService",
    "ReadinessReport",
]
