from __future__ import annotations

import pytest

from researchos.claims import (
    EvidenceState,
    ResearchClaim,
    ResearchClaimRepository,
    ResearchPlan,
)
from researchos.storage.repository import ResearchRepository


def make_plan() -> ResearchPlan:
    return ResearchPlan(
        hypothesis="DXY return is associated with next-session XAUUSD return.",
        sample_definition="XAUUSD M1, 2021-2025, regular sessions only.",
        features=("dxy_return_1",),
        labels=("xauusd_return_60m",),
        train_validation_test="2021-2023 / 2024 / 2025 chronological split",
        exclusions=("rows failing point-in-time availability",),
        costs_slippage="36-point spread; no interpolation or synthetic repair.",
        statistical_tests=("mean difference", "bootstrap confidence interval"),
        metrics=("mean_return", "hit_rate", "confidence_interval"),
        stopping_rules=("stop if data integrity gate fails",),
        multiple_testing_policy="planned primary test plus explicitly logged exploratory tests",
        replication_policy="independent period or dataset replication before support",
    )


def make_claim() -> ResearchClaim:
    return ResearchClaim(
        statement="A positive DXY shock is associated with a negative XAUUSD return over 60 minutes.",
        target_population="XAUUSD M1 observations, 2021-2025",
        instrument="XAUUSD",
        horizon="60 minutes",
        timestamp_policy="point-in-time feature availability",
        economic_rationale="Dollar strength may pressure USD-denominated gold.",
        falsification_conditions=("effect is zero or changes sign in independent replication",),
        primary_metrics=("mean_return", "confidence_interval"),
        minimum_evidence_requirements=("temporal integrity pass", "independent replication"),
        creator="test-user",
        workspace_id="workspace-test",
    )


def test_plan_hash_is_deterministic_and_lock_is_idempotent() -> None:
    claim = make_claim()
    plan = make_plan()

    first = claim.lock_plan(plan)
    second = claim.lock_plan(plan)

    assert first == plan.content_hash
    assert second == first
    assert claim.is_plan_locked
    assert claim.plan_hash == first

    with pytest.raises(ValueError, match="already locked"):
        ResearchPlan(
            **{
                **plan.to_dict(),
                "hypothesis": "A materially different hypothesis.",
                "features": ["vix_return_1"],
            }
        )


def test_locked_plan_rejects_material_change() -> None:
    claim = make_claim()
    plan = make_plan()
    claim.lock_plan(plan)
    changed = ResearchPlan(
        **{
            **plan.to_dict(),
            "hypothesis": "A materially different hypothesis.",
            "features": ["vix_return_1"],
        }
    )

    with pytest.raises(ValueError, match="already locked"):
        claim.lock_plan(changed)


def test_claim_versioning_creates_new_identity_without_mutating_parent() -> None:
    claim = make_claim()
    claim.lock_plan(make_plan())
    claim.set_evidence_state(EvidenceState.CANDIDATE)
    claim.add_experiment("exp-001")

    child = claim.fork_version(
        "A positive DXY shock is associated with a negative XAUUSD return over 30 minutes."
    )

    assert child.id != claim.id
    assert child.version == 2
    assert child.parent_claim_id == claim.id
    assert child.is_plan_locked is False
    assert claim.version == 1
    assert claim.evidence_state == EvidenceState.CANDIDATE
    assert claim.experiment_ids == ("exp-001",)


def test_round_trip_preserves_locked_plan_and_lineage_fields() -> None:
    claim = make_claim()
    claim.lock_plan(make_plan())
    claim.add_experiment("exp-001")
    claim.add_evidence("a" * 64)

    restored = ResearchClaim.from_dict(claim.to_dict())

    assert restored.id == claim.id
    assert restored.claim_hash == claim.claim_hash
    assert restored.research_plan is not None
    assert restored.research_plan.content_hash == claim.plan_hash
    assert restored.experiment_ids == ("exp-001",)
    assert restored.evidence_hashes == ("a" * 64,)


def test_claim_repository_reuses_canonical_generic_store() -> None:
    repository = ResearchRepository(db_path=":memory:")
    claims = ResearchClaimRepository(repository)
    claim = make_claim()
    claim.lock_plan(make_plan())

    claims.save(claim)
    loaded = claims.get(claim.id)

    assert loaded is not None
    assert loaded.id == claim.id
    assert loaded.plan_hash == claim.plan_hash
    assert claims.count() == 1
    assert [item.id for item in claims.list()] == [claim.id]

    claims.close()


def test_claim_rejects_invalid_version_parent_contract() -> None:
    with pytest.raises(ValueError, match="version 1"):
        ResearchClaim(statement="claim", version=1, parent_claim_id="parent")

    with pytest.raises(ValueError, match="version > 1"):
        ResearchClaim(statement="claim", version=2)
