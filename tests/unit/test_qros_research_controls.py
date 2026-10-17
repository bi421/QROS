
import polars as pl
import pytest

from researchos.orchestration.qros_research_controls import (
    apply_bnf_mean_reversion,
    build_audit_record,
    calculate_quarter_kelly_size,
    unified_research_gate,
)


def test_risk_sizing_positive_edge_respects_two_percent_cap():
    out = calculate_quarter_kelly_size(win_probability=0.6, average_win=2.0, average_loss=1.0,
        cost_per_unit=0.05, equity=10000, entry_price=2000, stop_loss_price=1990,
        contract_multiplier=1.0, risk_limit_fraction=0.02)
    assert out["status"] == "CANDIDATE_FOR_RESEARCH_REVIEW"
    assert out["risk_budget"] <= 200.0 + 1e-9
    assert out["execution_authorized"] is False
    assert out["position_size"] >= 0


def test_risk_sizing_nonpositive_ev_fails_closed():
    out = calculate_quarter_kelly_size(win_probability=0.2, average_win=1.0, average_loss=1.0,
        cost_per_unit=0.1, equity=10000, entry_price=2000, stop_loss_price=1990,
        contract_multiplier=1.0)
    assert out["status"] == "NO_TRADE"
    assert out["position_size"] == 0


def test_risk_sizing_rejects_invalid_cap_and_nonfinite():
    with pytest.raises(ValueError):
        calculate_quarter_kelly_size(win_probability=0.6, average_win=2, average_loss=1,
            cost_per_unit=0, equity=10000, entry_price=2000, stop_loss_price=1990,
            contract_multiplier=1, risk_limit_fraction=0.03)
    with pytest.raises(ValueError):
        calculate_quarter_kelly_size(win_probability=float("nan"), average_win=2, average_loss=1,
            cost_per_unit=0, equity=10000, entry_price=2000, stop_loss_price=1990,
            contract_multiplier=1)


def test_bnf_requires_full_window_and_capacity_for_strong_signal():
    closes = [100.0] * 24 + [60.0]
    df = pl.DataFrame({"close": closes, "volume": [1.0] * 25})
    out = apply_bnf_mean_reversion(df)
    assert out["bnf_signal"][23] == "NO_TRADE"
    assert out["bnf_signal"][24] == "BUY_STRONG"
    blocked = apply_bnf_mean_reversion(df, capacity_cap=1.0)
    assert blocked["bnf_signal"][24] == "CANDIDATE"


def test_bnf_missing_columns_fail_closed():
    with pytest.raises(ValueError):
        apply_bnf_mean_reversion(pl.DataFrame({"close": [1.0, 2.0]}))


def test_unified_gate_fails_closed_and_insider_cannot_override():
    args = dict(net_expectancy=1, bootstrap_ci_lower=0.1, robustness_score=0.95,
        fdr_passed=True, costs_verified=True, minimum_sample_passed=True,
        point_in_time_data_passed=True, risk_sizing_status="CANDIDATE_FOR_RESEARCH_REVIEW",
        bnf_signal="BUY_STRONG", insider_cluster=True)
    assert unified_research_gate(**args)["status"] == "CANDIDATE_FOR_FURTHER_REVIEW"
    args["bootstrap_ci_lower"] = -0.1
    out = unified_research_gate(**args)
    assert out["status"] == "NO_TRADE"
    assert "bootstrap_ci_lower_positive" in out["failed_checks"]
    assert out["insider_cluster_changes_gate"] is False
    assert out["execution_authorized"] is False


def test_audit_record_is_deterministic_and_hashed():
    args = dict(input_payload={"close": 2000.0, "timestamp": "2026-01-01T00:00:00Z"},
        decision={"status": "NO_TRADE"}, source_commit="abc123", config_version="v1")
    a, b = build_audit_record(**args), build_audit_record(**args)
    assert a == b
    assert len(a["input_sha256"]) == 64
    assert len(a["decision_sha256"]) == 64
    assert a["execution_authorized"] is False

def test_bnf_rejects_unsorted_or_duplicate_timestamps():
    unsorted = pl.DataFrame({"timestamp": [2, 1], "close": [100.0, 90.0], "volume": [1.0, 1.0]})
    with pytest.raises(ValueError, match="TIMESTAMP_MUST_BE_SORTED_ASCENDING"):
        apply_bnf_mean_reversion(unsorted)
    duplicated = pl.DataFrame({"timestamp": [1, 1], "close": [100.0, 90.0], "volume": [1.0, 1.0]})
    with pytest.raises(ValueError, match="DUPLICATE_TIMESTAMPS_NOT_ALLOWED"):
        apply_bnf_mean_reversion(duplicated)
