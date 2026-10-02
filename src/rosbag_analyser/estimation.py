from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


MAX_ESTIMATE_SAMPLES = 10
ESTIMATE_METHOD = "recent_rate_v2"
MAX_ESTIMATED_TOTAL_MS = 2**63 - 1


@dataclass(frozen=True)
class EstimateSample:
    runtime_ms: int
    work_units: int


@dataclass(frozen=True)
class FrozenEstimate:
    estimated_total_ms: int | None
    method: str
    sample_count: int


def estimate_total_ms(
    work_units: int,
    samples: tuple[EstimateSample, ...],
    *,
    max_samples: int = MAX_ESTIMATE_SAMPLES,
) -> FrozenEstimate:
    if work_units <= 0 or max_samples <= 0:
        return FrozenEstimate(None, "insufficient_history", 0)
    valid = tuple(
        sample
        for sample in samples[:max_samples]
        if sample.runtime_ms > 0 and sample.work_units > 0
    )
    if len(valid) < 2:
        return FrozenEstimate(None, "insufficient_history", len(valid))

    # An elapsed/estimate progress bar needs headroom: a median will be exceeded
    # by roughly half of comparable runs. Use the nearest-rank 80th percentile
    # with 15% headroom, retaining exact arithmetic for large byte counts.
    # Callers supply newest first, so ten fresh successes retire older samples
    # from prediction without deleting any processing history.
    rates = sorted(Fraction(item.runtime_ms, item.work_units) for item in valid)
    rate = rates[(4 * len(rates) + 4) // 5 - 1]
    predicted = rate * work_units * Fraction(115, 100)
    predicted_ms = (predicted.numerator + predicted.denominator - 1) // predicted.denominator
    if predicted_ms <= 0 or predicted_ms > MAX_ESTIMATED_TOTAL_MS:
        return FrozenEstimate(None, "insufficient_history", len(valid))
    return FrozenEstimate(predicted_ms, ESTIMATE_METHOD, len(valid))


__all__ = [
    "EstimateSample",
    "FrozenEstimate",
    "MAX_ESTIMATE_SAMPLES",
    "estimate_total_ms",
]
