import pytest
from researchos.orchestration.empirical_state_edge import (
    empirical_state_probability,
    chi_square_goodness_of_fit,
    evaluate_state_table,
)


def test_empirical_probability_returns_rate_and_interval():
    r = empirical_state_probability(60, 100)
    assert r["probability"] == pytest.approx(0.6)
    assert r["wilson_lower"] < 0.6 < r["wilson_upper"]


def test_chi_square_fair_split_is_not_significant():
    r = chi_square_goodness_of_fit([50, 50], [0.5, 0.5])
    assert r["status"] == "TESTED" and r["chi_square"] == pytest.approx(0.0)
    assert r["p_value"] == pytest.approx(1.0)


def test_chi_square_detects_predeclared_deviation():
    r = chi_square_goodness_of_fit([70, 30], [0.5, 0.5])
    assert r["p_value"] < 0.01 and r["reject_at_0_05"]


def test_chi_square_refuses_small_expected_cells():
    r = chi_square_goodness_of_fit([98, 2], [0.99, 0.01], min_expected=5)
    assert r["status"] == "NOT_TESTABLE_EXPECTED_COUNTS_TOO_SMALL"
    assert r["p_value"] is None


def test_state_table_applies_fdr_and_minimum_sample():
    rows = [{"z": "high", "body": "large", "success": i < 70} for i in range(100)]
    rows += [{"z": "low", "body": "small", "success": i < 2} for i in range(5)]
    r = evaluate_state_table(
        rows, state_fields=["z", "body"], outcome_field="success", min_trials=30
    )
    assert r["state_count"] == 2
    assert r["states"][0]["probability"] == pytest.approx(0.7)
    assert r["states"][1]["test_status"] == "INSUFFICIENT_SAMPLE"
