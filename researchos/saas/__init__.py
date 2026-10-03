"""SaaS delivery boundary for QROS.

This package owns tenancy, API, job orchestration, usage policy, and delivery
concerns. Scientific semantics remain in researchos.research_core and the
existing research pipeline.
"""

from researchos.saas.audit import AuditEvent, InMemoryAuditEventStore, SupabaseAuditEventStore
from researchos.saas.contracts import (
    Plan,
    ResearchJob,
    ResearchJobStatus,
    TenantContext,
    UsagePolicy,
)
from researchos.saas.datasets import (
    Dataset,
    DatasetVersion,
    InMemoryDatasetStorage,
    InMemoryDatasetStore,
    SupabaseDatasetStorage,
    SupabaseDatasetStore,
)
from researchos.saas.queue import InMemoryResearchJobQueue, SupabaseResearchJobQueue
from researchos.saas.retention_audit import retention_audit_callback
from researchos.saas.retention_reconciliation import (
    DeletionOperation,
    DeletionOperationState,
    InMemoryDeletionOperationStore,
    SupabaseDeletionOperationStore,
)
from researchos.saas.supabase_claim_store import SupabaseResearchClaimStore
from researchos.saas.supabase_job_store import SupabaseResearchJobStore
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver

__all__ = [
    "AuditEvent",
    "Dataset",
    "DatasetVersion",
    "DeletionOperation",
    "DeletionOperationState",
    "InMemoryAuditEventStore",
    "InMemoryDatasetStorage",
    "InMemoryDatasetStore",
    "InMemoryDeletionOperationStore",
    "InMemoryResearchJobQueue",
    "Plan",
    "ResearchJob",
    "ResearchJobStatus",
    "SupabaseAuditEventStore",
    "SupabaseDatasetStorage",
    "SupabaseDatasetStore",
    "SupabaseDeletionOperationStore",
    "SupabaseResearchClaimStore",
    "SupabaseResearchJobQueue",
    "SupabaseResearchJobStore",
    "SupabaseWorkspaceMembershipResolver",
    "TenantContext",
    "UsagePolicy",
    "retention_audit_callback",
]
