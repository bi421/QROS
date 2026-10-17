from __future__ import annotations

import pytest

from researchos.orchestration.edge_validation_suite import (
    cusum_change_points,
    five_attack_overfitting_suite,
    incremental_log_likelihood_test,
    moving_block_bootstrap_ci,
    outcome_dependence,
    quarter_kelly,
    research_decision_gate,
)


def test_quarter_kelly_caps_risk_and_fails_closed_on_negative_expectancy():
    profitable = [1.0] * 60 + [-1.0] * 40
    result = quarter_kelly(profitable, minimum_trades=50, max_fraction=0.01)
    assert result["full_kelly_fraction"] == pytest.approx(0.2)
    assert result["fractional_kelly_fraction"] == pytest.approx(0.05)
    assert result["applied_fraction_after_cap"] == pytest.approx(0.01)
    assert result["decision"] == "DIAGNOSTIC_ONLY"

    losing = [1.0] * 40 + [-1.0] * 60
    blocked = quarter_kelly(losing, minimum_trades=50)
    assert blocked["applied_fraction_after_cap"] == 0.0
    assert blocked["decision"] == "NO_BET"


def test_quarter_kelly_rejects_short_samples_and_bad_values():
    result = quarter_kelly([1.0, -1.0], minimum_trades=100)
    assert result["applied_fraction_after_cap"] == 0.0
    assert result["decision"] == "NO_BET"
    with pytest.raises(ValueError, match="NONFINITE_RETURN"):
        quarter_kelly([1.0, float("nan")])


def test_autocorrelation_and_streaks_are_diagnostic_only():
    result = outcome_dependence([-1, -1, -1, 1, 1, -1, -1, 1, 1, 1, -1])
    assert len(result["signed_outcome_autocorrelation"]) == 10
    assert result["interpretation"] == "DESCRIPTIVE_ONLY_NO_AUTOMATIC_RISK_ADJUSTMENT"
    assert result["conditional_streak_diagnostics"]


def test_block_bootstrap_is_reproducible_and_reports_interval():
    pnl = [0.2, -0.1, 0.3, 0.1, -0.05] * 12
    first = moving_block_bootstrap_ci(pnl, block_length=5, repetitions=300, seed=9)
    second = moving_block_bootstrap_ci(pnl, block_length=5, repetitions=300, seed=9)
    assert first == second
    assert first["ci_lower"] <= first["ci_upper"]
    assert first["method"] == "MOVING_BLOCK_BOOTSTRAP_PERCENTILE"


def test_five_attacks_are_deterministic_and_best_asset_is_na_for_xauusd():
    pnl = [0.1, -0.02, 0.03, 0.04, -0.01, 0.02, 0.01, -0.03, 0.05, 0.02] * 5
    first = five_attack_overfitting_suite(pnl, seed=13, omission_repetitions=100)
    second = five_attack_overfitting_suite(pnl, seed=13, omission_repetitions=100)
    assert first == second
    assert first["attacks"]["best_asset_removal"]["status"] == "NOT_APPLICABLE_SINGLE_ASSET"
    assert first["attacks"]["chronological_chunk_stability"]["status"] == "TESTED"
    assert first["attacks"]["top_five_trade_removal"]["status"] == "TESTED"
    assert 0.0 <= first["robustness_score"] <= 1.0
    assert first["interpretation"] == "ROBUSTNESS_SCORE_IS_NOT_PROBABILITY_THAT_EDGE_IS_REAL"


def test_five_attacks_validate_metadata_lengths():
    with pytest.raises(ValueError, match="ASSET_LENGTH_MISMATCH"):
        five_attack_overfitting_suite([0.1] * 10, assets=["XAUUSD"])


def test_decision_gate_is_fail_closed_and_never_authorizes_execution():
    blocked = research_decision_gate(
        net_expectancy=0.1,
        bootstrap_ci_lower=-0.01,
        overfitting_score=1.0,
        fdr_passed=True,
        costs_verified=True,
        minimum_sample_passed=True,
        point_in_time_data_passed=True,
    )
    assert blocked["status"] == "NO_TRADE"
    assert blocked["execution_authorized"] is False
    assert "bootstrap_ci_lower_positive" in blocked["failed_checks"]

    candidate = research_decision_gate(
        net_expectancy=0.1,
        bootstrap_ci_lower=0.01,
        overfitting_score=1.0,
        fdr_passed=True,
        costs_verified=True,
        minimum_sample_passed=True,
        point_in_time_data_passed=True,
    )
    assert candidate["status"] == "CANDIDATE_FOR_FURTHER_REVIEW"
    assert candidate["execution_authorized"] is False


def test_incremental_log_likelihood_requires_paired_probabilities_and_reports_gain():
    outcomes = [0, 1] * 10
    baseline = [0.5] * 20
    augmented = [0.2 if y == 0 else 0.8 for y in outcomes]
    result = incremental_log_likelihood_test(outcomes, baseline, augmented)
    assert result["augmented_model_improved"] is True
    assert result["log_likelihood_improvement"] > 0
    assert 0 <= result["p_value_unadjusted"] <= 1


def test_cusum_detects_predefined_mean_shift_without_emitting_trade_signal():
    series = [0.0] * 15 + [2.0] * 15
    result = cusum_change_points(
        series, reference_mean=0.0, reference_std=1.0, drift=0.5, threshold=5.0
    )
    assert result["status"] == "ANOMALIES_FOUND"
    assert result["alarms"]
    assert result["interpretation"] == "ANOMALY_DIAGNOSTIC_NOT_TRADE_SIGNAL"
