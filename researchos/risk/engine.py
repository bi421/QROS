"""Deterministic sizing and pre-trade risk gates for ResearchOS."""

from __future__ import annotations

from researchos.risk.contracts import (
    ExecutionMode,
    RISK_SCHEMA_VERSION,
    RiskAccountSnapshot,
    RiskCalculation,
    RiskGateResult,
    RiskInput,
    RiskOrderIntent,
    RiskPolicy,
    StrategyState,
)

_ZERO_TOLERANCE = 1e-15
_REQUIRED_CALIBRATION_STATUS = "well-calibrated"


def _kelly_fraction(probability: float, win_loss_ratio: float) -> float:
    """Return non-negative full Kelly fraction for a binary payoff model."""
    if not 0 <= probability <= 1:
        raise ValueError("probability must be in [0, 1]")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    fraction = probability - (1.0 - probability) / win_loss_ratio
    return 0.0 if fraction <= _ZERO_TOLERANCE else fraction


def calculate_risk(request: RiskInput) -> RiskCalculation:
    """Calculate constrained research-only risk sizing.

    The result is a sizing artifact, not an execution authorization.
    Account and portfolio controls are evaluated separately.
    """
    request.validate()
    ratio = request.trade_statistics.win_loss_ratio
    full_kelly = _kelly_fraction(request.probability, ratio)
    fractional_kelly = full_kelly * request.risk_policy.fractional_kelly
    final_fraction = min(
        fractional_kelly,
        request.risk_policy.max_risk_fraction,
    )
    risk_amount = request.account_equity * final_fraction

    position_size = None
    if request.risk_per_unit is not None:
        position_size = risk_amount / request.risk_per_unit
        max_notional = request.account_equity * request.risk_policy.max_position_fraction
        position_size = min(position_size, max_notional / request.risk_per_unit)

    return RiskCalculation(
        schema_version=RISK_SCHEMA_VERSION,
        asset=request.asset,
        direction=request.direction,
        probability=request.probability,
        win_loss_ratio=ratio,
        full_kelly_fraction=full_kelly,
        fractional_kelly_fraction=fractional_kelly,
        final_risk_fraction=final_fraction,
        risk_amount=risk_amount,
        position_size=position_size,
        capped=final_fraction < fractional_kelly,
        status="CALCULATED",
        research_id=request.research_id,
    )

