import pytest

from researchos.orchestration.net_expectancy_gate import evaluate_net_expectancy_gate


def _positive_gate(**overrides):
    args = {
        "win_probability": 0.7,
        "average_win": 2.0,
        "average_loss": 1.0,
        "roundtrip_cost": 0.1,
        "costs_verified": True,
        "net_returns": [0.8 + (i % 7) * 0.01 for i in range(240)],
        "bootstrap_replicates": 399,
        "seed": 17,
    }
    args.update(overrides)
    return evaluate_net_expectancy_gate(**args)


def test_unknown_costs_fail_closed():
    result = evaluate_net_expectancy_gate(
        win_probability=0.6, average_win=2.0, average_loss=1.0, roundtrip_cost=None
    )
    assert result["status"] == "NO_TRADE_COSTS_UNKNOWN"
    assert result["signal_allowed"] is False
    assert result["net_expectancy"] is None


def test_unverified_cost_audit_fails_closed():
    result = evaluate_net_expectancy_gate(
        win_probability=0.7,
        average_win=2.0,
        average_loss=1.0,
        roundtrip_cost=0.1,
        net_returns=[0.8] * 200,
    )
    assert result["status"] == "NO_TRADE_COST_AUDIT_UNVERIFIED"
    assert result["signal_allowed"] is False


def test_missing_net_returns_fail_closed():
    result = evaluate_net_expectancy_gate(
        win_probability=0.7,
        average_win=2.0,
        average_loss=1.0,
        roundtrip_cost=0.1,
        costs_verified=True,
    )
    assert result["status"] == "NO_TRADE_NET_RETURNS_MISSING"
    assert result["signal_allowed"] is False


def test_gate_requires_positive_point_expectancy_and_positive_bootstrap_ci():
    result = _positive_gate()
    assert result["signal_allowed"] is True
    assert result["net_expectancy"] == pytest.approx(1.0)
    assert result["ci_95_percent"][0] > 0
    assert result["ci_method"] == "moving_block_bootstrap"
    assert result["fractional_kelly_multiplier"] == pytest.approx(0.25)
    assert result["recommended_risk_fraction"] == pytest.approx(
        min(result["fractional_kelly_fraction_after_cost"], 0.01)
    )
    assert result["recommended_risk_fraction"] <= 0.01


def test_ci_including_zero_fails_closed_even_when_point_expectancy_is_positive():
    result = _positive_gate(net_returns=[(-1.0 if i % 2 else 1.0) for i in range(240)])
    assert result["net_expectancy"] > 0
    assert result["ci_95_percent"][0] <= 0
    assert result["signal_allowed"] is False
    assert result["recommended_risk_fraction"] == 0.0


def test_costs_can_turn_gross_positive_expectancy_into_no_trade():
    result = _positive_gate(roundtrip_cost=2.0)
    assert result["signal_allowed"] is False
    assert result["net_expectancy"] < 0


def test_insufficient_returns_fail_closed():
    result = _positive_gate(net_returns=[0.1] * 30)
    assert result["status"] == "NO_TRADE_INSUFFICIENT_NET_RETURNS"
    assert result["signal_allowed"] is False


def test_bootstrap_block_size_respects_label_horizon():
    result = _positive_gate(minimum_block_size=10)
    assert result["block_size"] >= 10
    assert result["minimum_block_size"] == 10


def test_explicit_bootstrap_block_size_below_label_horizon_is_rejected():
    with pytest.raises(ValueError, match="minimum_block_size"):
        _positive_gate(block_size=5, minimum_block_size=10)


def test_invalid_probability_rejected():
    with pytest.raises(ValueError, match="win_probability"):
        evaluate_net_expectancy_gate(
            win_probability=1.1, average_win=2.0, average_loss=1.0, roundtrip_cost=0.1
        )
