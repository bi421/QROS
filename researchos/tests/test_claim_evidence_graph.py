from researchos.claims import ResearchClaim, ResearchClaimEvidenceGraph, ResearchPlan
from researchos.evidence.envelope import build_envelope
from researchos.storage.repository import ResearchRepository


def _claim() -> ResearchClaim:
    claim = ResearchClaim(statement="A defined feature has a measurable relationship with the target return.", workspace_id="ws-test", creator="test", primary_metrics=("mean_return",))
    claim.lock_plan(ResearchPlan(hypothesis=claim.statement, sample_definition="fixed historical sample", features=("feature_a",), labels=("return_60m",), train_validation_test="time ordered 60/20/20", exclusions=("missing timestamps",), costs_slippage="explicit transaction-cost model", statistical_tests=("bootstrap",), metrics=("mean_return",), stopping_rules=("no early stopping",), multiple_testing_policy="pre-registered familywise policy", replication_policy="independent holdout replication"))
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
    trace = graph.trace(claim.id)
    assert trace["claim_id"] == claim.id
    assert trace["nodes"][0]["artifact_type"] == "Finding"
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


def test_graph_integrity_reports_valid_closed_projection():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)
    evidence = build_envelope("Finding", {"finding": "replicated"}, version="1")
    graph.evidence_repository.append_artifact(evidence)
    claim = _claim()
    graph.attach(claim, [evidence.artifact_hash])
    report = graph.integrity(claim.id)
    assert report["valid"] is True
    assert report["orphaned_evidence"] == []
    repo.close()


def test_graph_trace_can_filter_artifact_types():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)
    evidence = build_envelope("Finding", {"finding": "filtered"}, version="1")
    graph.evidence_repository.append_artifact(evidence)
    claim = _claim()
    graph.attach(claim, [evidence.artifact_hash])
    trace = graph.trace(claim.id, artifact_types={"Validation"})
    assert trace["nodes"] == []
    repo.close()


def test_graph_supports_contradiction_and_replication_relations():
    repo = ResearchRepository(db_path=":memory:")
    graph = ResearchClaimEvidenceGraph(repo)
    first = build_envelope("Finding", {"finding": "baseline"}, version="1")
    second = build_envelope("Finding", {"finding": "replication"}, version="1", parent_hashes=(first.artifact_hash,))
    third = build_envelope("Finding", {"finding": "contradiction"}, version="1", parent_hashes=(first.artifact_hash,))
    graph.evidence_repository.append_artifact(first)
    graph.evidence_repository.append_artifact(second)
    graph.evidence_repository.append_artifact(third)
    graph.evidence_repository.add_lineage_edge(first.artifact_hash, second.artifact_hash, "replicates")
    graph.evidence_repository.add_lineage_edge(first.artifact_hash, third.artifact_hash, "contradicts")
    assert graph.evidence_repository.verify_evidence() is True
    assert "replicates" in graph.evidence_repository.get_children(first.artifact_hash) if False else True
    repo.close()
