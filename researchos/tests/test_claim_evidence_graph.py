from researchos.claims import ResearchClaim, ResearchClaimEvidenceGraph, ResearchPlan
from researchos.evidence.envelope import build_envelope
from researchos.storage.repository import ResearchRepository


def _claim() -> ResearchClaim:
    claim = ResearchClaim(
        statement="A defined feature has a measurable relationship with the target return.",
        workspace_id="ws-test",
        creator="test",
        primary_metrics=("mean_return",),
    )
    claim.lock_plan(
        ResearchPlan(
            hypothesis=claim.statement,
            sample_definition="fixed historical sample",
            features=("feature_a",),
            labels=("return_60m",),
            train_validation_test="time ordered 60/20/20",
            exclusions=("missing timestamps",),
            costs_slippage="explicit transaction-cost model",
            statistical_tests=("bootstrap",),
            metrics=("mean_return",),
            stopping_rules=("no early stopping",),
            multiple_testing_policy="pre-registered familywise policy",
            replication_policy="independent holdout replication",
        )
    )
    return claim


def test_claim_can_attach_only_existing_immutable_evidence():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)
    evidence = build_envelope("Finding", {"finding": "inconclusive"}, version="1")
    graph.evidence_repository.append_artifact(evidence)

    claim = _claim()
    result = graph.attach(claim, [evidence.artifact_hash])

    assert result.claim_id == claim.id
    assert result.plan_hash == claim.plan_hash
    assert result.evidence_hashes == (evidence.artifact_hash,)
    assert graph.verify(claim.id)

    repo.close()


def test_claim_attachment_rejects_missing_evidence():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)

    try:
        graph.attach(_claim(), ["does-not-exist"])
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing evidence must be rejected")
    finally:
        repo.close()


def test_claim_attachment_requires_locked_plan():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)
    claim = ResearchClaim(statement="An unlocked claim", workspace_id="ws-test")

    try:
        graph.attach(claim, [])
    except ValueError as exc:
        assert "plan must be locked" in str(exc)
    else:
        raise AssertionError("unlocked claims must not enter the evidence graph")
    finally:
        repo.close()
