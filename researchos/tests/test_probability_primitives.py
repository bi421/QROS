from __future__ import annotations


import pytest

from researchos.probability import (
    ProbabilityAnalysis,
    ProbabilityMethod,
    expected_value,
    historical_expected_shortfall,
    historical_var,
    kelly_fraction,
    mutual_information,
    shannon_entropy,
)


def test_expected_value_matches_discrete_definition() -> None:
    assert expected_value((0.4, 0.6), (10.0, -5.0)) == pytest.approx(1.0)


def test_kelly_fraction_uses_declared_binary_odds() -> None:
    assert kelly_fraction(0.6, 0.4, 1.0) == pytest.approx(0.2)


def test_kelly_rejects_inconsistent_probabilities() -> None:
    with pytest.raises(ValueError, match="must equal 1"):
        kelly_fraction(0.6, 0.5, 1.0)


def test_shannon_entropy_is_zero_for_constant_state() -> None:
    assert shannon_entropy(["up"] * 10) == pytest.approx(0.0)


def test_shannon_entropy_is_one_bit_for_two_equally_likely_states() -> None:
    assert shannon_entropy(["up", "down"], base=2.0) == pytest.approx(1.0)


def test_mutual_information_is_zero_for_independent_cartesian_sample() -> None:
    x = [0, 0, 1, 1]
    y = [0, 1, 0, 1]
    assert mutual_information(x, y) == pytest.approx(0.0)


def test_mutual_information_is_positive_for_identical_states() -> None:
    assert mutual_information([0, 1, 0, 1], [0, 1, 0, 1]) == pytest.approx(1.0)


def test_historical_var_and_expected_shortfall_use_positive_loss_convention() -> None:
    returns = [0.10, 0.02, -0.01, -0.05, -0.20]
    var = historical_var(returns, 0.8)
    es = historical_expected_shortfall(returns, 0.8)
    assert var == pytest.approx(0.08)
    assert es >= var


def test_probability_analysis_requires_provenance() -> None:
    analysis = ProbabilityAnalysis(
        analysis_id="pa-001",
        claim_id="claim-001",
        method=ProbabilityMethod.EXPECTED_VALUE,
        population_definition="XAUUSD M1 2021-2025",
        time_window="2021-01-01/2025-12-31",
        data_version="dataset-v1",
        data_hash="a" * 64,
        sample_size=1000,
        point_estimate=0.001,
        probability_definition="empirical mean return per event",
        integrity_gate_status="PASSED",
    )

    assert analysis.to_dict()["method"] == "expected_value"
    assert analysis.to_dict()["data_hash"] == "a" * 64


def test_probability_analysis_rejects_invalid_uncertainty_interval() -> None:
    with pytest.raises(ValueError, match="lower bound"):
        ProbabilityAnalysis(
            analysis_id="pa-001",
            claim_id="claim-001",
            method=ProbabilityMethod.DESCRIPTIVE,
            population_definition="sample",
            time_window="2025",
            data_version="v1",
            data_hash="a" * 64,
            uncertainty_interval=(0.5, 0.1),
        )


def test_probability_analysis_rejects_unknown_governance_status() -> None:
    with pytest.raises(ValueError, match="out_of_sample_status"):
        ProbabilityAnalysis(
            analysis_id="pa-002",
            claim_id="claim-001",
            method=ProbabilityMethod.DESCRIPTIVE,
            population_definition="sample",
            time_window="2025",
            data_version="v1",
            data_hash="a" * 64,
            out_of_sample_status="MAYBE",
        )


def test_probability_analysis_requires_selection_count_for_multiple_testing_context() -> None:
    with pytest.raises(ValueError, match="selection_count"):
        ProbabilityAnalysis(
            analysis_id="pa-003",
            claim_id="claim-001",
            method=ProbabilityMethod.DESCRIPTIVE,
            population_definition="sample",
            time_window="2025",
            data_version="v1",
            data_hash="a" * 64,
            multiple_testing_context="holm alpha=0.05",
        )


def test_probability_analysis_rejects_non_positive_selection_count() -> None:
    with pytest.raises(ValueError, match="selection_count"):
        ProbabilityAnalysis(
            analysis_id="pa-004",
            claim_id="claim-001",
            method=ProbabilityMethod.DESCRIPTIVE,
            population_definition="sample",
            time_window="2025",
            data_version="v1",
            data_hash="a" * 64,
            selection_count=0,
        )


def test_brier_score_returns_deterministic_calibration_diagnostics():
    result = brier_score((0.9, 0.2, 0.7, 0.4), (1, 0, 1, 0))
    assert result.brier_score == pytest.approx(0.075)
    assert result.sample_size == 4
    assert result.mean_predicted_probability == pytest.approx(0.55)
    assert result.observed_frequency == pytest.approx(0.5)


def test_brier_score_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="probabilities"):
        brier_score((1.2,), (1,))
    with pytest.raises(ValueError, match="outcomes"):
        brier_score((0.5,), (2,))


def test_wilson_interval_is_bounded_and_contains_observed_rate():
    low, high = wilson_interval(50, 100)
    assert 0.0 <= low < 0.5 < high <= 1.0


def test_wilson_interval_rejects_invalid_counts():
    with pytest.raises(ValueError, match="successes"):
        wilson_interval(101, 100)
