import pytest

from researchos.orchestration.binomial_edge import binomial_edge_test
from researchos.orchestration.statistical_validation import (
    benjamini_hochberg,
    effective_sample_size,
    lag_autocorrelation,
)


def test_fair_coin_edge_test_detects_40_successes_out_of_60():
    result = binomial_edge_test(40, 60, null_probability=0.5, alternative="greater")
    assert result["observed_rate"] == pytest.approx(2 / 3)
    assert result["exact_p_value"] < 0.05
    assert result["reject_null_at_0_05"] is True
    assert (
        result["wilson_interval_lower"] < result["observed_rate"] < result["wilson_interval_upper"]
    )


def test_fair_coin_small_sample_does_not_claim_edge():
    result = binomial_edge_test(6, 10, null_probability=0.5, alternative="greater")
    assert result["exact_p_value"] > 0.05
    assert result["reject_null_at_0_05"] is False


def test_binary_reversal_event_can_use_one_third_null_if_justified():
    result = binomial_edge_test(40, 100, null_probability=1 / 3, alternative="greater")
    assert result["null_probability"] == pytest.approx(1 / 3)
    assert result["observed_rate"] == pytest.approx(0.4)


def test_lag1_autocorrelation_and_ess_diagnostic():
    rho = lag_autocorrelation([0, 1, 0, 1, 0, 1])
    assert rho is not None
    result = effective_sample_size(100, rho)
    assert result["n"] == 100
    assert 1 <= result["n_effective_approx"] <= 100


def test_bh_adjustment_preserves_input_order_and_adjusts_p_values():
    result = benjamini_hochberg([0.01, 0.04, 0.03, 0.8], q=0.05)
    assert [x["p_value"] for x in result] == [0.01, 0.04, 0.03, 0.8]
    assert result[0]["p_adjusted_bh"] == pytest.approx(0.04)
    assert result[3]["reject_at_q"] is False


@pytest.mark.parametrize(
    "args,kwargs",
    [
        ((0, 0), {}),
        ((11, 10), {}),
        ((1, 10), {"null_probability": 1.0}),
        ((1, 10), {"alternative": "up"}),
        ((1, 10), {"confidence": 0.92}),
    ],
)
def test_invalid_binomial_test_inputs_rejected(args, kwargs):
    with pytest.raises(ValueError):
        binomial_edge_test(*args, **kwargs)
