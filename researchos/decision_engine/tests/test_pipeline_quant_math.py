from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.pipeline import DecisionPipeline
from researchos.quant_math import QuantMathEngine

def test_pipeline_can_fuse_quant_math_without_manual_provider_wiring():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    quant=QuantMathEngine().evaluate([100,101,102,103,104],successes=8,failures=2)
    result=DecisionPipeline(quant_math_result=quant).run(context)
    assert result.evidence.total_items==2
    assert all(item.source.value=="QuantEngine" for item in result.evidence.items)
    assert result.probability.bullish_probability>result.probability.bearish_probability

def test_pipeline_rejects_ambiguous_aggregator_and_quant_result():
    context=DecisionContext(asset="XAUUSD",timeframe="M1")
    quant=QuantMathEngine().evaluate([100,101])
    from researchos.decision_engine.evidence import EvidenceAggregator
    import pytest
    with pytest.raises(ValueError,match="either aggregator or quant_math_result"):
        DecisionPipeline(aggregator=EvidenceAggregator(),quant_math_result=quant).run(context)
