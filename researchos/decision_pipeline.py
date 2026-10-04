"""Canonical ResearchOS Block 2 -> Block 3 -> Block 4 pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.action.report import PreTradeReport, build_pre_trade_report
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import RiskCalculation, RiskPolicy, TradeStatistics
from researchos.risk.engine import calculate_risk
from researchos.risk.governance import (
    RiskAccountState,
    RiskDecision,
    RiskLimits,
    StrategyRiskState,
    evaluate_pretrade_risk,
)


@dataclass(frozen=True)
class DecisionPipelineInput:
    """Explicit API-first input for the canonical decision pipeline."""

    assessment: ProbabilityAssessment | dict[str, Any]
    asset: str
    direction: str
    account_equity: float
    trade_statistics: TradeStatistics
    research_valid: bool
    research_limitations: tuple[str, ...] = ()
    risk_policy: RiskPolicy = RiskPolicy()
    risk_per_unit: float | None = None
    probability_calibration_status: str | None = None
    risk_account: RiskAccountState | None = None
    risk_limits: RiskLimits = RiskLimits()
    proposed_notional: float | None = None
    strategy_state: StrategyRiskState = StrategyRiskState.RISK_REVIEW


def _calibration_status(request: DecisionPipelineInput) -> str | None:
    """Resolve explicit calibration evidence without inventing a status."""
    if request.probability_calibration_status is not None:
        return request.probability_calibration_status
    if isinstance(request.assessment, ProbabilityAssessment):
        return request.assessment.probability_calibration_status
    return request.assessment.get("probability_calibration_status")


def _risk_decision(
    request: DecisionPipelineInput,
    risk: RiskCalculation,
) -> RiskDecision | None:
    if request.risk_account is None:
        return None
    return evaluate_pretrade_risk(
        risk,
        account=request.risk_account,
        limits=request.risk_limits,
        proposed_notional=request.proposed_notional,
        strategy_state=request.strategy_state,
        research_valid=request.research_valid,
    )


def run_decision_pipeline(request: DecisionPipelineInput) -> PreTradeReport:
    """Run validated probability -> sizing -> governance -> human-review report.

    The probability-to-risk adapter is the fail-closed integrity boundary:
    serialized assessments are reconstructed, validated, and hash-checked
    before any risk sizing occurs.
    """
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
    decision = _risk_decision(request, risk)
    return build_pre_trade_report(
        risk,
        research_valid=request.research_valid,
        research_limitations=request.research_limitations,
        risk_decision=decision,
    )
