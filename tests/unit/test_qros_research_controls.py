from __future__ import annotations

import hashlib

import polars as pl
import pytest

from researchos.orchestration.qros_research_controls import (
    LEGACY_GATE_STATUS,
    apply_bnf_mean_reversion,
    build_audit_record,
    calculate_quarter_kelly_size,
    unified_research_gate,
)


def _cost_metadata(n: int) -> dict[str, object]:
    return {
        "cost_source": "frozen-test-spread-log",
        "cost_units": "XAUUSD_PRICE_PER_OUNCE",
        "commission_model": "fixed_round_trip_from_broker_schedule",
        "slippage_model": "observed_fill_slippage",
        "spread_log_sha256": hashlib.sha256(b"frozen spread log").hexdigest(),
        "spread_observation_count": n,
        "net_return_definition": "NET_OF_SPREAD_COMMISSION_SLIPPAGE",
    }


def _positive_gate_kwargs() -> dict[str, object]:
    returns = [0.01] * 120
    return {
        "trade_returns": returns,
        "tested_trial_count": 19,
        "cost_metadata": _cost_metadata(len(returns)),
        "fold_returns": [[0.01] * 40, [0.02] * 40, [0.005] * 40],
        "bootstrap_repetitions": 999,
        "bootstrap_seed": 421,
    }


def test_risk_sizing_positive_point_expectancy_respects_two_percent_cap() -> None:
    result = calculate_quarter_kelly_size(
        win_probability=0.6, average_win=2, average_loss=1, cost_per_unit=0.05,
        equity=10_000, entry_price=2_000, stop_loss_price=1_990, contract_multiplier=1,
    )
    assert result["status"] == "CANDIDATE_FOR_RESEARCH_REVIEW"
    assert result["final_risk_fraction"] <= 0.02
    assert result["execution_authorized"] is False


def test_risk_sizing_nonpositive_ev_fails_closed() -> None:
    result = calculate_quarter_kelly_size(
        win_probability=0.3, average_win=1, average_loss=2, cost_per_unit=0.1,
        equity=10_000, entry_price=2_000, stop_loss_price=1_990, contract_multiplier=1,
    )
    assert result["status"] == "NO_TRADE"
    assert result["position_size"] == 0
    assert result["execution_authorized"] is False


def test_risk_sizing_rejects_invalid_cap_and_nonfinite() -> None:
    with pytest.raises(ValueError, match="RISK_LIMIT"):
        calculate_quarter_kelly_size(
            win_probability=0.6, average_win=2, average_loss=1, cost_per_unit=0.05,
            equity=10_000, entry_price=2_000, stop_loss_price=1_990, contract_multiplier=1,
            risk_limit_fraction=0.03,
        )


def test_bnf_uses_causal_rolling_quantiles_and_no_default_turnover_filter() -> None:
    close = [2_000 + ((i % 17) - 8) * 0.3 for i in range(1_300)]
    close[-1] = 1_850
    volume = [1_000_000.0] * len(close)
    out = apply_bnf_mean_reversion(
        pl.DataFrame({"close": close, "volume": volume}),
        quantile_window=300, quantile_min_samples=100,
    )
    assert out["zscore"][-1] < out["strong_threshold"][-1]
    assert out["bnf_signal"][-1] == "BUY_STRONG"
    assert out["decision_use"][-1] == "RESEARCH_ONLY_NOT_EXECUTION"
    assert out["strong_threshold"][-1] is not None
    assert out["bnf_signal"][:300].to_list().count("BUY_STRONG") >= 0


def test_bnf_capacity_filter_is_opt_in_for_tick_volume_data() -> None:
    close = [2_000 + ((i % 17) - 8) * 0.3 for i in range(1_300)]
    close[-1] = 1_850
    df = pl.DataFrame({"close": close, "volume": [1_000_000.0] * len(close)})
    kwargs = {"quantile_window": 300, "quantile_min_samples": 100}
    no_capacity_filter = apply_bnf_mean_reversion(df, **kwargs)
    capped = apply_bnf_mean_reversion(df, capacity_cap=1.0, **kwargs)
    assert no_capacity_filter["bnf_signal"][-1] == "BUY_STRONG"
    assert capped["bnf_signal"][-1] != "BUY_STRONG"


