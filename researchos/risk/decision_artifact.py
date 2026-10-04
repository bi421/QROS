"""Hash-linked envelope joining probability, sizing, governance and review."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from researchos.core.identity import deterministic_hash
from researchos.risk.contracts import RiskCalculation
from researchos.risk.governance import RiskDecision
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from researchos.action.report import PreTradeReport

RISK_DECISION_ARTIFACT_VERSION="RISK_DECISION_ARTIFACT_V1"

@dataclass(frozen=True)
class RiskDecisionArtifact:
    assessment_hash:str
    risk_calculation_hash:str
    risk_governance_hash:str
    report_hash:str
    artifact_version:str
    artifact_hash:str

    @classmethod
    def build(cls,risk:RiskCalculation,decision:RiskDecision,report:"PreTradeReport"|str)->"RiskDecisionArtifact":
        report_hash=report.report_hash if hasattr(report,"report_hash") else str(report)
        if not report_hash.strip(): raise ValueError("report_hash is required")
        if not risk.assessment_hash: raise ValueError("risk calculation assessment_hash is required")
        if not decision.audit_hash: raise ValueError("risk decision audit_hash is required")
        payload={"artifact_version":RISK_DECISION_ARTIFACT_VERSION,"assessment_hash":risk.assessment_hash,
                 "risk_calculation_hash":deterministic_hash(risk.to_dict()),"risk_governance_hash":decision.audit_hash,
                 "report_hash":report_hash}
        return cls(**payload,artifact_hash=deterministic_hash(payload))

    def to_dict(self)->dict[str,Any]:
        return {"assessment_hash":self.assessment_hash,"risk_calculation_hash":self.risk_calculation_hash,
                "risk_governance_hash":self.risk_governance_hash,"report_hash":self.report_hash,
                "artifact_version":self.artifact_version,"artifact_hash":self.artifact_hash}

    def verify(self)->bool:
        payload=self.to_dict(); supplied=payload.pop("artifact_hash")
        return deterministic_hash(payload)==supplied

    @classmethod
    def from_dict(cls,data:dict[str,Any])->"RiskDecisionArtifact":
        required=("assessment_hash","risk_calculation_hash","risk_governance_hash","report_hash","artifact_version","artifact_hash")
        missing=[key for key in required if not data.get(key)]
        if missing: raise ValueError(f"risk decision artifact missing fields: {', '.join(missing)}")
        obj=cls(*(str(data[key]) for key in required))
        if not obj.verify(): raise ValueError("risk decision artifact hash does not match content")
        return obj

def build_risk_decision_artifact(risk:RiskCalculation,decision:RiskDecision,report:PreTradeReport|str)->RiskDecisionArtifact:
    return RiskDecisionArtifact.build(risk,decision,report)

__all__=["RISK_DECISION_ARTIFACT_VERSION","RiskDecisionArtifact","build_risk_decision_artifact"]
