import pytest

from researchos.probability.economic_cost import EconomicCostContext


def test_total_cost_and_net_effect_are_deterministic() -> None:
    context = EconomicCostContext(
        spread_cost=0.10,
        slippage_cost=0.20,
        commission_cost=0.05,
        other_cost=0.15,
    )
    assert context.total_cost == pytest.approx(0.50)
    assert context.net_effect(1.25) == pytest.approx(0.75)


@pytest.mark.parametrize(
    "field",
    ["spread_cost", "slippage_cost", "commission_cost", "other_cost"],
)
def test_cost_components_must_be_non_negative(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        EconomicCostContext(**{field: -0.01})


def test_cost_context_requires_a_unit() -> None:
    with pytest.raises(ValueError, match="unit"):
        EconomicCostContext(unit=" ")
