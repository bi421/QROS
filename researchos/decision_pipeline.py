"""Canonical ResearchOS probability -> risk -> human-review pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.action.report import PreTradeReport, build_pre_trade_report
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import (
    ExecutionMode,
    RiskAccountSnapshot,
    RiskGateResult,
    RiskOrderIntent,
    RiskPolicy,
    StrategyState,
    TradeStatistics,
)
from researchos.risk.engine import calculate_risk, evaluate_risk_gate


@dataclass(frozen=True)
class DecisionPipelineInput:
    """Explicit API-first input for the governed decision pipeline."""

    assessment: ProbabilityAssessment | dict[str, Any]
    asset: str
    direction: str
    account_equity: float
    trade_statistics: TradeStatistics
    research_valid: bool
    risk_account: RiskAccountSnapshot | None = None
    strategy_id: str = ""
    position_notional: float = 0.0
    execution_mode: ExecutionMode = ExecutionMode.RESEARCH
    strategy_state: StrategyState = StrategyState.RESEARCH
    data_age_seconds: float = 0.0
    max_data_age_seconds: float = 5.0
    session_open: bool = True
    symbol_permitted: bool = True
    strategy_permitted: bool = True
    duplicate_order: bool = False
    orders_last_minute: int = 0
    max_orders_per_minute: int = 10
    margin_required: float = 0.0
    price_deviation_bps: float = 0.0
    max_price_deviation_bps: float = 100.0
    research_limitations: tuple[str, ...] = ()
    risk_policy: RiskPolicy = RiskPolicy()
    risk_per_unit: float | None = None
    probability_calibration_status: str | None = None


def _calibration_status(request: DecisionPipelineInput) -> str | None:
    """Resolve explicit calibration evidence without inventing a status."""
    if request.probability_calibration_status is not None:
        return request.probability_calibration_status
    if isinstance(request.assessment, ProbabilityAssessment):
        return request.assessment.probability_calibration_status
    return request.assessment.get("probability_calibration_status")


def _blocked_risk_context(request: DecisionPipelineInput) -> RiskGateResult:
    return RiskGateResult(
        schema_version="risk.v2",
        status="BLOCKED",
        execution_allowed=False,
        hard_failures=("RISK_ACCOUNT_CONTEXT_MISSING",),
        policy_version=request.risk_policy.version,
    )


def run_decision_pipeline(request: DecisionPipelineInput) -> PreTradeReport:
    """Run probability -> sizing -> hard risk gate -> human-review report."""
    risk_input = risk_input_from_probability(
        request.assessment,
        asset=request.asset,
        direction=request.direction,
        account_equity=request.account_equity,
        trade_statistics=request.trade_statistics,
        risk_policy=request.risk_policy,
        risk_per_unit=request.risk_per_unit,
        probability_calibration_status=_calibration_status(request),
    )
    risk = calculate_risk(risk_input)

    if request.risk_account is None:
        gate = _blocked_risk_context(request)
    else:
        requested_position_size = risk.position_size or 0.0
        gate = evaluate_risk_gate(
            request.risk_account,
            RiskOrderIntent(
                asset=request.asset,
                strategy_id=request.strategy_id,
                requested_position_size=requested_position_size,
                position_notional=request.position_notional,
                risk_amount=risk.risk_amount,
                data_age_seconds=request.data_age_seconds,
                max_data_age_seconds=request.max_data_age_seconds,
                session_open=request.session_open,
                symbol_permitted=request.symbol_permitted,
                strategy_permitted=request.strategy_permitted,
                duplicate_order=request.duplicate_order,
                orders_last_minute=request.orders_last_minute,
                max_orders_per_minute=request.max_orders_per_minute,
                margin_required=request.margin_required,
                execution_mode=request.execution_mode,
                strategy_state=request.strategy_state,
                price_deviation_bps=request.price_deviation_bps,
                max_price_deviation_bps=request.max_price_deviation_bps,
                research_id=risk.research_id,
                probability_calibration_status=risk_input.probability_calibration_status,
            ),
            policy=request.risk_policy,
        )

    return build_pre_trade_report(
        risk,
        research_valid=request.research_valid,
        research_limitations=request.research_limitations,
        risk_gate=gate,
    )
