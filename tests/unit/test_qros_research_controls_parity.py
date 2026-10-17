import pytest

from researchos.orchestration.qros_research_controls import calculate_quarter_kelly_size


def test_cpp_python_kelly_sizing_parity():
    native = pytest.importorskip("researchos.engines.quant.python.cpp_quant_engine.qros_research_controls")
    kwargs = dict(
        win_probability=0.6, average_win=2.0, average_loss=1.0, cost_per_unit=0.05,
        equity=10_000.0, entry_price=2_000.0, stop_loss_price=1_990.0,
        contract_multiplier=1.0,
    )
    py = calculate_quarter_kelly_size(**kwargs)
    cpp = native.risk_size(
        kwargs["win_probability"], kwargs["average_win"], kwargs["average_loss"],
        kwargs["cost_per_unit"], kwargs["equity"], kwargs["entry_price"],
        kwargs["stop_loss_price"], kwargs["contract_multiplier"],
        kwargs.get("risk_limit_fraction", 0.02), kwargs.get("fractional_kelly", 0.25),
    )
    assert cpp["status"] == py["status"]
    assert cpp["execution_authorized"] is False
    assert cpp["position_size"] == pytest.approx(py["position_size"], rel=1e-12)
