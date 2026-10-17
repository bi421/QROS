import math
import pytest
from researchos.orchestration.candle_potential_geometry import (
    potential_geometry_features,
    first_touch_barrier_label,
)


def test_potential_geometry_is_finite_and_curvature_uses_prior_return():
    f = potential_geometry_features(
        close=101,
        ema=100,
        prior_log_returns=[0.001],
        current_log_return=0.002,
        prior_return_scale=0.01,
        range_velocity=0.5,
    )
    assert f["potential_proxy"] > 0
    assert f["kinetic_potential_ratio"] > 0
    assert f["path_curvature_proxy"] == pytest.approx((0.2 - 0.1) / (1 + 0.2**2) ** 1.5)
    assert all(v is None or math.isfinite(v) for v in f.values())


def test_zero_displacement_does_not_divide_by_zero():
    f = potential_geometry_features(
        close=100,
        ema=100,
        prior_log_returns=[],
        current_log_return=0,
        prior_return_scale=0,
        range_velocity=0,
    )
    assert f["kinetic_potential_ratio"] == 0
    assert f["path_curvature_proxy"] is None


def test_barrier_label_checks_future_bars_and_detects_ambiguous_touch():
    rows = [(100, 99, 100), (102, 100, 101), (103, 97, 100), (101, 99, 100)]
    assert first_touch_barrier_label(rows, 0, 102, 98, 3) == "UP_FIRST"
    assert first_touch_barrier_label(rows, 1, 102, 98, 2) == "AMBIGUOUS"
    assert first_touch_barrier_label(rows, 2, 105, 95, 1) == "TIMEOUT"
