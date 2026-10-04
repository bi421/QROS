"""Bridge Bayesian partition posteriors into the canonical decision-evidence path.

The Bayesian layer owns conditioning. The DecisionEngine owns evidence fusion.
This adapter deliberately does not create a second ProbabilityAssessment.
"""
from __future__ import annotations

from researchos.decision_engine.context import DecisionContext
from researchos.decision_engine.contracts import (
    DecisionEvidenceItem,
    EvidenceSource,
    ProbabilityOutcome,
)
from researchos.quant_math.bayesian_update import BayesianUpdateResult

_DIRECTION_MAP = {
    "bullish": ProbabilityOutcome.BULLISH,
    "bearish": ProbabilityOutcome.BEARISH,
    "neutral": ProbabilityOutcome.NEUTRAL,
}
ADAPTER_VERSION = "BAYESIAN_PARTITION_EVIDENCE_V1"


def bayesian_partition_to_evidence(
    result: BayesianUpdateResult,
    context: DecisionContext,
    *,
    item_weight: float = 1.0,
) -> list[DecisionEvidenceItem]:
    """Expose a directional Bayesian posterior as canonical evidence.

    The adapter is intentionally strict: only a three-way partition whose
    hypotheses map one-to-one to Bullish/Bearish/Neutral may enter the
    directional ProbabilityCalculator path. Arbitrary state spaces remain
    valid Bayesian results but must not be silently coerced into directions.

    Posterior mass is represented by the canonical item's weight while
    confidence remains 1.0 because the item is a deterministic consequence
    of the supplied probabilistic model. Model uncertainty is preserved in
    provenance rather than fabricated as a confidence score.
    """
    if not 0.0 <= float(item_weight) <= 1.0:
        raise ValueError("item_weight must be in [0, 1]")

    directions: list[ProbabilityOutcome] = []
    seen: set[ProbabilityOutcome] = set()
    for hypothesis in result.hypotheses:
        key = str(hypothesis).strip().lower()
        direction = _DIRECTION_MAP.get(key)
        if direction is None:
            raise ValueError(
                "Bayesian partition is not direction-compatible; "
                "hypotheses must be exactly Bullish/Bearish/Neutral"
            )
        if direction in seen:
            raise ValueError(f"duplicate directional hypothesis: {hypothesis}")
        seen.add(direction)
        directions.append(direction)

    required = set(_DIRECTION_MAP.values())
    if seen != required or len(result.hypotheses) != 3:
        raise ValueError(
            "direction-compatible Bayesian partition requires exactly "
            "Bullish, Bearish, Neutral hypotheses"
        )

    items: list[DecisionEvidenceItem] = []
    for hypothesis, posterior, direction in zip(
        result.hypotheses, result.posterior_probabilities, directions
    ):
        source_id = f"{result.event_id}:{hypothesis}"
        items.append(
            DecisionEvidenceItem(
                source=EvidenceSource.QUANT_ENGINE,
                source_id=source_id,
                direction=direction,
                strength=float(posterior),
                weight=float(posterior) * float(item_weight),
                confidence=1.0,
                description=f"Bayesian partition posterior for {hypothesis}",
                supporting_ids=[context.id, result.evidence_hash],
                provenance={
                    "component": "bayesian_partition",
                    "adapter_version": ADAPTER_VERSION,
                    "partition_id": result.partition_id,
                    "partition_version": result.partition_version,
                    "event_id": result.event_id,
                    "update_version": result.update_version,
                    "evidence_hash": result.evidence_hash,
                    "result_hash": result.result_hash,
                    "hypothesis": hypothesis,
                    "prior_probability": result.prior_probabilities[
                        result.hypotheses.index(hypothesis)
                    ],
                    "likelihood": result.likelihoods[
                        result.hypotheses.index(hypothesis)
                    ],
                    "posterior_probability": float(posterior),
                    "predictive_evidence_probability": result.evidence_probability,
                    "inference_family": "bayesian_partition",
                },
            )
        )
    return items


__all__ = ["ADAPTER_VERSION", "bayesian_partition_to_evidence"]
