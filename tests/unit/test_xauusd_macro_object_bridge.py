"""Tests for bridging existing macro assessment objects without rescoring."""

from datetime import datetime, timezone

import pytest

from researchos.macro.engine import ALL_DRIVERS
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
from researchos.orchestration.xauusd_macro_object_bridge import (
    macro_snapshot_from_existing_assessments,
)

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)

ASSESSMENT_TYPES = {
    "Real_Yield": RealYieldSnapshot,
    "DXY": DollarStrengthSnapshot,
    "Fed": FedPolicyAssessment,
    "Inflation": InflationAssessment,
    "Labor_Market": LaborMarketAssessment,
    "Economic_Growth": EconomicGrowthAssessment,
    "Safe_Haven": SafeHavenAssessment,
    "Central_Bank": CentralBankDemand,
    "Physical_Demand": PhysicalDemandSnapshot,
    "Positioning": PositioningAssessment,
}


def assessments(score=65.0):
    return {
        name: cls(
            id=f"macro-{name}",
            timestamp=NOW,
            score=score,
            confidence=0.8,
            evidence_ids=[f"raw-evidence-{name}"],
        )
        for name, cls in ASSESSMENT_TYPES.items()
    }


def test_maps_existing_ten_driver_assessments_without_rescoring():
    result = macro_snapshot_from_existing_assessments(
        assessments(score=65.0),
        provider_id="existing-macro-engine-v1",
        max_age_seconds=3600,
    )
    assert len(result.observations) == len(ALL_DRIVERS) == 10
    first = result.observations[0]
    assert first.score == 65.0
    assert first.confidence == 0.8
    assert first.gold_impact_direction == 1
    assert first.as_of == NOW
    assert f"macro-object:macro-{first.driver_name}" in first.source_refs
    assert f"macro-evidence:raw-evidence-{first.driver_name}" in first.source_refs


@pytest.mark.parametrize(("score", "expected_direction"), [(0.0, -1), (50.0, 0), (100.0, 1)])
def test_existing_gold_score_maps_to_direction_without_changing_score(score, expected_direction):
    result = macro_snapshot_from_existing_assessments(
        assessments(score=score),
        provider_id="existing-macro-engine-v1",
        max_age_seconds=3600,
    )
    assert all(item.score == score for item in result.observations)
    assert all(item.gold_impact_direction == expected_direction for item in result.observations)


def test_missing_driver_fails_closed():
    inputs = assessments()
    inputs.pop(ALL_DRIVERS[-1])
    with pytest.raises(ValueError, match="MACRO_ASSESSMENTS_MISSING"):
        macro_snapshot_from_existing_assessments(
            inputs,
            provider_id="existing-macro-engine-v1",
            max_age_seconds=3600,
        )


def test_wrong_assessment_type_fails_closed():
    inputs = assessments()
    inputs["DXY"] = RealYieldSnapshot(
        id="wrong-type",
        timestamp=NOW,
        score=60.0,
        confidence=0.8,
        evidence_ids=["raw-evidence"],
    )
    with pytest.raises(ValueError, match="INVALID_MACRO_ASSESSMENT_TYPE:DXY"):
        macro_snapshot_from_existing_assessments(
            inputs,
            provider_id="existing-macro-engine-v1",
            max_age_seconds=3600,
        )


def test_per_driver_freshness_budget_is_required():
    with pytest.raises(ValueError, match="MACRO_FRESHNESS_BUDGET_MISSING"):
        macro_snapshot_from_existing_assessments(
            assessments(),
            provider_id="existing-macro-engine-v1",
            max_age_seconds={"Real_Yield": 3600},
        )


def test_invalid_existing_score_is_rejected_without_recalculation():
    inputs = assessments()
    inputs["Real_Yield"].score = float("nan")
    with pytest.raises(ValueError, match="INVALID_MACRO_SCORE"):
        macro_snapshot_from_existing_assessments(
            inputs,
            provider_id="existing-macro-engine-v1",
            max_age_seconds=3600,
        )
