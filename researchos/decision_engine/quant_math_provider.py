"""Directional evidence adapter for the quantitative mathematics layer."""
from __future__ import annotations
from researchos.decision_engine.bayesian_partition_provider import bayesian_partition_to_evidence
from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.contracts import DecisionEvidenceItem,EvidenceSource,ProbabilityOutcome
from researchos.quant_math.bayesian_update import BayesianUpdateResult
from researchos.quant_math.contracts import QuantMathResult

class QuantMathEvidenceProvider:
    """Expose independent quant dimensions; ProbabilityCalculator fuses them later."""
    def __init__(self,result:QuantMathResult):
        self.result=result

    @staticmethod
    def _direction(value:float)->ProbabilityOutcome:
        if value>0: return ProbabilityOutcome.BULLISH
        if value<0: return ProbabilityOutcome.BEARISH
        return ProbabilityOutcome.NEUTRAL

    def collect(self,context:DecisionContext)->list[DecisionEvidenceItem]:
        r=self.result; g=r.geometry; s=r.statistics
        items=[
            DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,source_id=f"{r.result_hash}:geometry",
                direction=self._direction(g.slope),strength=min(1.0,abs(g.trend_r2)),
                weight=0.15,confidence=min(1.0,abs(g.trend_r2)),
                description="Market geometry: slope, angle, curvature and trend fit",
                supporting_ids=[context.id],
                provenance={"component":"geometry","version":"MARKET_GEOMETRY_V1","result_hash":r.result_hash,
                             "slope":g.slope,"angle_degrees":g.angle_degrees,"distance":g.distance,
                             "curvature":g.curvature,"trend_r2":g.trend_r2,
                             "support_level":g.support_level,"resistance_level":g.resistance_level},
            ),
            DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,source_id=f"{r.result_hash}:statistics",
                direction=self._direction(s.regression_slope or 0.0),
                strength=min(1.0,abs(s.regression_r2 or 0.0)),
                weight=0.15,confidence=min(1.0,abs(s.regression_r2 or 0.0)),
                description="Statistics: dispersion, z-score, correlation and regression",
                supporting_ids=[context.id],
                provenance={"component":"statistics","version":"STATISTICS_V1","result_hash":r.result_hash,
                             "count":s.count,"mean":s.mean,"variance":s.variance,
                             "standard_deviation":s.standard_deviation,"z_score_last":s.z_score_last,
                             "correlation":s.correlation,"regression_slope":s.regression_slope,
                             "regression_r2":s.regression_r2},
            ),
        ]
        if r.bayesian is not None:
            posterior=r.bayesian.posterior_mean
            items.append(DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,source_id=f"{r.result_hash}:bayesian",
                direction=self._direction(posterior-0.5),
                strength=min(1.0,abs(posterior-0.5)*2.0),weight=0.15,
                confidence=min(1.0,(r.bayesian.successes+r.bayesian.failures)/100.0),
                description="Bayesian posterior probability",supporting_ids=[context.id],
                provenance={"component":"bayesian","result_hash":r.result_hash,
                             "prior_alpha":r.bayesian.prior_alpha,"prior_beta":r.bayesian.prior_beta,
                             "successes":r.bayesian.successes,"failures":r.bayesian.failures,
                             "posterior_mean":posterior},
            ))
        if self.bayesian_partition is not None:\n            items.extend(bayesian_partition_to_evidence(self.bayesian_partition, context))\n        if r.monte_carlo is not None:
            median=r.monte_carlo.percentile_50
            spread=r.monte_carlo.percentile_95-r.monte_carlo.percentile_05
            direction=self._direction(r.monte_carlo.mean_terminal-median)
            confidence=0.0 if spread==0 else min(1.0,max(0.0,1.0-(median-r.monte_carlo.percentile_05)/spread))
            strength=0.0 if median==0 else min(1.0,abs(r.monte_carlo.mean_terminal/median-1.0))
            items.append(DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,source_id=f"{r.result_hash}:monte_carlo",
                direction=direction,strength=strength,weight=0.15,confidence=confidence,
                description="Monte Carlo terminal distribution",supporting_ids=[context.id],
                provenance={"component":"monte_carlo","result_hash":r.result_hash,
                             "simulations":r.monte_carlo.simulations,"seed":r.monte_carlo.seed,
                             "mean_terminal":r.monte_carlo.mean_terminal,
                             "percentile_05":r.monte_carlo.percentile_05,
                             "percentile_50":median,"percentile_95":r.monte_carlo.percentile_95},
            ))
        return items
