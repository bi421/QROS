"""Immutable contracts for the ResearchOS decision-risk boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RISK_SCHEMA_VERSION = "risk.v1"


@dataclass(frozen=True)
class TradeStatistics:
    """Historical payoff statistics used by the risk calculation."""

    average_win: float
    average_loss: float
    sample_size: int = 0

    def validate(self) -> None:
        if self.average_win <= 0:
            raise ValueError("average_win must be positive")
        if self.average_loss <= 0:
            raise ValueError("average_loss must be positive")
        if self.sample_size < 0:
            raise ValueError("sample_size must be non-negative")

    @property
    def win_loss_ratio(self) -> float:
        self.validate()
        return self.average_win / self.average_loss

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeStatistics:
        return cls(
            average_win=float(data["average_win"]),
            average_loss=float(data["average_loss"]),
            sample_size=int(data.get("sample_size", 0)),
        )


@dataclass(frozen=True)
class RiskPolicy:
    """Explicit constraints applied after Kelly sizing."""

    fractional_kelly: float = 0.25
    max_risk_fraction: float = 0.01
    max_position_fraction: float = 1.0

    def validate(self) -> None:
        if not 0 < self.fractional_kelly <= 1:
            raise ValueError("fractional_kelly must be in (0, 1]")
        if not 0 <= self.max_risk_fraction <= 1:
            raise ValueError("max_risk_fraction must be in [0, 1]")
        if not 0 <= self.max_position_fraction <= 1:
            raise ValueError("max_position_fraction must be in [0, 1]")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskPolicy:
        return cls(
            fractional_kelly=float(data.get("fractional_kelly", 0.25)),
            max_risk_fraction=float(data.get("max_risk_fraction", 0.01)),
            max_position_fraction=float(data.get("max_position_fraction", 1.0)),
        )


@dataclass(frozen=True)
class RiskInput:
    """Cross-block input consumed by the risk engine."""

    asset: str
    direction: str
    probability: float
    account_equity: float
    trade_statistics: TradeStatistics
    risk_policy: RiskPolicy = RiskPolicy()
    risk_per_unit: float | None = None
    research_id: str | None = None
    probability_method: str | None = None
    probability_calculation_version: str | None = None
    probability_calibration_status: str | None = None
    assessment_hash: str | None = None

    def validate(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.direction.strip():
            raise ValueError("direction must not be empty")
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be in [0, 1]")
        if self.account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if self.risk_per_unit is not None and self.risk_per_unit <= 0:
            raise ValueError("risk_per_unit must be positive when supplied")
        self.trade_statistics.validate()
        self.risk_policy.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": RISK_SCHEMA_VERSION,
            "asset": self.asset,
            "direction": self.direction,
            "probability": self.probability,
            "account_equity": self.account_equity,
            "trade_statistics": {
                "average_win": self.trade_statistics.average_win,
                "average_loss": self.trade_statistics.average_loss,
                "sample_size": self.trade_statistics.sample_size,
            },
            "risk_policy": {
                "fractional_kelly": self.risk_policy.fractional_kelly,
                "max_risk_fraction": self.risk_policy.max_risk_fraction,
                "max_position_fraction": self.risk_policy.max_position_fraction,
            },
            "risk_per_unit": self.risk_per_unit,
            "research_id": self.research_id,
            "probability_method": self.probability_method,
            "probability_calculation_version": self.probability_calculation_version,
            "probability_calibration_status": self.probability_calibration_status,
            "assessment_hash": self.assessment_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskInput:
        version = data.get("schema_version", RISK_SCHEMA_VERSION)
        if version != RISK_SCHEMA_VERSION:
            raise ValueError(f"unsupported risk schema: {version}")
        request = cls(
            asset=str(data["asset"]),
            direction=str(data["direction"]),
            probability=float(data["probability"]),
            account_equity=float(data["account_equity"]),
            trade_statistics=TradeStatistics.from_dict(data["trade_statistics"]),
            risk_policy=RiskPolicy.from_dict(data.get("risk_policy", {})),
            risk_per_unit=(float(data["risk_per_unit"]) if data.get("risk_per_unit") is not None else None),
            research_id=data.get("research_id"),
            probability_method=data.get("probability_method"),
            probability_calculation_version=data.get("probability_calculation_version"),
            probability_calibration_status=data.get("probability_calibration_status"),
            assessment_hash=data.get("assessment_hash"),
        )
        request.validate()
        return request


@dataclass(frozen=True)
class RiskCalculation:
    """Deterministic risk-sizing result; never an order or broker instruction."""

    schema_version: str
    asset: str
    direction: str
    probability: float
    win_loss_ratio: float
    full_kelly_fraction: float
    fractional_kelly_fraction: float
    final_risk_fraction: float
    risk_amount: float
    position_size: float | None
    capped: bool
    status: str
    research_id: str | None = None
    probability_method: str | None = None
    probability_calculation_version: str | None = None
    probability_calibration_status: str | None = None
    assessment_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "asset": self.asset,
            "direction": self.direction,
            "probability": self.probability,
            "win_loss_ratio": self.win_loss_ratio,
            "full_kelly_fraction": self.full_kelly_fraction,
            "fractional_kelly_fraction": self.fractional_kelly_fraction,
            "final_risk_fraction": self.final_risk_fraction,
            "risk_amount": self.risk_amount,
            "position_size": self.position_size,
            "capped": self.capped,
            "status": self.status,
            "research_id": self.research_id,
            "probability_method": self.probability_method,
            "probability_calculation_version": self.probability_calculation_version,
            "probability_calibration_status": self.probability_calibration_status,
            "assessment_hash": self.assessment_hash,
        }
