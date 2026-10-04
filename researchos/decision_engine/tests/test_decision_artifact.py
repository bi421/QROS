import pytest
from researchos.decision_engine.artifact import DecisionArtifact
from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.pipeline import DecisionPipeline
from researchos.quant_math import QuantMathEngine

def test_decision_artifact_hash_links_entire_decision_chain():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    quant=QuantMathEngine().evaluate([100,101,102,103],successes=8,failures=2,monte_carlo_simulations=25)
    result=DecisionPipeline(quant_math_result=quant).run(context)
    artifact=DecisionArtifact.build(result.evidence,result.score,result.probability,result.report)
    assert artifact.context_id==context.id
    assert artifact.evidence_collection_hash==result.evidence.collection_hash
    assert artifact.score_hash==result.score.score_hash
    assert artifact.assessment_hash==result.probability.assessment_hash
    assert artifact.report_hash==result.report.report_hash
    assert artifact.verify()

def test_decision_artifact_rejects_tampering():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    quant=QuantMathEngine().evaluate([100,101,102])
    result=DecisionPipeline(quant_math_result=quant).run(context)
    artifact=DecisionArtifact.build(result.evidence,result.score,result.probability,result.report)
    payload=artifact.to_dict()
    payload["report_hash"]="tampered"
    with pytest.raises(ValueError,match="hash does not match"):
        DecisionArtifact.from_dict(payload)
