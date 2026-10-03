from __future__ import annotations

import pytest

from researchos.decision_engine.contracts import ProbabilityOutcome
from researchos.decision_pipeline import DecisionPipelineInput, run_decision_pipeline
from researchos.market_memory.decision_adapter import market_memory_to_decision_evidence, market_memory_to_probability
from researchos.market_memory.event_schema import EvidenceRecord, EvidenceStatus, MarketMemoryReport
from researchos.risk.contracts import RiskPolicy, TradeStatistics
from researchos.risk.governance import RiskAccountState, StrategyRiskState


def _record(name: str, direction: str, probability: float) -> EvidenceRecord:
    provenance = {
        "algorithm": "sha256",
        "evidence_computation_digest": f"digest-{name}",
        "dataset_version_bound": "canonical-v1",
        "dataset_identity": {
            "dataset_id": "xauusd-d1-validated",
            "dataset_content_hash": "content-hash-e2e",
            "dataset_hash": "canonical-v1",
        },
    }
    return EvidenceRecord(
        finding_id=f"E2E|{name}",
        finding_name=name,
        dataset_id="xauusd-d1-validated",
        dataset_version="canonical-v1",
        event_definition="SMA20/100 crossover",
        condition_definition=f"{{'direction':'{direction}'}}",
        sample_size=1000,
        time_range=("2021-01-03T18:00:00+00:00", "2025-12-31T16:57:00+00:00"),
        computation_method="forward_return_analysis",
        code_module="market_memory.pipeline_v1",
        statistical_method="wilson",
        result={"raw_probability": probability},
        uncertainty={"provenance": provenance},
        status=EvidenceStatus.VALIDATED.value,
    )


def _validated_report() -> MarketMemoryReport:
    return MarketMemoryReport(
        report_id="MMR|E2E|XAUUSD|D1",
        asset="XAUUSD",
        timeframe="D1",
        event_type="sma_crossover",
        evidence_records=[
            _record("bullish_crossover", "bullish", 0.80),
            _record("bearish_crossover", "bearish", 0.40),
        ],
    )


def test_market_memory_to_probability_to_risk_to_pretrade_is_end_to_end() -> None:
    """Regression: validated Market Memory must reach the canonical pipeline with provenance."""
    report = _validated_report()
    evidence = market_memory_to_decision_evidence(report)
    assessment = market_memory_to_probability(report, decision_context_id="research-e2e-xauusd")
    pretrade = run_decision_pipeline(
        DecisionPipelineInput(
            assessment=assessment,
            asset="XAUUSD",
            direction="bullish",
            account_equity=10_000,
            trade_statistics=TradeStatistics(average_win=150, average_loss=100, sample_size=1000),
            research_valid=True,
            research_limitations=(),
            risk_per_unit=20,
            risk_policy=RiskPolicy(max_risk_fraction=0.0025),
            risk_account=RiskAccountState(
                day_start_equity=10_000,
                current_equity=10_000,
                high_water_mark=10_000,
                strategy_reference_equity=10_000,
            ),
            proposed_notional=1_000,
            strategy_state=StrategyRiskState.RISK_REVIEW,
        )
    )

    assert len(evidence) == 2
    assert {item.direction for item in evidence} == {ProbabilityOutcome.BULLISH, ProbabilityOutcome.BEARISH}
    assert all(item.provenance["dataset_identity"]["dataset_hash"] == "canonical-v1" for item in evidence)
    assert all(item.provenance["algorithm"] == "sha256" for item in evidence)
    assert assessment.decision_context_id == "research-e2e-xauusd"
    assert assessment.sample_size == 2
    assert assessment.bullish_probability > assessment.bearish_probability
    assert assessment.bullish_probability + assessment.bearish_probability + assessment.neutral_probability == pytest.approx(1.0)
    assert assessment.assessment_hash
    assert pretrade.schema_version == "pretrade.v1"
    assert pretrade.status == "READY_FOR_HUMAN_REVIEW"
    assert pretrade.research_id == "research-e2e-xauusd"
    assert pretrade.direction == "bullish"
    assert pretrade.probability == assessment.bullish_probability
    assert pretrade.risk_valid is True
    assert pretrade.risk_amount > 0
    assert pretrade.position_size is not None
