from rosbag_analyser.estimation import EstimateSample, estimate_total_ms


def test_requires_two_positive_compatible_samples() -> None:
    empty = estimate_total_ms(100, ())
    one = estimate_total_ms(100, (EstimateSample(50, 10),))
    invalid = estimate_total_ms(
        100,
        (EstimateSample(0, 10), EstimateSample(50, 0)),
    )

    assert empty.method == "insufficient_history"
    assert empty.sample_count == 0
    assert one.estimated_total_ms is None
    assert one.sample_count == 1
    assert invalid.sample_count == 0


def test_uses_exact_median_rate_and_rounds_total_up() -> None:
    result = estimate_total_ms(
        7,
        (
            EstimateSample(10, 3),
            EstimateSample(40, 10),
            EstimateSample(1_000, 10),
        ),
    )

    assert result.method == "median_rate_v1"
    assert result.sample_count == 3
    assert result.estimated_total_ms == 28


def test_even_sample_median_and_sample_bound_are_deterministic() -> None:
    result = estimate_total_ms(
        10,
        (
            EstimateSample(10, 10),
            EstimateSample(30, 10),
            EstimateSample(10_000, 10),
        ),
        max_samples=2,
    )

    assert result.estimated_total_ms == 20
    assert result.sample_count == 2


def test_invalid_work_units_return_unavailable() -> None:
    result = estimate_total_ms(
        0,
        (EstimateSample(10, 10), EstimateSample(20, 10)),
    )

    assert result.estimated_total_ms is None
    assert result.method == "insufficient_history"
