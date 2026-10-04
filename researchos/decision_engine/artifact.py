"""Canonical, hash-linked decision artifact for QROS audit persistence."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from researchos.core.identity import deterministic_hash
from researchos.decision_engine.evidence import EvidenceCollection
from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.decision_engine.report import DecisionReport
from researchos.decision_engine.score import EvidenceScore

DECISION_ARTIFACT_VERSION="DECISION_ARTIFACT_V1"

@dataclass(frozen=True)
class DecisionArtifact:
    context_id:str
    evidence_collection_id:str
    evidence_collection_hash:str
    score_id:str
    score_hash:str
    probability_id:str
    assessment_hash:str
    report_id:str
    report_hash:str
    artifact_version:str
    artifact_hash:str

    @classmethod
    def build(cls,evidence:EvidenceCollection,score:EvidenceScore,probability:ProbabilityAssessment,report:DecisionReport)->"DecisionArtifact":
        payload={
            "artifact_version":DECISION_ARTIFACT_VERSION,
            "context_id":evidence.decision_context_id,
            "evidence_collection_id":evidence.id,"evidence_collection_hash":evidence.collection_hash,
            "score_id":score.id,"score_hash":score.score_hash,
            "probability_id":probability.id,"assessment_hash":probability.assessment_hash,
            "report_id":report.id,"report_hash":report.report_hash,
        }
        return cls(**{k:payload[k] for k in (
            "context_id","evidence_collection_id","evidence_collection_hash","score_id","score_hash",
            "probability_id","assessment_hash","report_id","report_hash","artifact_version")},
                   artifact_hash=deterministic_hash(payload))

    def to_dict(self)->dict[str,Any]:
        return {
            "context_id":self.context_id,"evidence_collection_id":self.evidence_collection_id,
            "evidence_collection_hash":self.evidence_collection_hash,"score_id":self.score_id,
            "score_hash":self.score_hash,"probability_id":self.probability_id,
            "assessment_hash":self.assessment_hash,"report_id":self.report_id,
            "report_hash":self.report_hash,"artifact_version":self.artifact_version,
            "artifact_hash":self.artifact_hash,
        }

    def verify(self)->bool:
        payload=self.to_dict()
        supplied=payload.pop("artifact_hash")
        return deterministic_hash(payload)==supplied

    @classmethod
    def from_dict(cls,data:dict[str,Any])->"DecisionArtifact":
        required=("context_id","evidence_collection_id","evidence_collection_hash","score_id","score_hash",
                  "probability_id","assessment_hash","report_id","report_hash","artifact_version","artifact_hash")
        missing=[key for key in required if key not in data or not data[key]]
        if missing: raise ValueError(f"decision artifact missing fields: {', '.join(missing)}")
        obj=cls(*(str(data[key]) for key in required))
        if not obj.verify(): raise ValueError("decision artifact hash does not match content")
        return obj
