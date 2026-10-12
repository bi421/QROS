from __future__ import annotations

import math

import pytest

pytest.importorskip("cpp_quant_engine.qros_biberion")
from cpp_quant_engine import qros_biberion as biberion


def _model(*, bearish: float = 0.0, neutral: float = 0.0, bullish: float = 0.0):
    model = biberion.StateModel()
    model.weights = [0.0] * 18
    model.bias = [bearish, neutral, bullish]
    model.threshold = 0.75
    return model


def _observation(*, latency_ms: float = 20.0, vxy_level: float = 15.0,
                 dxy_abs_change_pct: float = 0.2, dxy_fresh: bool = True):
    observation = biberion.SafetyObservation()
    observation.latency_ms = latency_ms
    observation.vxy_level = vxy_level
    observation.dxy_abs_change_pct = dxy_abs_change_pct
    observation.dxy_fresh = dxy_fresh
    return observation


def test_softmax_probabilities_sum_to_one_and_select_bullish() -> None:
    result = biberion.evaluate_market_state(
        [0.0] * 6, _observation(), _model(bullish=3.0), biberion.SafetyLimits()
    )
    assert result.safety_passed is True
    assert result.state == 1
    assert result.p_bullish > 0.75
    assert math.isclose(
        result.p_bearish + result.p_neutral + result.p_bullish, 1.0, abs_tol=1e-12
    )


def test_safety_gate_forces_neutral_even_when_bullish_probability_is_high() -> None:
    result = biberion.evaluate_market_state(
        [0.0] * 6,
        _observation(latency_ms=500.0),
        _model(bullish=5.0),
        biberion.SafetyLimits(),
    )
    assert result.p_bullish > 0.75
    assert result.state == 0
    assert result.safety_passed is False
    assert result.reason == "safety_gate_latency_exceeded"


def test_stale_dxy_fails_closed() -> None:
    result = biberion.evaluate_market_state(
        [0.0] * 6,
        _observation(dxy_fresh=False),
        _model(bearish=5.0),
        biberion.SafetyLimits(),
    )
    assert result.state == 0
    assert result.reason == "safety_gate_dxy_stale"


def test_invalid_feature_shape_fails_closed() -> None:
    result = biberion.evaluate_market_state(
        [0.0, float("nan")],
        _observation(),
        _model(bullish=5.0),
        biberion.SafetyLimits(),
    )
    assert result.state == 0
    assert result.safety_passed is False
    assert result.reason == "invalid_model_features_or_safety_inputs"
