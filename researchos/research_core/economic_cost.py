"""Explicit economic-cost model contract for governed research results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomicCostModel:
    """Deterministic cost assumptions; values are expressed in return units."""

    commission_per_trade: float = 0.0
    spread_per_trade: float = 0.0
    slippage_per_trade: float = 0.0
    market_impact_per_trade: float = 0.0
    fixed_cost_per_trade: float = 0.0

    def __post_init__(self) -> None:
        values = (self.commission_per_trade, self.spread_per_trade, self.slippage_per_trade, self.market_impact_per_trade, self.fixed_cost_per_trade)
        if any(v < 0 for v in values):
            raise ValueError("economic cost components must be >= 0")

    @property
    def per_trade(self) -> float:
        return sum((self.commission_per_trade, self.spread_per_trade, self.slippage_per_trade, self.market_impact_per_trade, self.fixed_cost_per_trade))

    def net_return(self, gross_return: float, trade_count: int) -> float:
        if trade_count < 0:
            raise ValueError("trade_count must be >= 0")
        return gross_return - self.per_trade * trade_count

    def to_dict(self) -> dict[str, float]:
        return {
            "commission_per_trade": self.commission_per_trade,
            "spread_per_trade": self.spread_per_trade,
            "slippage_per_trade": self.slippage_per_trade,
            "market_impact_per_trade": self.market_impact_per_trade,
            "fixed_cost_per_trade": self.fixed_cost_per_trade,
            "per_trade": self.per_trade,
        }


__all__ = ["EconomicCostModel"]
