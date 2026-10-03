"""Account and pre-trade risk governance for the ResearchOS decision boundary.

Adds the account-level and portfolio-level controls missing above the existing
per-trade sizing calculation. Deterministic, immutable, research-only, and
fail-closed. Never creates or submits orders.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any

from researchos.risk.contracts import RiskCalculation

RISK_GOVERNANCE_SCHEMA_VERSION = "risk-governance.v1"
_RISK_TOLERANCE = 1e-12
_NEAR_LIMIT_UTILIZATION = 0.80


class StrategyRiskState(str, Enum):
    """Governed lifecycle for a strategy's risk/deployment state."""

    RESEARCH = "RESEARCH"
    VALIDATED = "VALIDATED"
    RISK_REVIEW = "RISK_REVIEW"
    PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
    DEPLOYMENT_ELIGIBLE = "DEPLOYMENT_ELIGIBLE"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class RiskViolationCode(str, Enum):
    """Stable machine-readable hard risk violations."""

    RESEARCH_INVALID = "RESEARCH_INVALID"
    STRATEGY_STATE_BLOCKED = "STRATEGY_STATE_BLOCKED"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    MAX_STRATEGY_LOSS = "MAX_STRATEGY_LOSS"
    MAX_TRADE_RISK = "MAX_TRADE_RISK"
    MAX_PORTFOLIO_OPEN_RISK = "MAX_PORTFOLIO_OPEN_RISK"
    MAX_GROSS_EXPOSURE = "MAX_GROSS_EXPOSURE"
    MAX_SINGLE_INSTRUMENT_EXPOSURE = "MAX_SINGLE_INSTRUMENT_EXPOSURE"
    PROPOSED_NOTIONAL_REQUIRED = "PROPOSED_NOTIONAL_REQUIRED"
    RISK_EQUITY_MISMATCH = "RISK_EQUITY_MISMATCH"


class StrategyStateTransitionError(ValueError):
    """Raised when a strategy attempts to skip a governed state."""


_ALLOWED_RISK_STATES = {
    StrategyRiskState.RISK_REVIEW,
    StrategyRiskState.PAPER_ELIGIBLE,
    StrategyRiskState.DEPLOYMENT_ELIGIBLE,
    StrategyRiskState.ACTIVE,
}

_STATE_TRANSITIONS = {
    StrategyRiskState.RESEARCH: {StrategyRiskState.VALIDATED},
    StrategyRiskState.VALIDATED: {StrategyRiskState.RISK_REVIEW},
    StrategyRiskState.RISK_REVIEW: {
        StrategyRiskState.PAPER_ELIGIBLE,
        StrategyRiskState.SUSPENDED,
    },
    StrategyRiskState.PAPER_ELIGIBLE: {
        StrategyRiskState.DEPLOYMENT_ELIGIBLE,
        StrategyRiskState.SUSPENDED,
    },
    StrategyRiskState.DEPLOYMENT_ELIGIBLE: {
        StrategyRiskState.ACTIVE,
        StrategyRiskState.SUSPENDED,
    },
    StrategyRiskState.ACTIVE: {
        StrategyRiskState.SUSPENDED,
        StrategyRiskState.RETIRED,
    },
    StrategyRiskState.SUSPENDED: {
        StrategyRiskState.RISK_REVIEW,
        StrategyRiskState.RETIRED,
    },
    StrategyRiskState.RETIRED: set(),
}


def _coerce_strategy_state(value: StrategyRiskState | str) -> StrategyRiskState:
    if isinstance(value, StrategyRiskState):
        return value
    try:
        return StrategyRiskState(str(value).strip().upper())
    except ValueError as exc:
        raise ValueError(f"unsupported strategy risk state: {value!r}") from exc


def validate_strategy_transition(
    current: StrategyRiskState | str,
    target: StrategyRiskState | str,
) -> None:
    """Validate one adjacent strategy-state transition."""
    current_state = _coerce_strategy_state(current)
    target_state = _coerce_strategy_state(target)
    if current_state == target_state:
        return
    if target_state not in _STATE_TRANSITIONS[current_state]:
        raise StrategyStateTransitionError(
            f"invalid strategy state transition: "
            f"{current_state.value} -> {target_state.value}"
        )


