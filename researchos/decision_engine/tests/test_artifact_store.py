import pytest
from researchos.decision_engine.artifact import DecisionArtifact
from researchos.decision_engine.artifact_store import InMemoryDecisionArtifactStore
from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.pipeline import DecisionPipeline
from researchos.quant_math import QuantMathEngine

def _artifact():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    quant=QuantMathEngine().evaluate([100,101,102,103])
    result=DecisionPipeline(quant_math_result=quant).run(context)
    return DecisionArtifact.build(result.evidence,result.score,result.probability,result.report)

def test_store_is_idempotent_by_artifact_hash():
    store=InMemoryDecisionArtifactStore()
    artifact=_artifact()
    assert store.put(artifact) is artifact
    assert store.put(artifact) is artifact
    assert len(store)==1
    assert store.get(artifact.artifact_hash)==artifact

def test_store_rejects_invalid_artifact():
    store=InMemoryDecisionArtifactStore()
    artifact=_artifact()
    invalid=DecisionArtifact(
        context_id=artifact.context_id,evidence_collection_id=artifact.evidence_collection_id,
        evidence_collection_hash=artifact.evidence_collection_hash,score_id=artifact.score_id,
        score_hash=artifact.score_hash,probability_id=artifact.probability_id,
        assessment_hash=artifact.assessment_hash,report_id=artifact.report_id,
        report_hash="tampered",artifact_version=artifact.artifact_version,artifact_hash=artifact.artifact_hash,
    )
    with pytest.raises(ValueError,match="invalid decision artifact"):
        store.put(invalid)
