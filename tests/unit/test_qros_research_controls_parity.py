import pytest

from researchos.orchestration.qros_research_controls import calculate_quarter_kelly_size


def test_cpp_python_kelly_sizing_parity():
    native = pytest.importorskip("researchos.engines.quant.python.cpp_quant_engine.qros_research_controls")
    args = dict(win_probability=0.6, average_win=2.0, average_loss=1.0, cost_per_unit=0.05,
        equity=10000.0, entry_price=2000.0, stop_loss_price=1990.0, contract_multiplier=1.0,
        risk_limit_fraction=0.02, fractional_kelly=0.25)
    py = calculate_quarter_kelly_size(**args)
    cpp = native.risk_size(args["win_probability"], args["average_win"], args["average_loss"],
        args["cost_per_unit"], args["equity"], args["entry_price"], args["stop_loss_price"],
        args["contract_multiplier"], args["risk_limit_fraction"], args["fractional_kelly"])
    assert cpp["status"] == py["status"]
    assert cpp["net_expectancy"] == pytest.approx(py["net_expectancy"], rel=1e-12)
    assert cpp["position_size"] == pytest.approx(py["position_size"], rel=1e-12)
    assert cpp["execution_authorized"] is False


def test_cpp_python_bnf_signal_parity():
    native = pytest.importorskip("researchos.engines.quant.python.cpp_quant_engine.qros_research_controls")
    import polars as pl
    from researchos.orchestration.qros_research_controls import apply_bnf_mean_reversion
    close = [100.0] * 24 + [60.0, 70.0, 80.0]
    volume = [1.0] * len(close)
    py = apply_bnf_mean_reversion(pl.DataFrame({"close": close, "volume": volume}))
    cpp = native.bnf_signals(close, volume)
    assert list(py["bnf_signal"]) == list(cpp)