@dataclass(frozen=True)
class RiskLimits:
    """Immutable account and portfolio hard-risk profile."""

    max_daily_loss_fraction: float = 0.02
    max_drawdown_fraction: float = 0.06
    max_strategy_loss_fraction: float = 0.03
    max_trade_loss_fraction: float = 0.005
    target_trade_risk_fraction: float = 0.0025
    max_portfolio_open_risk_fraction: float = 0.01
    max_gross_exposure_fraction: float = 3.0
    max_single_instrument_exposure_fraction: float = 1.5

    def validate(self) -> None:
        bounded = {
            "max_daily_loss_fraction": self.max_daily_loss_fraction,
            "max_drawdown_fraction": self.max_drawdown_fraction,
            "max_strategy_loss_fraction": self.max_strategy_loss_fraction,
            "max_trade_loss_fraction": self.max_trade_loss_fraction,
            "target_trade_risk_fraction": self.target_trade_risk_fraction,
            "max_portfolio_open_risk_fraction": self.max_portfolio_open_risk_fraction,
        }
        for name, value in bounded.items():
            if not math.isfinite(value) or not 0.0 < value <= 1.0:
                raise ValueError(f"{name} must be finite and in (0, 1]")
        if self.target_trade_risk_fraction > self.max_trade_loss_fraction:
            raise ValueError(
                "target_trade_risk_fraction must not exceed max_trade_loss_fraction"
            )
        if (
            not math.isfinite(self.max_gross_exposure_fraction)
            or self.max_gross_exposure_fraction <= 0.0
        ):
            raise ValueError("max_gross_exposure_fraction must be finite and positive")
        if (
            not math.isfinite(self.max_single_instrument_exposure_fraction)
            or self.max_single_instrument_exposure_fraction <= 0.0
        ):
            raise ValueError(
                "max_single_instrument_exposure_fraction must be finite and positive"
            )

    def to_dict(self) -> dict[str, float]:
        self.validate()
        return {
            "max_daily_loss_fraction": self.max_daily_loss_fraction,
            "max_drawdown_fraction": self.max_drawdown_fraction,
            "max_strategy_loss_fraction": self.max_strategy_loss_fraction,
            "max_trade_loss_fraction": self.max_trade_loss_fraction,
            "target_trade_risk_fraction": self.target_trade_risk_fraction,
            "max_portfolio_open_risk_fraction": self.max_portfolio_open_risk_fraction,
            "max_gross_exposure_fraction": self.max_gross_exposure_fraction,
            "max_single_instrument_exposure_fraction": (
                self.max_single_instrument_exposure_fraction
            ),
        }


