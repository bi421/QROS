import pytest\n\nfrom researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.quant_math_provider import QuantMathEvidenceProvider
from researchos.quant_math import QuantMathEngine

def test_provider_exposes_independent_quant_dimensions():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    result=QuantMathEngine().evaluate(
        [100,101,103,102,105],
        successes=8,
        failures=2,
        monte_carlo_simulations=50,
    )
    items=QuantMathEvidenceProvider(result).collect(context)
    assert [item.source_id for item in items]==[
        f"{result.result_hash}:geometry",
        f"{result.result_hash}:statistics",
        f"{result.result_hash}:bayesian",
        f"{result.result_hash}:monte_carlo",
    ]
    assert all(item.source.value=="QuantEngine" for item in items)
    assert all(item.supporting_ids==[context.id] for item in items)
    assert all(item.provenance["result_hash"]==result.result_hash for item in items)

def test_provider_does_not_claim_edge_from_geometry_alone():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    result=QuantMathEngine().evaluate([100,101,102,103])
    item=QuantMathEvidenceProvider(result).collect(context)[0]
    assert item.provenance["component"]=="geometry"
    assert item.provenance["trend_r2"]==1.0


def test_provider_can_append_directional_bayesian_partition_evidence():
    from researchos.quant_math.bayesian_update import bayesian_update
    from researchos.quant_math.partition import ProbabilityPartition

    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    result=QuantMathEngine().evaluate([100,101,102,103])
    partition=ProbabilityPartition.from_sequences(
        "direction", ["Bullish","Bearish","Neutral"], [0.3,0.4,0.3]
    )
    update=bayesian_update(
        partition,
        event_id="direction-event",
        likelihoods=[0.8,0.2,0.5],
        evidence_hash="direction-evidence",
    )
    items=QuantMathEvidenceProvider(result, bayesian_partition=update).collect(context)
    bayesian_items=[i for i in items if i.provenance.get("component")=="bayesian_partition"]
    assert len(bayesian_items)==3
    assert [i.weight for i in bayesian_items] == pytest.approx(update.posterior_probabilities)
