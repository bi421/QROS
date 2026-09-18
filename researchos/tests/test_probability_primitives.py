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
