"""Directional evidence adapter for the quantitative mathematics layer."""
from __future__ import annotations
from researchos.decision_engine.contracts import DecisionEvidenceItem,EvidenceSource,ProbabilityOutcome
from researchos.decision_engine.context import DecisionContext
from researchos.quant_math.contracts import QuantMathResult

class QuantMathEvidenceProvider:
    def __init__(self,result:QuantMathResult):
        self.result=result
    def collect(self,context:DecisionContext)->list[DecisionEvidenceItem]:
        g=self.result.geometry
        direction=ProbabilityOutcome.NEUTRAL
        if g.slope>0: direction=ProbabilityOutcome.BULLISH
        elif g.slope<0: direction=ProbabilityOutcome.BEARISH
        strength=min(1.0,max(0.0,abs(g.trend_r2)))
        confidence=strength
        return [DecisionEvidenceItem(
            source=EvidenceSource.QUANT_ENGINE,
            source_id=self.result.result_hash,
            direction=direction,
            strength=strength,
            weight=0.15,
            confidence=confidence,
            description="Quantitative market geometry and statistical evidence",
            supporting_ids=[context.id],
            provenance={"calculation_version":self.result.calculation_version,"result_hash":self.result.result_hash,"slope":g.slope,"angle_degrees":g.angle_degrees,"curvature":g.curvature,"trend_r2":g.trend_r2,"support_level":g.support_level,"resistance_level":g.resistance_level},
        )]
