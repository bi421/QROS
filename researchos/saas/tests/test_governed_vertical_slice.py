from __future__ import annotations

from uuid import uuid4

from researchos.claims.claim import ResearchClaim, ResearchPlan
from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import Plan, ResearchJob, ResearchJobStatus, TenantContext, WorkspaceRole
from researchos.saas.finding import ResearchFindingRecord, VALIDATED_STATUS
from researchos.saas.finding_api import InMemoryResearchFindingStore
from researchos.saas.research_report import build_research_report
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.validation import ResearchValidationRecord
from researchos.saas.validation_api import InMemoryResearchValidationStore


def _plan() -> ResearchPlan:
    return ResearchPlan(
        hypothesis="A pre-registered XAUUSD M1 relationship is measurable.",
        sample_definition="XAUUSD M1 event-time sample",
        features=("return_1",),
        labels=("return_60m",),
        train_validation_test="time ordered 60/20/20",
        exclusions=("missing timestamps",),
        costs_slippage="explicit transaction-cost model",
        statistical_tests=("paired bootstrap",),
        metrics=("brier_score",),
        stopping_rules=("no early stopping",),
        multiple_testing_policy="pre-registered familywise policy",
        replication_policy="independent holdout replication",
    )


def test_governed_research_vertical_slice_preserves_lineage_end_to_end() -> None:
    tenant = TenantContext(uuid4(), uuid4(), Plan.PRO, WorkspaceRole.RESEARCHER)

    claim = ResearchClaim(
        statement="A pre-registered XAUUSD M1 relationship is measurable.",
        target_population="XAUUSD M1",
        instrument="XAUUSD",
        horizon="60m",
        timestamp_policy="event-time only",
        economic_rationale="research contract test",
        falsification_conditions=("brier improvement <= 0",),
        primary_metrics=("brier_score",),
        minimum_evidence_requirements=("N >= 100",),
        creator=str(tenant.user_id),
        workspace_id=str(tenant.workspace_id),
        research_id="vertical-slice-test",
    )
    plan_hash = claim.lock_plan(_plan())
    assert claim.is_plan_locked
    assert claim.plan_hash == plan_hash

    jobs = InMemoryResearchJobStore()
    job = jobs.create(
        tenant.workspace_id,
        ResearchJob(
            id=uuid4(),
            workspace_id=tenant.workspace_id,
            dataset_version_id=uuid4(),
            workflow_id="xauusd_m1_frozen_research_v1",
            status=ResearchJobStatus.QUEUED,
            source_dataset_sha256="1" * 64,
            created_by=tenant.user_id,
            claim_id=claim.id,
            plan_hash=plan_hash,
        ),
    )
    lease = jobs.claim(tenant.workspace_id, job.id, "vertical-slice-test", 60)
    result = jobs.record_result(
        tenant.workspace_id,
        job.id,
        lease.token,
        ResearchResult(
            status="SUCCEEDED",
            source_dataset_sha256=job.source_dataset_sha256,
            artifacts=(ResearchArtifact("result", "result", "2" * 64),),
        ),
    )
    assert job.claim_id == claim.id
    assert job.plan_hash == plan_hash

    validations = InMemoryResearchValidationStore()
    validation_payload = {"gate": "PASS", "brier_improvement": 0.1}
    validation = ResearchValidationRecord(
        id=uuid4(),
        workspace_id=tenant.workspace_id,
        research_run_id=job.id,
        result_manifest_sha256=result.manifest_sha256,
        claim_id=claim.id,
        plan_hash=plan_hash,
        validation_sha256=ResearchValidationRecord.compute_validation_sha256(validation_payload),
        status=VALIDATED_STATUS,
        metrics={"brier_improvement": 0.1},
    )
    validations.create(validation)

    findings = InMemoryResearchFindingStore()
    finding_payload = {"finding": "validated", "metrics": {"brier_improvement": 0.1}}
    finding = ResearchFindingRecord(
        id=uuid4(),
        workspace_id=tenant.workspace_id,
        research_run_id=job.id,
        validation_id=validation.id,
        result_manifest_sha256=result.manifest_sha256,
        validation_sha256=validation.validation_sha256,
        claim_id=claim.id,
        plan_hash=plan_hash,
        finding_sha256=ResearchFindingRecord.compute_finding_sha256(finding_payload),
        status=VALIDATED_STATUS,
        payload=finding_payload,
    )
    findings.create(finding)

    report = build_research_report(result, tuple(), finding=finding)

    assert validation.result_manifest_sha256 == result.manifest_sha256
    assert validation.claim_id == claim.id
    assert validation.plan_hash == plan_hash
    assert finding.validation_id == validation.id
    assert finding.validation_sha256 == validation.validation_sha256
    assert finding.result_manifest_sha256 == result.manifest_sha256
    assert finding.claim_id == claim.id
    assert finding.plan_hash == plan_hash
    assert report.finding_sha256 == finding.finding_sha256
    assert finding.finding_sha256 in report.markdown
    assert validation.validation_sha256 in report.markdown
    assert result.manifest_sha256 in report.markdown
    assert plan_hash in report.markdown
