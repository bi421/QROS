import pytest

from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.risk.decision_artifact import RiskDecisionArtifact


def test_risk_artifact_requires_full_provenance():
    assessment = ProbabilityAssessment.from_dict(
        {
            "decision_context_id": "ctx-1",
            "assessment_hash": "",
            "bullish_probability": 0.7,
            "bearish_probability": 0.2,
            "neutral_probability": 0.1,
            "confidence": 0.8,
            "uncertainty": 0.2,
            "evidence_strength": 0.8,
            "historical_consistency": 0.7,
            "sample_size": 20,
            "probability_method": "weighted-evidence",
            "calculation_version": "PROBABILITY_V1",
        }
    )
    assert assessment.assessment_hash == ""


def test_artifact_hash_is_tamper_evident():
    with pytest.raises(ValueError, match="assessment_hash"):
        RiskDecisionArtifact.build(
            type("Risk", (), {"assessment_hash": "", "to_dict": lambda self: {}})(),
            type("Decision", (), {"audit_hash": "gov"})(),
            "report",
        )
