"""Canonical probability -> sizing -> governance -> human-review pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.action.report import PreTradeReport, build_pre_trade_report
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.risk.adapters import risk_input_from_probability
from researchos.risk.contracts import RiskCalculation, RiskPolicy, TradeStatistics
from researchos.risk.decision_artifact import RiskDecisionArtifact
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


@dataclass(frozen=True)
class DecisionRiskPipelineResult:
    risk: RiskCalculation
    risk_decision: RiskDecision
    report: PreTradeReport
    artifact: RiskDecisionArtifact


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


def _calculate(
    request: DecisionPipelineInput,
) -> tuple[RiskCalculation, RiskDecision | None, PreTradeReport]:
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
    report = build_pre_trade_report(
        risk,
        research_valid=request.research_valid,
        research_limitations=request.research_limitations,
        risk_decision=decision,
    )
    return risk, decision, report


def run_decision_pipeline(request: DecisionPipelineInput) -> PreTradeReport:
    """Run validated probability -> sizing -> governance -> human-review report."""
    return _calculate(request)[2]


def run_decision_pipeline_with_artifact(
    request: DecisionPipelineInput,
) -> DecisionRiskPipelineResult:
    """Return the complete hash-linked sizing/governance/review chain.

    A governance decision is mandatory for artifact creation. This prevents an
    unevaluated report from being mistaken for a governed risk decision.
    """
    risk, decision, report = _calculate(request)
    if decision is None:
        raise ValueError("risk account is required for governed risk artifact creation")
    artifact = RiskDecisionArtifact.build(risk, decision, report)
    return DecisionRiskPipelineResult(
        risk=risk,
        risk_decision=decision,
        report=report,
        artifact=artifact,
    )


__all__ = [
    "DecisionPipelineInput",
    "DecisionRiskPipelineResult",
    "run_decision_pipeline",
    "run_decision_pipeline_with_artifact",
]
