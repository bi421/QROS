import pytest

from researchos.orchestration.candle_velocity import (
    CandleVelocityEngine,
    estimate_conditional_outcomes,
    estimate_wick_conditioned_outcomes,
)


def test_z_score_uses_only_prior_completed_candles_and_flags_impulse():
    engine = CandleVelocityEngine(window=4, z_threshold=2.0)
    for candle_range in (1.0, 2.0, 3.0, 4.0):
        result = engine.update(100.0, 100.0 + candle_range, 100.0, 100.5)
        assert result["z_speed"] is None
        assert result["impulse"] is False
    result = engine.update(100.0, 110.0, 99.0, 108.0)
    assert result["z_speed"] is not None
    assert result["z_speed"] > 2.0
    assert result["impulse"] is True
    assert result["direction"] == 1


def test_directional_and_range_velocity_units():
    result = CandleVelocityEngine(window=2).update(100, 104, 98, 103, interval_seconds=60)
    assert result["directional_velocity"] == pytest.approx(3 / 60)
    assert result["range_velocity"] == pytest.approx(6 / 60)
    assert result["direction"] == 1


def test_outcome_rates_are_empirical_and_sum_to_one():
    result = estimate_conditional_outcomes(
        [2.5, 3.0, 2.2, 1.9, None],
        [1, -1, 1, 1, 1],
        ["CONTINUATION", "REVERSAL", "SIDEWAYS", "CONTINUATION", "REVERSAL"],
    )
    assert result["eligible_events"] == 3
    assert result["counts"] == {"CONTINUATION": 1, "REVERSAL": 1, "SIDEWAYS": 1}
    assert sum(result["probabilities"].values()) == pytest.approx(1.0)


def test_empty_outcome_sample_returns_null_probabilities():
    result = estimate_conditional_outcomes([None], [0], [None])
    assert result["eligible_events"] == 0
    assert set(result["probabilities"].values()) == {None}


def test_rejects_invalid_ohlc_and_misaligned_outcomes():
    with pytest.raises(ValueError, match="invalid OHLC"):
        CandleVelocityEngine().update(100, 99, 101, 100)
    with pytest.raises(ValueError, match="equal lengths"):
        estimate_conditional_outcomes([2.5], [1], [])


def test_rolling_state_is_bounded():
    engine = CandleVelocityEngine(window=5)
    for i in range(100):
        engine.update(100 + i, 102 + i, 99 + i, 101 + i)
    assert len(engine._ranges) == 5


def test_wick_lengths_ratios_and_close_location_are_reported():
    result = CandleVelocityEngine(window=2).update(100, 110, 95, 108)
    assert result["body_length"] == pytest.approx(8)
    assert result["upper_wick_length"] == pytest.approx(2)
    assert result["lower_wick_length"] == pytest.approx(5)
    assert result["body_ratio"] == pytest.approx(8 / 15)
    assert result["upper_wick_ratio"] == pytest.approx(2 / 15)
    assert result["lower_wick_ratio"] == pytest.approx(5 / 15)
    assert result["close_location"] == pytest.approx(13 / 15)
    assert result["wick_pattern"] == "LOWER_WICK_DOMINANT"


def test_wick_conditioned_empirical_probabilities_group_by_direction_and_wick():
    features = [
        {"z_speed": 2.5, "direction": 1, "wick_pattern": "LOWER_WICK_DOMINANT"},
        {"z_speed": 2.2, "direction": 1, "wick_pattern": "LOWER_WICK_DOMINANT"},
        {"z_speed": 2.8, "direction": -1, "wick_pattern": "UPPER_WICK_DOMINANT"},
        {"z_speed": 1.0, "direction": 1, "wick_pattern": "BALANCED"},
    ]
    outcomes = ["CONTINUATION", "REVERSAL", "REVERSAL", "SIDEWAYS"]
    result = estimate_wick_conditioned_outcomes(features, outcomes)
    group = result["groups"]["direction_UP|LOWER_WICK_DOMINANT"]
    assert group["n"] == 2
    assert group["probabilities"]["CONTINUATION"] == pytest.approx(0.5)
    assert group["probabilities"]["REVERSAL"] == pytest.approx(0.5)
    assert result["groups"]["direction_DOWN|UPPER_WICK_DOMINANT"]["n"] == 1


def test_wick_probability_rejects_misaligned_inputs():
    with pytest.raises(ValueError, match="equal lengths"):
        estimate_wick_conditioned_outcomes([], ["REVERSAL"])
