"""Deterministic pre-trade report assembly; no execution logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.core.identity import deterministic_hash
from researchos.risk.contracts import RiskCalculation
from researchos.risk.governance import RiskDecision

ACTION_SCHEMA_VERSION = "pretrade.v1"


@dataclass(frozen=True)
class PreTradeReport:
    """Immutable human-review package assembled from research and risk outputs."""

    schema_version: str
    asset: str
    direction: str
    probability: float
    risk_amount: float
    risk_fraction: float
    position_size: float | None
    research_valid: bool
    risk_valid: bool
    status: str
    research_id: str | None = None
    limitations: tuple[str, ...] = ()
    risk_governance_valid: bool = False
    risk_governance_status: str = "NOT_EVALUATED"
    risk_violations: tuple[str, ...] = ()
    risk_decision_hash: str | None = None
    probability_method: str | None = None
    probability_calculation_version: str | None = None
    probability_calibration_status: str | None = None
    assessment_hash: str | None = None

    @property
    def report_hash(self) -> str:
        """Return the deterministic hash of the canonical report payload."""
        return deterministic_hash(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "asset": self.asset,
            "direction": self.direction,
            "probability": self.probability,
            "risk_amount": self.risk_amount,
            "risk_fraction": self.risk_fraction,
            "position_size": self.position_size,
            "research_valid": self.research_valid,
            "risk_valid": self.risk_valid,
            "status": self.status,
            "research_id": self.research_id,
            "limitations": list(self.limitations),
            "risk_governance_valid": self.risk_governance_valid,
            "risk_governance_status": self.risk_governance_status,
            "risk_violations": list(self.risk_violations),
            "risk_decision_hash": self.risk_decision_hash,
            "probability_method": self.probability_method,
            "probability_calculation_version": self.probability_calculation_version,
            "probability_calibration_status": self.probability_calibration_status,
            "assessment_hash": self.assessment_hash,
        }


def build_pre_trade_report(
    risk: RiskCalculation,
    *,
    research_valid: bool,
    research_limitations: tuple[str, ...] = (),
    risk_decision: RiskDecision | None = None,
) -> PreTradeReport:
    """Assemble a review report without making an execution decision."""
    risk_valid = risk.status == "CALCULATED"
    limitations = tuple(research_limitations)

    if not research_valid:
        status = "BLOCKED_RESEARCH_VALIDATION"
    elif not risk_valid:
        status = "BLOCKED_RISK_CALCULATION"
    elif risk.risk_amount <= 0:
        status = "NO_POSITIVE_RISK_BUDGET"
    elif risk_decision is None:
        status = "BLOCKED_RISK_GOVERNANCE"
    elif not risk_decision.allowed:
        status = "BLOCKED_RISK_GOVERNANCE"
    else:
        status = "READY_FOR_HUMAN_REVIEW"

    return PreTradeReport(
        schema_version=ACTION_SCHEMA_VERSION,
        asset=risk.asset,
        direction=risk.direction,
        probability=risk.probability,
        risk_amount=risk.risk_amount,
        risk_fraction=risk.final_risk_fraction,
        position_size=risk.position_size,
        research_valid=research_valid,
        risk_valid=risk_valid,
        status=status,
        research_id=risk.research_id,
        limitations=limitations,
        risk_governance_valid=(
            risk_decision.allowed if risk_decision is not None else False
        ),
        risk_governance_status=(
            risk_decision.status if risk_decision is not None else "NOT_EVALUATED"
        ),
        risk_violations=(
            tuple(item.code.value for item in risk_decision.violations)
            if risk_decision is not None
            else ()
        ),
        risk_decision_hash=(
            risk_decision.audit_hash if risk_decision is not None else None
        ),
        probability_method=risk.probability_method,
        probability_calculation_version=risk.probability_calculation_version,
        probability_calibration_status=risk.probability_calibration_status,
        assessment_hash=risk.assessment_hash,
    )