@dataclass(frozen=True)
class RiskAccountState:
    """Immutable account snapshot consumed by the governance gate."""

    day_start_equity: float
    current_equity: float
    high_water_mark: float
    strategy_reference_equity: float
    strategy_pnl: float = 0.0
    open_risk_amount: float = 0.0
    gross_exposure: float = 0.0
    single_instrument_exposure: float = 0.0
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None

    def validate(self) -> None:
        for name in (
            "day_start_equity",
            "current_equity",
            "high_water_mark",
            "strategy_reference_equity",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name in (
            "open_risk_amount",
            "gross_exposure",
            "single_instrument_exposure",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and non-negative")
        if self.kill_switch_active and not (
            self.kill_switch_reason and self.kill_switch_reason.strip()
        ):
            raise ValueError(
                "kill_switch_reason is required when kill_switch_active is True"
            )

    @property
    def daily_loss_fraction(self) -> float:
        self.validate()
        return max(
            0.0,
            (self.day_start_equity - self.current_equity) / self.day_start_equity,
        )

    @property
    def drawdown_fraction(self) -> float:
        self.validate()
        return max(
            0.0,
            (self.high_water_mark - self.current_equity) / self.high_water_mark,
        )

    @property
    def strategy_loss_fraction(self) -> float:
        self.validate()
        return max(
            0.0,
            -self.strategy_pnl / self.strategy_reference_equity,
        )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "day_start_equity": self.day_start_equity,
            "current_equity": self.current_equity,
            "high_water_mark": self.high_water_mark,
            "strategy_reference_equity": self.strategy_reference_equity,
            "strategy_pnl": self.strategy_pnl,
            "open_risk_amount": self.open_risk_amount,
            "gross_exposure": self.gross_exposure,
            "single_instrument_exposure": self.single_instrument_exposure,
            "kill_switch_active": self.kill_switch_active,
            "kill_switch_reason": self.kill_switch_reason,
        }


@dataclass(frozen=True)
class RiskViolation:
    """Immutable, machine-readable hard violation."""

    code: RiskViolationCode
    observed: float | None = None
    limit: float | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "observed": self.observed,
            "limit": self.limit,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RiskDecision:
    """Immutable pre-trade risk decision and audit envelope."""

    schema_version: str
    status: str
    strategy_state: str
    research_valid: bool
    daily_loss_fraction: float
    drawdown_fraction: float
    strategy_loss_fraction: float
    proposed_trade_risk_fraction: float
    projected_open_risk_fraction: float | None
    projected_gross_exposure_fraction: float | None
    projected_single_instrument_exposure_fraction: float | None
    violations: tuple[RiskViolation, ...] = ()
    warnings: tuple[str, ...] = ()
    audit_hash: str = ""

    @property
    def allowed(self) -> bool:
        return self.status == "PASS" and not self.violations

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "strategy_state": self.strategy_state,
            "research_valid": self.research_valid,
            "daily_loss_fraction": self.daily_loss_fraction,
            "drawdown_fraction": self.drawdown_fraction,
            "strategy_loss_fraction": self.strategy_loss_fraction,
            "proposed_trade_risk_fraction": self.proposed_trade_risk_fraction,
            "projected_open_risk_fraction": self.projected_open_risk_fraction,
            "projected_gross_exposure_fraction": self.projected_gross_exposure_fraction,
            "projected_single_instrument_exposure_fraction": (
                self.projected_single_instrument_exposure_fraction
            ),
            "violations": [item.to_dict() for item in self.violations],
            "warnings": list(self.warnings),
        }

    def with_audit_hash(self) -> RiskDecision:
        payload = json.dumps(
            self._hash_payload(),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = sha256(payload.encode("utf-8")).hexdigest()
        return RiskDecision(
            schema_version=self.schema_version,
            status=self.status,
            strategy_state=self.strategy_state,
            research_valid=self.research_valid,
            daily_loss_fraction=self.daily_loss_fraction,
            drawdown_fraction=self.drawdown_fraction,
            strategy_loss_fraction=self.strategy_loss_fraction,
            proposed_trade_risk_fraction=self.proposed_trade_risk_fraction,
            projected_open_risk_fraction=self.projected_open_risk_fraction,
            projected_gross_exposure_fraction=self.projected_gross_exposure_fraction,
            projected_single_instrument_exposure_fraction=(
                self.projected_single_instrument_exposure_fraction
            ),
            violations=self.violations,
            warnings=self.warnings,
            audit_hash=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._hash_payload(),
            "audit_hash": self.audit_hash,
        }


def _near_limit_warning(name: str, observed: float, limit: float) -> str | None:
    if limit <= 0.0 or not (observed < limit):
        return None
    if observed >= _NEAR_LIMIT_UTILIZATION * limit:
        return f"{name}: utilization >= {_NEAR_LIMIT_UTILIZATION:.0%}"
    return None


def evaluate_pretrade_risk(
    risk: RiskCalculation,
    *,
    account: RiskAccountState,
    limits: RiskLimits = RiskLimits(),
    proposed_notional: float | None,
    strategy_state: StrategyRiskState | str,
    research_valid: bool,
) -> RiskDecision:
    """Evaluate hard account and portfolio controls around one proposed trade."""
    account.validate()
    limits.validate()
    for name in ("risk_amount", "final_risk_fraction"):
        value = getattr(risk, name)
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    state = _coerce_strategy_state(strategy_state)
    violations: list[RiskViolation] = []
    warnings: list[str] = []

    daily_loss = account.daily_loss_fraction
    drawdown = account.drawdown_fraction
    strategy_loss = account.strategy_loss_fraction
    proposed_risk_fraction = risk.risk_amount / account.current_equity

    if not research_valid:
        violations.append(RiskViolation(RiskViolationCode.RESEARCH_INVALID))

    if state not in _ALLOWED_RISK_STATES:
        violations.append(
            RiskViolation(
                RiskViolationCode.STRATEGY_STATE_BLOCKED,
                detail=f"state={state.value}",
            )
        )

    if account.kill_switch_active:
        violations.append(
            RiskViolation(
                RiskViolationCode.KILL_SWITCH_ACTIVE,
                detail=account.kill_switch_reason,
            )
        )

    if proposed_notional is None or proposed_notional <= 0.0:
        violations.append(
            RiskViolation(RiskViolationCode.PROPOSED_NOTIONAL_REQUIRED)
        )
        projected_open_risk = None
        projected_gross = None
        projected_single = None
    else:
        projected_open_risk = (
            account.open_risk_amount + risk.risk_amount
        ) / account.current_equity
        projected_gross = (
            account.gross_exposure + proposed_notional
        ) / account.current_equity
        projected_single = (
            account.single_instrument_exposure + proposed_notional
        ) / account.current_equity

    expected_risk_amount = account.current_equity * risk.final_risk_fraction
    if abs(risk.risk_amount - expected_risk_amount) > (
        _RISK_TOLERANCE * max(account.current_equity, 1.0)
    ):
        violations.append(
            RiskViolation(
                RiskViolationCode.RISK_EQUITY_MISMATCH,
                observed=risk.risk_amount,
                limit=expected_risk_amount,
            )
        )

    hard_checks = (
        (
            RiskViolationCode.DAILY_LOSS_LIMIT,
            daily_loss,
            limits.max_daily_loss_fraction,
        ),
        (
            RiskViolationCode.MAX_DRAWDOWN,
            drawdown,
            limits.max_drawdown_fraction,
        ),
        (
            RiskViolationCode.MAX_STRATEGY_LOSS,
            strategy_loss,
            limits.max_strategy_loss_fraction,
        ),
        (
            RiskViolationCode.MAX_TRADE_RISK,
            proposed_risk_fraction,
            limits.max_trade_loss_fraction,
        ),
        (
            RiskViolationCode.MAX_PORTFOLIO_OPEN_RISK,
            projected_open_risk,
            limits.max_portfolio_open_risk_fraction,
        ),
        (
            RiskViolationCode.MAX_GROSS_EXPOSURE,
            projected_gross,
            limits.max_gross_exposure_fraction,
        ),
        (
            RiskViolationCode.MAX_SINGLE_INSTRUMENT_EXPOSURE,
            projected_single,
            limits.max_single_instrument_exposure_fraction,
        ),
    )
    for code, observed, limit in hard_checks:
        if observed is not None and observed + _RISK_TOLERANCE >= limit:
            violations.append(
                RiskViolation(code, observed=observed, limit=limit)
            )
        warning = (
            _near_limit_warning(code.value, observed, limit)
            if observed is not None
            else None
        )
        if warning is not None:
            warnings.append(warning)

    status = "BLOCKED" if violations else "PASS"
    return RiskDecision(
        schema_version=RISK_GOVERNANCE_SCHEMA_VERSION,
        status=status,
        strategy_state=state.value,
        research_valid=research_valid,
        daily_loss_fraction=daily_loss,
        drawdown_fraction=drawdown,
        strategy_loss_fraction=strategy_loss,
        proposed_trade_risk_fraction=proposed_risk_fraction,
        projected_open_risk_fraction=projected_open_risk,
        projected_gross_exposure_fraction=projected_gross,
        projected_single_instrument_exposure_fraction=projected_single,
        violations=tuple(violations),
        warnings=tuple(warnings),
    ).with_audit_hash()


__all__ = [
    "RISK_GOVERNANCE_SCHEMA_VERSION",
    "RiskDecision",
    "RiskLimits",
    "RiskAccountState",
    "RiskViolation",
    "RiskViolationCode",
    "StrategyRiskState",
    "StrategyStateTransitionError",
    "evaluate_pretrade_risk",
    "validate_strategy_transition",
]