def evaluate_risk_gate(
    account: RiskAccountSnapshot,
    intent: RiskOrderIntent,
    *,
    policy: RiskPolicy,
) -> RiskGateResult:
    """Evaluate all deterministic hard pre-trade controls.

    Violations block the proposed intent. The function never silently shrinks,
    rewrites, or substitutes an order.
    """
    account.validate()
    intent.validate()
    policy.validate()

    failures: list[str] = []
    warnings: list[str] = []

    if account.kill_switch_active:
        failures.append("KILL_SWITCH_ACTIVE")
    if account.daily_loss_fraction >= policy.max_daily_loss_fraction:
        failures.append("MAX_DAILY_LOSS_BREACHED")
    if account.total_drawdown_fraction >= policy.max_total_drawdown_fraction:
        failures.append("MAX_TOTAL_DRAWDOWN_BREACHED")
    if account.strategy_loss_fraction >= policy.max_strategy_loss_fraction:
        failures.append("MAX_STRATEGY_LOSS_BREACHED")

    max_trade_loss = account.equity * policy.max_loss_per_trade_fraction
    if intent.risk_amount > max_trade_loss + _ZERO_TOLERANCE:
        failures.append("MAX_LOSS_PER_TRADE_BREACHED")

    projected_open_risk = account.open_risk_amount + intent.risk_amount
    max_open_risk = account.equity * policy.max_portfolio_open_risk_fraction
    if projected_open_risk > max_open_risk + _ZERO_TOLERANCE:
        failures.append("MAX_PORTFOLIO_OPEN_RISK_BREACHED")

    projected_gross = account.gross_exposure_amount + intent.position_notional
    max_gross = account.equity * policy.max_gross_exposure_multiple
    if projected_gross > max_gross + _ZERO_TOLERANCE:
        failures.append("MAX_GROSS_EXPOSURE_BREACHED")

    projected_instrument = (
        account.instrument_exposure_amount + intent.position_notional
    )
    max_instrument = (
        account.equity * policy.max_single_instrument_exposure_multiple
    )
    if projected_instrument > max_instrument + _ZERO_TOLERANCE:
        failures.append("MAX_SINGLE_INSTRUMENT_EXPOSURE_BREACHED")

    if intent.data_age_seconds > intent.max_data_age_seconds:
        failures.append("STALE_MARKET_DATA")
    if not intent.session_open:
        failures.append("MARKET_SESSION_CLOSED")
    if not intent.symbol_permitted:
        failures.append("SYMBOL_NOT_PERMITTED")
    if not intent.strategy_permitted:
        failures.append("STRATEGY_NOT_PERMITTED")
    if intent.duplicate_order:
        failures.append("DUPLICATE_ORDER")
    if intent.orders_last_minute >= intent.max_orders_per_minute:
        failures.append("ORDER_RATE_LIMIT_BREACHED")
    if intent.price_deviation_bps > intent.max_price_deviation_bps:
        failures.append("FAT_FINGER_PRICE_BAND_BREACHED")
    if (
        account.available_margin is not None
        and intent.margin_required > account.available_margin + _ZERO_TOLERANCE
    ):
        failures.append("INSUFFICIENT_AVAILABLE_MARGIN")
    if intent.risk_amount <= _ZERO_TOLERANCE:
        failures.append("NO_POSITIVE_RISK_BUDGET")

    if intent.execution_mode in {ExecutionMode.PAPER, ExecutionMode.LIVE}:
        if intent.requested_position_size > _ZERO_TOLERANCE and intent.position_notional <= _ZERO_TOLERANCE:
            failures.append("MISSING_POSITION_NOTIONAL")
        if (
            intent.probability_calibration_status is None
            or intent.probability_calibration_status.strip().lower()
            != _REQUIRED_CALIBRATION_STATUS
        ):
            failures.append("PROBABILITY_NOT_WELL_CALIBRATED")

    if intent.execution_mode is ExecutionMode.PAPER:
        if intent.strategy_state not in {
            StrategyState.PAPER_ELIGIBLE,
            StrategyState.DEPLOYMENT_ELIGIBLE,
            StrategyState.ACTIVE,
        }:
            failures.append("STRATEGY_NOT_PAPER_ELIGIBLE")
    elif intent.execution_mode is ExecutionMode.LIVE:
        if intent.strategy_state not in {
            StrategyState.DEPLOYMENT_ELIGIBLE,
            StrategyState.ACTIVE,
        }:
            failures.append("STRATEGY_NOT_DEPLOYMENT_ELIGIBLE")

    utilization_checks = (
        ("DAILY_LOSS_UTILIZATION_HIGH", account.daily_loss_fraction, policy.max_daily_loss_fraction),
        ("TOTAL_DRAWDOWN_UTILIZATION_HIGH", account.total_drawdown_fraction, policy.max_total_drawdown_fraction),
        ("STRATEGY_LOSS_UTILIZATION_HIGH", account.strategy_loss_fraction, policy.max_strategy_loss_fraction),
        ("OPEN_RISK_UTILIZATION_HIGH", projected_open_risk / account.equity, policy.max_portfolio_open_risk_fraction),
        ("GROSS_EXPOSURE_UTILIZATION_HIGH", projected_gross / account.equity, policy.max_gross_exposure_multiple),
        (
            "INSTRUMENT_EXPOSURE_UTILIZATION_HIGH",
            projected_instrument / account.equity,
            policy.max_single_instrument_exposure_multiple,
        ),
    )
    for warning, utilization, limit in utilization_checks:
        if (
            limit > 0
            and utilization + _ZERO_TOLERANCE >= policy.warning_utilization_fraction
        ):
            warnings.append(warning)

    status = "BLOCKED" if failures else (
        "RESEARCH_ONLY" if intent.execution_mode is ExecutionMode.RESEARCH else "PASS"
    )
    return RiskGateResult(
        schema_version=RISK_SCHEMA_VERSION,
        status=status,
        execution_allowed=not failures and intent.execution_mode is not ExecutionMode.RESEARCH,
        hard_failures=tuple(failures),
        warnings=tuple(warnings),
        policy_version=policy.version,
        research_id=intent.research_id,
    )
