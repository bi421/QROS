from __future__ import annotations

import pytest

from researchos.decision_engine.contracts import (
    DecisionEvidenceItem,
    EvidenceSource,
    ProbabilityOutcome,
)
from researchos.decision_engine.probability import CalibratedLinearPool


def _item(source_id: str, distribution: dict[str, float], weight: float) -> DecisionEvidenceItem:
    return DecisionEvidenceItem(
        source=EvidenceSource.QUANT_ENGINE,
        source_id=source_id,
        direction=ProbabilityOutcome.BULLISH,
        strength=1.0,
        weight=weight,
        confidence=1.0,
        description="validated component",
        provenance={
            "calibration_status": "validated",
            "probability_distribution": distribution,
        },
    )


def test_calibrated_linear_pool_preserves_probability_simplex() -> None:
    result = CalibratedLinearPool().fuse(
        "ctx",
        "collection",
        [
            _item("a", {"bullish": 0.8, "bearish": 0.1, "neutral": 0.1}, 1.0),
            _item("b", {"bullish": 0.2, "bearish": 0.7, "neutral": 0.1}, 3.0),
        ],
    )

    assert result.bullish_probability == pytest.approx(0.35)
    assert result.bearish_probability == pytest.approx(0.55)
    assert result.neutral_probability == pytest.approx(0.10)
    assert (
        result.bullish_probability
        + result.bearish_probability
        + result.neutral_probability
    ) == pytest.approx(1.0)


def test_calibrated_linear_pool_rejects_unvalidated_component() -> None:
    item = _item("a", {"bullish": 0.8, "bearish": 0.1, "neutral": 0.1}, 1.0)
    item.provenance["calibration_status"] = "unknown"

    with pytest.raises(ValueError, match="validated calibration"):
        CalibratedLinearPool().fuse("ctx", "collection", [item])


def test_calibrated_linear_pool_rejects_non_simplex_distribution() -> None:
    item = _item("a", {"bullish": 0.8, "bearish": 0.8, "neutral": 0.1}, 1.0)

    with pytest.raises(ValueError, match="sum to 1.0"):
        CalibratedLinearPool().fuse("ctx", "collection", [item])
