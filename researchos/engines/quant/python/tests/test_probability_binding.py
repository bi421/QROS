import pytest

probability = pytest.importorskip("cpp_quant_engine.qros_probability")


def make_input(calibrated=True, stress=False):
    x = probability.Input()
    x.base_probability = 0.85
    x.latency_ms = 50 if stress else 5
    x.vxy = 14.5 if stress else 6.5
    x.dxy = 106.8 if stress else 101.2
    x.dxy_baseline = 101.2
    x.alpha_per_ms = 0.001
    x.beta_per_vxy_unit = 0.002
    x.gamma_per_dxy_point = 0.01
    x.gate_threshold = 0.70
    x.calibration_verified = calibrated
    return x


def test_probability_score_and_gate():
    result = probability.evaluate(make_input())
    assert result.estimated_success_probability == pytest.approx(0.832)
    assert result.research_gate_pass


def test_stress_case_score_is_computed_not_assumed():
    result = probability.evaluate(make_input(stress=True))
    assert result.estimated_success_probability == pytest.approx(0.715)


def test_unverified_calibration_fails_closed():
    assert not probability.evaluate(make_input(False)).research_gate_pass
