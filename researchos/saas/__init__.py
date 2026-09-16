"""SaaS delivery boundary for QROS.

This package owns tenancy, API, job orchestration, usage policy, and delivery
concerns. Scientific semantics remain in ``researchos.research_core`` and the
existing research pipeline.
"""

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
from researchos.saas.supabase_job_store import SupabaseResearchJobStore
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver

__all__ = [
    "Dataset",
    "DatasetVersion",
    "InMemoryDatasetStorage",
    "InMemoryDatasetStore",
    "InMemoryResearchJobQueue",
    "Plan",
    "ResearchJob",
    "ResearchJobStatus",
    "SupabaseDatasetStorage",
    "SupabaseDatasetStore",
    "SupabaseResearchJobQueue",
    "SupabaseResearchJobStore",
    "SupabaseWorkspaceMembershipResolver",
    "TenantContext",
    "UsagePolicy",
]
