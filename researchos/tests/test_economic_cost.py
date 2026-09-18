import pytest

from researchos.research_core.economic_cost import EconomicCostModel


def test_cost_model_is_explicit_and_deterministic():
    model = EconomicCostModel(commission_per_trade=0.001, spread_per_trade=0.002, slippage_per_trade=0.003)
    assert model.per_trade == pytest.approx(0.006)
    assert model.net_return(0.10, 10) == pytest.approx(0.04)
    assert model.to_dict()["per_trade"] == pytest.approx(0.006)


def test_negative_costs_and_trade_counts_are_rejected():
    with pytest.raises(ValueError):
        EconomicCostModel(slippage_per_trade=-0.001)
    with pytest.raises(ValueError):
        EconomicCostModel().net_return(0.1, -1)
