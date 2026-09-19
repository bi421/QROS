"""Deterministic economic cost and slippage contracts for research evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EconomicCostContext:
    """Declared cost assumptions attached to a research result.

    Values use the same return/unit convention as the analysis result. The
    contract records assumptions; it does not invent market costs.
    """

    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    commission_cost: float = 0.0
    other_cost: float = 0.0
    currency: str = ""
    unit: str = "return"
    source: str = ""
    version: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("spread_cost", self.spread_cost),
            ("slippage_cost", self.slippage_cost),
            ("commission_cost", self.commission_cost),
            ("other_cost", self.other_cost),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
        if not self.unit.strip():
            raise ValueError("unit must not be empty")

    @property
    def total_cost(self) -> float:
        return (
            self.spread_cost
            + self.slippage_cost
            + self.commission_cost
            + self.other_cost
        )

    def net_effect(self, gross_effect: float) -> float:
        return gross_effect - self.total_cost


__all__ = ["EconomicCostContext"]