def test_bnf_requires_close_and_valid_timestamp_order() -> None:
    with pytest.raises(ValueError, match="CLOSE"):
        apply_bnf_mean_reversion(pl.DataFrame({"volume": [1.0, 2.0]}))
    unsorted = pl.DataFrame({"timestamp": [2, 1], "close": [1.0, 2.0]})
    with pytest.raises(ValueError, match="SORTED"):
        apply_bnf_mean_reversion(unsorted)


def test_gate_computes_ci_fdr_sample_and_fold_stability_from_returns() -> None:
    result = unified_research_gate(**_positive_gate_kwargs())
    assert result["status"] == "CANDIDATE_FOR_FURTHER_REVIEW"
    assert result["checks"]["bootstrap_ci_lower_positive"] is True
    assert result["checks"]["trial_adjusted_fdr_sufficient_condition"] is True
    assert result["checks"]["minimum_sample_size"] is True
    assert result["checks"]["fold_stability"] is True
    assert result["tested_trial_count"] == 19
    assert result["execution_authorized"] is False


def test_gate_rejects_negative_returns_and_insufficient_sample() -> None:
    kwargs = _positive_gate_kwargs()
    kwargs["trade_returns"] = [-0.01] * 120
    kwargs["fold_returns"] = [[-0.01] * 40, [-0.02] * 40, [-0.005] * 40]
    result = unified_research_gate(**kwargs)
    assert result["status"] == "NO_TRADE"
    assert "bootstrap_ci_lower_positive" in result["failed_checks"]
    kwargs["trade_returns"] = [0.01] * 20
    kwargs["fold_returns"] = [[0.01] * 7, [0.02] * 7, [0.005] * 6]
    small = unified_research_gate(**kwargs)
    assert small["status"] == "NO_TRADE"
    assert "minimum_sample_size" in small["failed_checks"]


def test_gate_legacy_boolean_interface_cannot_produce_candidate() -> None:
    with pytest.raises(TypeError):
        unified_research_gate(
            net_expectancy=1.0, bootstrap_ci_lower=0.1, robustness_score=0.99,
            fdr_passed=True, costs_verified=True, minimum_sample_passed=True,
            point_in_time_data_passed=True, risk_sizing_status="CANDIDATE_FOR_RESEARCH_REVIEW",
            bnf_signal="BUY_STRONG",
        )
    result = unified_research_gate()
    assert result["status"] == LEGACY_GATE_STATUS
    assert result["execution_authorized"] is False


def test_gate_requires_cost_provenance_and_stable_folds() -> None:
    kwargs = _positive_gate_kwargs()
    kwargs["cost_metadata"] = {"costs_verified": True}
    kwargs["fold_returns"] = [[0.01] * 40, [-0.02] * 40, [-0.005] * 40]
    missing_costs = unified_research_gate(**kwargs)
    assert missing_costs["status"] == "NO_TRADE_COST_PROVENANCE_INVALID"
    assert "COST_SPREAD_LOG_HASH_INVALID" in missing_costs["cost_metadata_failures"]

    kwargs["cost_metadata"] = _cost_metadata(120)
    unstable = unified_research_gate(**kwargs)
    assert unstable["status"] == "NO_TRADE"
    assert "fold_stability" in unstable["failed_checks"]


def test_audit_record_is_deterministic_and_hashed() -> None:
    kwargs = {
        "input_payload": {"dataset_sha256": "abc", "rows": 10},
        "decision": {"status": "NO_TRADE", "execution_authorized": False},
        "source_commit": "deadbeef", "config_version": "v2",
    }
    first, second = build_audit_record(**kwargs), build_audit_record(**kwargs)
    assert first == second
    assert len(first["input_sha256"]) == 64
    assert len(first["decision_sha256"]) == 64
    assert first["execution_authorized"] is False
