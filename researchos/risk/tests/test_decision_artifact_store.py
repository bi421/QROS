from researchos.risk.decision_artifact import RiskDecisionArtifact
from researchos.risk.decision_artifact_store import InMemoryRiskDecisionArtifactStore

def _artifact() -> RiskDecisionArtifact:
    payload = {
        "assessment_hash": "assessment-1",
        "risk_calculation_hash": "risk-1",
        "risk_governance_hash": "governance-1",
        "report_hash": "report-1",
        "artifact_version": "RISK_DECISION_ARTIFACT_V1",
    }
    from researchos.core.identity import deterministic_hash
    return RiskDecisionArtifact(**payload, artifact_hash=deterministic_hash(payload))

def test_store_is_idempotent_and_replayable() -> None:
    store = InMemoryRiskDecisionArtifactStore()
    artifact = _artifact()
    assert store.put(artifact) == artifact
    assert store.put(artifact) == artifact
    assert len(store) == 1
    assert store.get(artifact.artifact_hash) == artifact

def test_store_rejects_tampering() -> None:
    store = InMemoryRiskDecisionArtifactStore()
    artifact = _artifact()
    tampered = RiskDecisionArtifact(
        assessment_hash="tampered",
        risk_calculation_hash=artifact.risk_calculation_hash,
        risk_governance_hash=artifact.risk_governance_hash,
        report_hash=artifact.report_hash,
        artifact_version=artifact.artifact_version,
        artifact_hash=artifact.artifact_hash,
    )
    import pytest
    with pytest.raises(ValueError, match="invalid"):
        store.put(tampered)
