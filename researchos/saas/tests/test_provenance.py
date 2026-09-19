from uuid import uuid4

from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.provenance import build_result_record, manifest_sha256


def _result(artifact_id: str = "a", source: str = "0" * 64) -> ResearchResult:
    return ResearchResult(
        status="SUCCEEDED",
        source_dataset_sha256=source,
        artifacts=(ResearchArtifact(artifact_id, "evidence", "1" * 64),),
    )


def test_manifest_hash_is_deterministic():
    assert manifest_sha256(_result()) == manifest_sha256(_result())


def test_manifest_changes_when_artifact_identity_changes():
    assert manifest_sha256(_result("a")) != manifest_sha256(_result("b"))


def test_result_record_binds_workspace_and_run_identity():
    workspace_id = uuid4()
    run_id = uuid4()
    record = build_result_record(workspace_id, run_id, _result())
    assert record.workspace_id == workspace_id
    assert record.research_run_id == run_id
    assert record.source_dataset_sha256 == "0" * 64
    assert len(record.manifest_sha256) == 64


def test_artifact_manifest_is_order_independent():
    artifacts = (
        ResearchArtifact("b", "result", "2" * 64),
        ResearchArtifact("a", "evidence", "1" * 64),
    )
    from researchos.saas.provenance import artifact_manifest_sha256
    assert artifact_manifest_sha256(artifacts) == artifact_manifest_sha256(tuple(reversed(artifacts)))


def test_artifact_manifest_has_versioned_canonical_schema():
    from researchos.saas.provenance import artifact_manifest_payload
    artifacts = (ResearchArtifact("a", "evidence", "1" * 64),)
    assert artifact_manifest_payload(artifacts) == {
        "schema": "research-artifact-manifest.v1",
        "artifacts": [{"artifact_id": "a", "kind": "evidence", "content_sha256": "1" * 64}],
    }


def test_artifact_manifest_rejects_duplicate_artifact_ids():
    import pytest
    from researchos.saas.provenance import artifact_manifest_payload
    artifacts = (
        ResearchArtifact("a", "evidence", "1" * 64),
        ResearchArtifact("a", "result", "2" * 64),
    )
    with pytest.raises(ValueError, match="artifact_id must be unique"):
        artifact_manifest_payload(artifacts)
