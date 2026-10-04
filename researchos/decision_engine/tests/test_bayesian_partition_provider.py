import pytest

from researchos.decision_engine.bayesian_partition_provider import (
    bayesian_partition_to_evidence,
)
from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.evidence import EvidenceCollection, EvidenceValidator
from researchos.quant_math.bayesian_update import bayesian_update
from researchos.quant_math.partition import ProbabilityPartition


def _context() -> DecisionContext:
    return DecisionContext(asset="XAUUSD", symbol="XAUUSD", timeframe="M1")


def _result():
    partition = ProbabilityPartition.from_sequences(
        "direction", ["Bullish", "Bearish", "Neutral"], [0.3, 0.4, 0.3]
    )
    return bayesian_update(
        partition,
        event_id="event-1",
        likelihoods=[0.8, 0.2, 0.5],
        evidence_hash="evidence-1",
    )


def test_bayesian_partition_maps_exactly_into_canonical_evidence() -> None:
    result = _result()
    items = bayesian_partition_to_evidence(result, _context())

    assert [item.direction.value for item in items] == [
        "Bullish",
        "Bearish",
        "Neutral",
    ]
    assert [item.weight for item in items] == pytest.approx(
        result.posterior_probabilities
    )
    assert all(item.confidence == 1.0 for item in items)
    assert all(
        item.provenance["evidence_hash"] == result.evidence_hash for item in items
    )


def test_direction_adapter_rejects_arbitrary_state_space() -> None:
    partition = ProbabilityPartition.from_sequences(
        "market-state", ["A", "B", "C"], [1 / 3, 1 / 3, 1 / 3]
    )
    result = bayesian_update(partition, event_id="event-2", likelihoods=[1, 1, 0])
    with pytest.raises(ValueError, match="direction-compatible"):
        bayesian_partition_to_evidence(result, _context())


def test_evidence_validator_rejects_duplicate_inference_hash() -> None:
    result = _result()
    items = bayesian_partition_to_evidence(result, _context())
    duplicate = list(items)
    collection = EvidenceCollection(
        decision_context_id=_context().id,
        items=duplicate,
    )
    errors = EvidenceValidator().validate_collection(collection)
    assert any("Duplicate evidence_hash" in error for error in errors)
