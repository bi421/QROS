"""Bridge existing persisted MacroAnalysisEngine assessments into XAUUSD evidence.

No existing macro scoring is changed. The bridge only maps the already
computed, documented gold-support score scale into an explicit directional
field required by the new evidence contract.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime

from researchos.macro.engine import (
    DRIVER_CENTRAL_BANK,
    DRIVER_DXY,
    DRIVER_FED,
    DRIVER_GROWTH,
    DRIVER_INFLATION,
    DRIVER_LABOR,
    DRIVER_PHYSICAL,
    DRIVER_POSITIONING,
    DRIVER_REAL_YIELD,
    DRIVER_SAFE_HAVEN,
)
from researchos.objects.macro import (
    CentralBankDemand,
    DollarStrengthSnapshot,
    EconomicGrowthAssessment,
    FedPolicyAssessment,
    InflationAssessment,
    LaborMarketAssessment,
    PhysicalDemandSnapshot,
    PositioningAssessment,
    RealYieldSnapshot,
    SafeHavenAssessment,
)
from researchos.orchestration.xauusd_macro_adapter import (
    MacroDriverObservation,
    XAUUSDMacroSnapshot,
)

_MACRO_OBJECT_TYPES = {
    DRIVER_REAL_YIELD: RealYieldSnapshot,
    DRIVER_DXY: DollarStrengthSnapshot,
    DRIVER_FED: FedPolicyAssessment,
    DRIVER_INFLATION: InflationAssessment,
    DRIVER_LABOR: LaborMarketAssessment,
    DRIVER_GROWTH: EconomicGrowthAssessment,
    DRIVER_SAFE_HAVEN: SafeHavenAssessment,
    DRIVER_CENTRAL_BANK: CentralBankDemand,
    DRIVER_PHYSICAL: PhysicalDemandSnapshot,
    DRIVER_POSITIONING: PositioningAssessment,
}


def _direction_from_existing_gold_score(score: float) -> int:
    """Interpret the existing 0-100 gold-support scale without rescoring it."""
    if isinstance(score, bool):
        raise ValueError("INVALID_EXISTING_MACRO_SCORE")
    try:
        value = float(score)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_EXISTING_MACRO_SCORE") from exc
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError("INVALID_EXISTING_MACRO_SCORE")
    return 1 if value > 50.0 else -1 if value < 50.0 else 0


def macro_snapshot_from_existing_assessments(
    assessments: Mapping[str, object],
    *,
    provider_id: str,
    max_age_seconds: int | Mapping[str, int],
) -> XAUUSDMacroSnapshot:
    """Map all ten existing driver objects into the typed macro snapshot.

    Every driver must have the exact existing assessment type. The freshness
    budget is caller-supplied because source cadence differs by driver.
    Assessment timestamps and IDs are preserved as provenance; no raw source
    data is fetched and no score/confidence is recalculated.
    """
    if not isinstance(assessments, Mapping):
        raise ValueError("MACRO_ASSESSMENTS_MUST_BE_MAPPING")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("MACRO_PROVIDER_ID_REQUIRED")

    missing = tuple(name for name in _MACRO_OBJECT_TYPES if name not in assessments)
    if missing:
        raise ValueError("MACRO_ASSESSMENTS_MISSING:" + ",".join(missing))

    observations: list[MacroDriverObservation] = []
    for driver_name, expected_type in _MACRO_OBJECT_TYPES.items():
        assessment = assessments[driver_name]
        if not isinstance(assessment, expected_type):
            raise ValueError(f"INVALID_MACRO_ASSESSMENT_TYPE:{driver_name}")

        try:
            score = assessment.score
            confidence = assessment.confidence
            as_of: datetime = assessment.timestamp
            object_id = assessment.id
            evidence_ids = assessment.evidence_ids
        except AttributeError as exc:
            raise ValueError(f"INCOMPLETE_MACRO_ASSESSMENT:{driver_name}") from exc

        if isinstance(max_age_seconds, Mapping):
            if driver_name not in max_age_seconds:
                raise ValueError(f"MACRO_FRESHNESS_BUDGET_MISSING:{driver_name}")
            age_budget = max_age_seconds[driver_name]
        else:
            age_budget = max_age_seconds

        refs = []
        if isinstance(object_id, str) and object_id.strip():
            refs.append(f"macro-object:{object_id}")
        if isinstance(evidence_ids, (tuple, list)):
            refs.extend(
                f"macro-evidence:{item}"
                for item in evidence_ids
                if isinstance(item, str) and item.strip()
            )
        if not refs:
            raise ValueError(f"MACRO_SOURCE_PROVENANCE_REQUIRED:{driver_name}")

        observations.append(
            MacroDriverObservation(
                driver_name=driver_name,
                score=score,
                confidence=confidence,
                gold_impact_direction=_direction_from_existing_gold_score(score),
                as_of=as_of,
                source_refs=tuple(refs),
                max_age_seconds=age_budget,
            )
        )

    return XAUUSDMacroSnapshot(
        provider_id=provider_id,
        observations=tuple(observations),
    )


__all__ = ["macro_snapshot_from_existing_assessments"]
