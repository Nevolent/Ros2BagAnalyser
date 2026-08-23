from __future__ import annotations

from rosbag_analyser.catalog.types import SafeDiagnostic
from rosbag_analyser.health import ApplicationHealthService


class FakeDerivedGuard:
    def __init__(
        self,
        availability: SafeDiagnostic | None = None,
        admission: SafeDiagnostic | None = None,
    ) -> None:
        self.availability = availability
        self.admission = admission

    def availability_diagnostic(self) -> SafeDiagnostic | None:
        return self.availability

    def diagnostic(self) -> SafeDiagnostic | None:
        return self.availability or self.admission


class FakeAdmissionGuard:
    def __init__(
        self,
        source: SafeDiagnostic | None = None,
        derived: FakeDerivedGuard | None = None,
    ) -> None:
        self.source = source
        self.derived_guard = derived

    def source_diagnostic(self) -> SafeDiagnostic | None:
        return self.source


def service(guard: FakeAdmissionGuard, *, database_ok: bool = True):
    def database_check() -> None:
        if not database_ok:
            raise RuntimeError("private database failure")

    return ApplicationHealthService(
        "release-test",
        database_check=database_check,
        admission_guard=guard,  # type: ignore[arg-type]
        worker_online=lambda: True,
    )


def test_low_space_pauses_preparation_without_hiding_ready_artifacts() -> None:
    report = service(
        FakeAdmissionGuard(
            derived=FakeDerivedGuard(
                admission=SafeDiagnostic("derived_space_low", "private detail")
            )
        )
    ).readiness()

    assert report.ready
    assert report.capabilities["catalog"].available
    assert report.capabilities["artifact_delivery"].available
    assert not report.capabilities["new_preparation"].available
    assert report.capabilities["new_preparation"].code == "derived_space_low"


def test_source_loss_keeps_saved_catalog_and_artifacts_ready() -> None:
    report = service(
        FakeAdmissionGuard(
            source=SafeDiagnostic("source_mount_unavailable", "private detail"),
            derived=FakeDerivedGuard(),
        )
    ).readiness()

    assert report.ready
    assert report.capabilities["catalog"].available
    assert report.capabilities["artifact_delivery"].available
    assert not report.capabilities["source_access"].available
    assert not report.capabilities["new_preparation"].available


def test_database_or_derived_loss_fails_core_readiness() -> None:
    database = service(
        FakeAdmissionGuard(derived=FakeDerivedGuard()), database_ok=False
    ).readiness()
    derived = service(
        FakeAdmissionGuard(
            derived=FakeDerivedGuard(
                availability=SafeDiagnostic(
                    "derived_mount_unavailable", "private detail"
                )
            )
        )
    ).readiness()

    assert not database.ready
    assert not database.capabilities["catalog"].available
    assert not derived.ready
    assert not derived.capabilities["artifact_delivery"].available
