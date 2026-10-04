from __future__ import annotations

import pytest

from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.contracts import DecisionEvidenceItem, EvidenceSource, ProbabilityOutcome
from researchos.decision_engine.evidence import EvidenceAggregator
from researchos.decision_engine.pipeline import DecisionPipeline

from researchos.tests.test_decision_engine_pipeline import make_context


def test_directional_provider_reaches_probability_and_preserves_provenance() -> None:
    class BullishProvider:
        def collect(self, context: DecisionContext) -> list[DecisionEvidenceItem]:
            return [DecisionEvidenceItem(
                source=EvidenceSource.MARKET_MEMORY,
                source_id="live-memory-001",
                direction=ProbabilityOutcome.BULLISH,
                strength=0.9,
                weight=1.0,
                confidence=0.9,
                description="Provider-supplied directional evidence",
                supporting_ids=["live-memory-001"],
                provenance={"provider": "test"},
            )]

    result = DecisionPipeline(
        aggregator=EvidenceAggregator(
            providers={EvidenceSource.MARKET_MEMORY: BullishProvider()}
        )
    ).run(make_context())

    assert result.probability.bullish_probability > result.probability.bearish_probability
    item = next(item for item in result.evidence.items if item.source_id == "live-memory-001")
    assert item.direction is ProbabilityOutcome.BULLISH
    assert item.provenance == {"provider": "test"}


def test_provider_cannot_emit_evidence_for_another_source() -> None:
    class WrongSourceProvider:
        def collect(self, context: DecisionContext) -> list[DecisionEvidenceItem]:
            return [DecisionEvidenceItem(
                source=EvidenceSource.EXPERIMENT,
                source_id="wrong-source",
                direction=ProbabilityOutcome.BEARISH,
                strength=0.5,
                weight=1.0,
                confidence=0.5,
                description="Invalid provider output",
            )]

    with pytest.raises(ValueError, match="emitted Experiment"):
        DecisionPipeline(
            aggregator=EvidenceAggregator(
                providers={EvidenceSource.MARKET_MEMORY: WrongSourceProvider()}
            )
        ).run(make_context())
