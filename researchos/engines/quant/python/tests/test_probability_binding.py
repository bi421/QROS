import pytest
probability = pytest.importorskip("cpp_quant_engine.qros_probability")
def make_input(calibrated=True):
    x=probability.Input()
    x.base_probability=.85; x.latency_ms=5; x.vxy=6.5; x.dxy=101.2; x.dxy_baseline=101.2
    x.alpha_per_ms=.001; x.beta_per_vxy_unit=.002; x.gamma_per_dxy_point=.01
    x.gate_threshold=.70; x.calibration_verified=calibrated
    return x
def test_probability_score_and_gate():
    r=probability.evaluate(make_input())
    assert r.estimated_success_probability == pytest.approx(.832)
    assert r.research_gate_pass
def test_unverified_calibration_fails_closed():
    assert not probability.evaluate(make_input(False)).research_gate_pass
