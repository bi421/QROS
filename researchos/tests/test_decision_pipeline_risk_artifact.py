from researchos.decision_engine.probability import ProbabilityAssessment
from researchos.decision_pipeline import (
    DecisionPipelineInput,
    run_decision_pipeline_with_artifact,
)
from researchos.risk.contracts import TradeStatistics
from researchos.risk.decision_artifact_store import InMemoryRiskDecisionArtifactStore
from researchos.risk.governance import (
    RiskAccountState,
    RiskLimits,
    StrategyRiskState,
)


def test_full_probability_to_risk_artifact_replay() -> None:
    assessment = ProbabilityAssessment(
        decision_context_id="ctx-e2e",
        evidence_collection_id="evidence-e2e",
        bullish_probability=0.70,
        bearish_probability=0.20,
        neutral_probability=0.10,
        confidence=0.80,
        uncertainty=0.20,
        evidence_strength=0.75,
        historical_consistency=0.70,
        sample_size=20,
    )
    request = DecisionPipelineInput(
        assessment=assessment,
        asset="XAUUSD",
        direction="LONG",
        account_equity=10_000.0,
        trade_statistics=TradeStatistics(
            average_win=200.0,
            average_loss=100.0,
            sample_size=20,
        ),
        research_valid=True,
        risk_account=RiskAccountState(
            day_start_equity=10_000.0,
            current_equity=10_000.0,
            high_water_mark=10_000.0,
            strategy_reference_equity=10_000.0,
        ),
        risk_limits=RiskLimits(),
        proposed_notional=1_000.0,
        strategy_state=StrategyRiskState.RISK_REVIEW,
    )
    result = run_decision_pipeline_with_artifact(request)
    assert result.risk.assessment_hash == assessment.assessment_hash
    assert result.risk_decision.allowed
    assert result.report.status == "READY_FOR_HUMAN_REVIEW"
    assert result.artifact.verify()

    store = InMemoryRiskDecisionArtifactStore()
    stored = store.put(result.artifact)
    replayed = store.put(result.artifact)
    assert stored == replayed == result.artifact
    assert store.get(result.artifact.artifact_hash) == result.artifact
    assert len(store) == 1
