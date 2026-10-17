from datetime import datetime, timedelta
import pytest

from researchos.orchestration.candle_kinetic_engine import CandleKineticEngine


def test_candle_shape_ratios_are_bounded_and_sum_to_one_for_valid_candle():
    engine = CandleKineticEngine(window=3, z_threshold=2.0)
    feature = engine.update(100.0, 110.0, 95.0, 107.0)
    assert feature["body_ratio"] == pytest.approx(7 / 15)
    assert feature["upper_ratio"] == pytest.approx(3 / 15)
    assert feature["lower_ratio"] == pytest.approx(5 / 15)
    assert feature["body_ratio"] + feature["upper_ratio"] + feature["lower_ratio"] == pytest.approx(
        1.0
    )
    assert feature["range_energy_proxy"] >= 0
    assert feature["range_acceleration_proxy"] is None


def test_z_score_uses_prior_window_and_impulse_threshold():
    engine = CandleKineticEngine(window=3, z_threshold=2.0)
    for high in (101, 102, 103):
        result = engine.update(100, high, 100, 100.5)
        assert result["z_speed"] is None
    result = engine.update(100, 110, 100, 108)
    assert result["z_speed"] is not None
    assert result["impulse"] is True


def test_compute_features_resets_state_on_timestamp_gap():
    engine = CandleKineticEngine(window=2)
    start = datetime(2025, 1, 1)
    rows = [
        (start, 100, 101, 99, 100.5),
        (start + timedelta(minutes=15), 100, 101, 99, 100.5),
        (start + timedelta(hours=1), 100, 101, 99, 100.5),
    ]
    features = engine.compute_features(rows)
    assert features[2]["z_speed"] is None
    assert features[2]["range_acceleration_proxy"] is None
