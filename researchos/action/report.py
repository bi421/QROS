"""Deterministic pre-trade report assembly; no execution logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from researchos.risk.contracts import RiskAuditEvent, RiskCalculation, RiskGateResult

ACTION_SCHEMA_VERSION = "pretrade.v2"


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
    risk_gate_status: str | None = None
    execution_allowed: bool = False
    risk_hard_failures: tuple[str, ...] = ()
    risk_warnings: tuple[str, ...] = ()
    risk_audit_event: RiskAuditEvent | None = None

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
            "risk_gate_status": self.risk_gate_status,
            "execution_allowed": self.execution_allowed,
            "risk_hard_failures": list(self.risk_hard_failures),
            "risk_warnings": list(self.risk_warnings),
            "risk_audit_event": (
                self.risk_audit_event.to_dict()
                if self.risk_audit_event is not None
                else None
            ),
        }


def build_pre_trade_report(
    risk: RiskCalculation,
    *,
    research_valid: bool,
    research_limitations: tuple[str, ...] = (),
    risk_gate: RiskGateResult | None = None,
    risk_audit_event: RiskAuditEvent | None = None,
) -> PreTradeReport:
    """Assemble a review report without placing or authorizing an order."""
    risk_valid = risk.status == "CALCULATED"
    gate_status = risk_gate.status if risk_gate is not None else None
    if risk_gate is not None:
        risk_valid = risk_valid and gate_status != "BLOCKED"

    limitations = tuple(research_limitations)
    execution_allowed = (
        risk_gate.execution_allowed and research_valid and risk_valid
        if risk_gate is not None
        else False
    )
    hard_failures = risk_gate.hard_failures if risk_gate is not None else ()
    warnings = risk_gate.warnings if risk_gate is not None else ()

    if not research_valid:
        status = "BLOCKED_RESEARCH_VALIDATION"
    elif not risk_valid:
        status = (
            "BLOCKED_RISK_GATE"
            if risk_gate is not None and gate_status == "BLOCKED"
            else "BLOCKED_RISK_CALCULATION"
        )
    elif risk.risk_amount <= 0:
        status = "NO_POSITIVE_RISK_BUDGET"
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
        risk_gate_status=gate_status,
        execution_allowed=execution_allowed,
        risk_hard_failures=hard_failures,
        risk_warnings=warnings,
        risk_audit_event=risk_audit_event,
    )
