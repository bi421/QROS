"""Immutable contracts for the ResearchOS risk-management boundary."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

RISK_SCHEMA_VERSION = "risk.v2"
RISK_AUDIT_SCHEMA_VERSION = "risk.audit.v1"
RISK_TOLERANCE = 1e-12


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


class ExecutionMode(str, Enum):
    """Execution context requested by a caller."""

    RESEARCH = "RESEARCH"
    PAPER = "PAPER"
    LIVE = "LIVE"


class StrategyState(str, Enum):
    """Governed strategy lifecycle."""

    RESEARCH = "RESEARCH"
    VALIDATED = "VALIDATED"
    RISK_REVIEW = "RISK_REVIEW"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    DEPLOYMENT_ELIGIBLE = "DEPLOYMENT_ELIGIBLE"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


_ALLOWED_STRATEGY_TRANSITIONS: dict[StrategyState, frozenset[StrategyState]] = {
    StrategyState.RESEARCH: frozenset({StrategyState.VALIDATED}),
    StrategyState.VALIDATED: frozenset({StrategyState.RISK_REVIEW}),
    StrategyState.RISK_REVIEW: frozenset(
        {StrategyState.PAPER_ELIGIBLE, StrategyState.SUSPENDED}
    ),
    StrategyState.PAPER_ELIGIBLE: frozenset(
        {StrategyState.DEPLOYMENT_ELIGIBLE, StrategyState.SUSPENDED}
    ),
    StrategyState.DEPLOYMENT_ELIGIBLE: frozenset(
        {StrategyState.ACTIVE, StrategyState.SUSPENDED}
    ),
    StrategyState.ACTIVE: frozenset(
        {StrategyState.SUSPENDED, StrategyState.RETIRED}
    ),
    StrategyState.SUSPENDED: frozenset(
        {StrategyState.RISK_REVIEW, StrategyState.RETIRED}
    ),
    StrategyState.RETIRED: frozenset(),
}


def validate_strategy_transition(
    current: StrategyState,
    target: StrategyState,
) -> None:
    """Fail closed unless the strategy follows the governed state machine."""
    if target not in _ALLOWED_STRATEGY_TRANSITIONS[current]:
        raise ValueError(
            f"invalid strategy transition: {current.value} -> {target.value}"
        )


@dataclass(frozen=True)
class TradeStatistics:
    """Historical payoff statistics used by the sizing calculation."""

    average_win: float
    average_loss: float
    sample_size: int = 0

    def validate(self) -> None:
        _require_finite("average_win", self.average_win)
        _require_finite("average_loss", self.average_loss)
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
    """Versioned hard/soft risk limits.

    Existing sizing fields remain backward compatible. Governance fields model
    account, strategy, portfolio, exposure, and operational hard stops.
    """

    fractional_kelly: float = 0.25
    max_risk_fraction: float = 0.01
    max_position_fraction: float = 1.0

    target_risk_fraction: float = 0.0025
    max_loss_per_trade_fraction: float = 0.005
    max_daily_loss_fraction: float = 0.02
    max_total_drawdown_fraction: float = 0.06
    max_strategy_loss_fraction: float = 0.03
    max_portfolio_open_risk_fraction: float = 0.01
    max_gross_exposure_multiple: float = 3.0
    max_single_instrument_exposure_multiple: float = 1.5
    warning_utilization_fraction: float = 0.80

    version: str = "RISK_POLICY_V2"

    def validate(self) -> None:
        for name in (
            "fractional_kelly",
            "max_risk_fraction",
            "max_position_fraction",
            "target_risk_fraction",
            "max_loss_per_trade_fraction",
            "max_daily_loss_fraction",
            "max_total_drawdown_fraction",
            "max_strategy_loss_fraction",
            "max_portfolio_open_risk_fraction",
            "max_gross_exposure_multiple",
            "max_single_instrument_exposure_multiple",
            "warning_utilization_fraction",
        ):
            _require_finite(name, float(getattr(self, name)))

        if not 0 < self.fractional_kelly <= 1:
            raise ValueError("fractional_kelly must be in (0, 1]")
        if not 0 <= self.max_risk_fraction <= 1:
            raise ValueError("max_risk_fraction must be in [0, 1]")
        if not 0 <= self.max_position_fraction <= 1:
            raise ValueError("max_position_fraction must be in [0, 1]")
        if not 0 < self.target_risk_fraction <= 1:
            raise ValueError("target_risk_fraction must be in (0, 1]")
        if not 0 < self.max_loss_per_trade_fraction <= 1:
            raise ValueError("max_loss_per_trade_fraction must be in (0, 1]")
        if not 0 < self.max_daily_loss_fraction <= 1:
            raise ValueError("max_daily_loss_fraction must be in (0, 1]")
        if not 0 < self.max_total_drawdown_fraction <= 1:
            raise ValueError("max_total_drawdown_fraction must be in (0, 1]")
        if not 0 < self.max_strategy_loss_fraction <= 1:
            raise ValueError("max_strategy_loss_fraction must be in (0, 1]")
        if not 0 < self.max_portfolio_open_risk_fraction <= 1:
            raise ValueError("max_portfolio_open_risk_fraction must be in (0, 1]")
        if self.max_gross_exposure_multiple <= 0:
            raise ValueError("max_gross_exposure_multiple must be positive")
        if self.max_single_instrument_exposure_multiple <= 0:
            raise ValueError(
                "max_single_instrument_exposure_multiple must be positive"
            )
        if not 0 < self.warning_utilization_fraction <= 1:
            raise ValueError("warning_utilization_fraction must be in (0, 1]")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskPolicy:
        return cls(
            fractional_kelly=float(data.get("fractional_kelly", 0.25)),
            max_risk_fraction=float(data.get("max_risk_fraction", 0.01)),
            max_position_fraction=float(data.get("max_position_fraction", 1.0)),
            target_risk_fraction=float(data.get("target_risk_fraction", 0.0025)),
            max_loss_per_trade_fraction=float(
                data.get("max_loss_per_trade_fraction", 0.005)
            ),
            max_daily_loss_fraction=float(
                data.get("max_daily_loss_fraction", 0.02)
            ),
            max_total_drawdown_fraction=float(
                data.get("max_total_drawdown_fraction", 0.06)
            ),
            max_strategy_loss_fraction=float(
                data.get("max_strategy_loss_fraction", 0.03)
            ),
            max_portfolio_open_risk_fraction=float(
                data.get("max_portfolio_open_risk_fraction", 0.01)
            ),
            max_gross_exposure_multiple=float(
                data.get("max_gross_exposure_multiple", 3.0)
            ),
            max_single_instrument_exposure_multiple=float(
                data.get("max_single_instrument_exposure_multiple", 1.5)
            ),
            warning_utilization_fraction=float(
                data.get("warning_utilization_fraction", 0.80)
            ),
            version=str(data.get("version", "RISK_POLICY_V2")),
        )


@dataclass(frozen=True)
class RiskInput:
    """Probability and payoff input consumed by the sizing engine."""

    asset: str
    direction: str
    probability: float
    account_equity: float
    trade_statistics: TradeStatistics
    risk_policy: RiskPolicy = RiskPolicy()
    risk_per_unit: float | None = None
    research_id: str | None = None
    probability_method: str | None = None
    probability_calibration_status: str | None = None

    def validate(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.direction.strip():
            raise ValueError("direction must not be empty")
        _require_finite("probability", self.probability)
        if not 0 <= self.probability <= 1:
            raise ValueError("probability must be in [0, 1]")
        _require_finite("account_equity", self.account_equity)
        if self.account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if self.risk_per_unit is not None:
            _require_finite("risk_per_unit", self.risk_per_unit)
            if self.risk_per_unit <= 0:
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
                "target_risk_fraction": self.risk_policy.target_risk_fraction,
                "max_loss_per_trade_fraction": self.risk_policy.max_loss_per_trade_fraction,
                "max_daily_loss_fraction": self.risk_policy.max_daily_loss_fraction,
                "max_total_drawdown_fraction": self.risk_policy.max_total_drawdown_fraction,
                "max_strategy_loss_fraction": self.risk_policy.max_strategy_loss_fraction,
                "max_portfolio_open_risk_fraction": self.risk_policy.max_portfolio_open_risk_fraction,
                "max_gross_exposure_multiple": self.risk_policy.max_gross_exposure_multiple,
                "max_single_instrument_exposure_multiple": self.risk_policy.max_single_instrument_exposure_multiple,
                "warning_utilization_fraction": self.risk_policy.warning_utilization_fraction,
                "version": self.risk_policy.version,
            },
            "risk_per_unit": self.risk_per_unit,
            "research_id": self.research_id,
            "probability_method": self.probability_method,
            "probability_calibration_status": self.probability_calibration_status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskInput:
        version = data.get("schema_version", RISK_SCHEMA_VERSION)
        if version not in {"risk.v1", RISK_SCHEMA_VERSION}:
            raise ValueError(f"unsupported risk schema: {version}")
        request = cls(
            asset=str(data["asset"]),
            direction=str(data["direction"]),
            probability=float(data["probability"]),
            account_equity=float(data["account_equity"]),
            trade_statistics=TradeStatistics.from_dict(data["trade_statistics"]),
            risk_policy=RiskPolicy.from_dict(data.get("risk_policy", {})),
            risk_per_unit=(
                float(data["risk_per_unit"])
                if data.get("risk_per_unit") is not None
                else None
            ),
            research_id=data.get("research_id"),
            probability_method=data.get("probability_method"),
            probability_calibration_status=data.get(
                "probability_calibration_status"
            ),
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
        }


@dataclass(frozen=True)
class RiskAccountSnapshot:
    """Immutable point-in-time account and portfolio risk ledger."""

    equity: float
    day_start_equity: float
    high_water_mark: float
    strategy_reference_equity: float
    strategy_loss_amount: float
    open_risk_amount: float
    gross_exposure_amount: float
    instrument_exposure_amount: float
    realized_pnl: float
    unrealized_pnl: float
    trading_costs: float
    available_margin: float | None = None
    kill_switch_active: bool = False

    def validate(self) -> None:
        numeric = {
            "equity": self.equity,
            "day_start_equity": self.day_start_equity,
            "high_water_mark": self.high_water_mark,
            "strategy_reference_equity": self.strategy_reference_equity,
            "strategy_loss_amount": self.strategy_loss_amount,
            "open_risk_amount": self.open_risk_amount,
            "gross_exposure_amount": self.gross_exposure_amount,
            "instrument_exposure_amount": self.instrument_exposure_amount,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "trading_costs": self.trading_costs,
        }
        for name, value in numeric.items():
            _require_finite(name, value)
        if self.equity <= 0:
            raise ValueError("equity must be positive")
        for name in (
            "day_start_equity",
            "high_water_mark",
            "strategy_reference_equity",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "strategy_loss_amount",
            "open_risk_amount",
            "gross_exposure_amount",
            "instrument_exposure_amount",
            "trading_costs",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.available_margin is not None:
            _require_finite("available_margin", self.available_margin)
            if self.available_margin < 0:
                raise ValueError("available_margin must be non-negative")
        reconstructed = (
            self.day_start_equity
            + self.realized_pnl
            + self.unrealized_pnl
            - self.trading_costs
        )
        if abs(reconstructed - self.equity) > RISK_TOLERANCE * max(1.0, self.equity):
            raise ValueError(
                "equity must reconcile with day_start_equity + PnL - trading_costs"
            )

    @property
    def daily_loss_fraction(self) -> float:
        return max(0.0, (self.day_start_equity - self.equity) / self.day_start_equity)

    @property
    def total_drawdown_fraction(self) -> float:
        return max(0.0, (self.high_water_mark - self.equity) / self.high_water_mark)

    @property
    def strategy_loss_fraction(self) -> float:
        return max(
            0.0,
            self.strategy_loss_amount / self.strategy_reference_equity,
        )

    @classmethod
    def flat(cls, equity: float) -> RiskAccountSnapshot:
        """Create a reconciled flat snapshot for a new research account."""
        return cls(
            equity=equity,
            day_start_equity=equity,
            high_water_mark=equity,
            strategy_reference_equity=equity,
            strategy_loss_amount=0.0,
            open_risk_amount=0.0,
            gross_exposure_amount=0.0,
            instrument_exposure_amount=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            trading_costs=0.0,
        )


@dataclass(frozen=True)
class RiskOrderIntent:
    """Proposed position context used only by the pre-trade risk gate."""

    asset: str
    strategy_id: str
    requested_position_size: float
    position_notional: float
    risk_amount: float
    estimated_costs: float = 0.0
    data_age_seconds: float = 0.0
    max_data_age_seconds: float = 5.0
    session_open: bool = True
    symbol_permitted: bool = True
    strategy_permitted: bool = True
    duplicate_order: bool = False
    orders_last_minute: int = 0
    max_orders_per_minute: int = 10
    margin_required: float = 0.0
    execution_mode: ExecutionMode = ExecutionMode.RESEARCH
    strategy_state: StrategyState = StrategyState.RESEARCH
    price_deviation_bps: float = 0.0
    max_price_deviation_bps: float = 100.0
    order_id: str | None = None
    research_id: str | None = None
    probability_calibration_status: str | None = None

    def validate(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        numeric = {
            "requested_position_size": self.requested_position_size,
            "position_notional": self.position_notional,
            "risk_amount": self.risk_amount,
            "estimated_costs": self.estimated_costs,
            "data_age_seconds": self.data_age_seconds,
            "max_data_age_seconds": self.max_data_age_seconds,
            "margin_required": self.margin_required,
            "price_deviation_bps": self.price_deviation_bps,
            "max_price_deviation_bps": self.max_price_deviation_bps,
        }
        for name, value in numeric.items():
            _require_finite(name, value)
        if self.requested_position_size < 0:
            raise ValueError("requested_position_size must be non-negative")
        if self.position_notional < 0:
            raise ValueError("position_notional must be non-negative")
        if self.risk_amount < 0:
            raise ValueError("risk_amount must be non-negative")
        if self.estimated_costs < 0:
            raise ValueError("estimated_costs must be non-negative")
        if self.data_age_seconds < 0 or self.max_data_age_seconds < 0:
            raise ValueError("data age values must be non-negative")
        if self.orders_last_minute < 0 or self.max_orders_per_minute <= 0:
            raise ValueError("order-rate values are invalid")
        if self.margin_required < 0:
            raise ValueError("margin_required must be non-negative")
        if self.price_deviation_bps < 0 or self.max_price_deviation_bps < 0:
            raise ValueError("price deviation values must be non-negative")


@dataclass(frozen=True)
class RiskGateResult:
    """Immutable hard-gate decision."""

    schema_version: str
    status: str
    execution_allowed: bool
    hard_failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    policy_version: str = "RISK_POLICY_V2"
    research_id: str | None = None

    @property
    def blocked(self) -> bool:
        return not self.execution_allowed

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "execution_allowed": self.execution_allowed,
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "policy_version": self.policy_version,
            "research_id": self.research_id,
        }


@dataclass(frozen=True)
class RiskAuditEvent:
    """Content-addressed immutable audit record."""

    schema_version: str
    event_type: str
    timestamp: str
    event_id: str
    asset: str
    strategy_id: str
    status: str
    hard_failures: tuple[str, ...]
    warnings: tuple[str, ...]
    policy_version: str
    research_id: str | None = None

    @classmethod
    def from_gate(
        cls,
        gate: RiskGateResult,
        *,
        asset: str,
        strategy_id: str,
        timestamp: str,
    ) -> RiskAuditEvent:
        payload = {
            "schema_version": RISK_AUDIT_SCHEMA_VERSION,
            "event_type": "RISK_GATE",
            "timestamp": timestamp,
            "asset": asset,
            "strategy_id": strategy_id,
            "status": gate.status,
            "hard_failures": gate.hard_failures,
            "warnings": gate.warnings,
            "policy_version": gate.policy_version,
            "research_id": gate.research_id,
        }
        event_id = hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            schema_version=RISK_AUDIT_SCHEMA_VERSION,
            event_type="RISK_GATE",
            timestamp=timestamp,
            event_id=event_id,
            asset=asset,
            strategy_id=strategy_id,
            status=gate.status,
            hard_failures=gate.hard_failures,
            warnings=gate.warnings,
            policy_version=gate.policy_version,
            research_id=gate.research_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
            "asset": self.asset,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "hard_failures": list(self.hard_failures),
            "warnings": list(self.warnings),
            "policy_version": self.policy_version,
            "research_id": self.research_id,
        }
