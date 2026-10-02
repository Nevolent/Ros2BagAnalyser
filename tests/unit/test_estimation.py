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


def test_uses_upper_runtime_rate_with_headroom_and_rounds_up() -> None:
    result = estimate_total_ms(
        7,
        (
            EstimateSample(10, 3),
            EstimateSample(40, 10),
            EstimateSample(1_000, 10),
        ),
    )

    assert result.method == "recent_rate_v2"
    assert result.sample_count == 3
    assert result.estimated_total_ms == 805


def test_two_samples_use_slower_rate_and_respect_sample_bound() -> None:
    result = estimate_total_ms(
        10,
        (
            EstimateSample(10, 10),
            EstimateSample(30, 10),
            EstimateSample(10_000, 10),
        ),
        max_samples=2,
    )

    assert result.estimated_total_ms == 35
    assert result.sample_count == 2


def test_invalid_work_units_return_unavailable() -> None:
    result = estimate_total_ms(
        0,
        (EstimateSample(10, 10), EstimateSample(20, 10)),
    )

    assert result.estimated_total_ms is None
    assert result.method == "insufficient_history"


def test_ten_new_successes_retire_old_samples_without_resetting_history() -> None:
    old = (EstimateSample(10, 100),) * 10
    fresh = (EstimateSample(100, 100),) * 10
    assert estimate_total_ms(100, old).estimated_total_ms == 12
    # Existing compatible history still gives an estimate during transition.
    assert estimate_total_ms(100, fresh[:1] + old).estimated_total_ms is not None
    result = estimate_total_ms(100, fresh + old)
    assert result.estimated_total_ms == 115
    assert result.sample_count == 10
    assert len(old) == 10


def test_recent_window_resists_two_extreme_slow_samples() -> None:
    samples = (EstimateSample(10_000, 100),) * 2 + (EstimateSample(100, 100),) * 8
    assert estimate_total_ms(100, samples).estimated_total_ms == 115
