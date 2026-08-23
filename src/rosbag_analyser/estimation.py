from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


MAX_ESTIMATE_SAMPLES = 20
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

    rates = sorted(Fraction(item.runtime_ms, item.work_units) for item in valid)
    middle = len(rates) // 2
    if len(rates) % 2:
        median_rate = rates[middle]
    else:
        median_rate = (rates[middle - 1] + rates[middle]) / 2
    predicted = median_rate * work_units
    predicted_ms = (predicted.numerator + predicted.denominator - 1) // predicted.denominator
    if predicted_ms <= 0 or predicted_ms > MAX_ESTIMATED_TOTAL_MS:
        return FrozenEstimate(None, "insufficient_history", len(valid))
    return FrozenEstimate(predicted_ms, "median_rate_v1", len(valid))


__all__ = [
    "EstimateSample",
    "FrozenEstimate",
    "MAX_ESTIMATE_SAMPLES",
    "estimate_total_ms",
]
