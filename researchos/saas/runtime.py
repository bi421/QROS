"""Production composition root for QROS SaaS."""
from __future__ import annotations

import os


from supabase import create_client

from researchos.saas.api import create_app
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver
from researchos.saas.supabase_session import SupabaseSessionValidator
from researchos.saas.datasets import SupabaseDatasetStorage, SupabaseDatasetStore
from researchos.saas.queue import SupabaseResearchJobQueue
from researchos.saas.supabase_job_store import SupabaseResearchJobStore
from researchos.saas.supabase_claim_store import SupabaseResearchClaimStore
from researchos.saas.evidence_api import SupabaseResearchEvidenceStore
from researchos.saas.supabase_validation_store import SupabaseResearchValidationStore
from researchos.saas.supabase_finding_store import SupabaseResearchFindingStore
from researchos.saas.idempotency import SupabaseIdempotencyStore
from researchos.saas.billing import SupabaseBillingEventStore, SupabaseEntitlementStore
from researchos.saas.rate_limit import SupabaseRateLimiter
from researchos.saas.workspace import SupabaseWorkspaceProvisioner


def build_production_app() -> FastAPI:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)
    membership = SupabaseWorkspaceMembershipResolver(client)
    session_validator = SupabaseSessionValidator(client)
    auth = SupabaseJwtAuthProvider(
        client,
        membership,
        expected_issuer=f"{url.rstrip('/')}/auth/v1",
        session_validator=session_validator,
    )
    def readiness_probe() -> None:
        response = client.table("workspace").select("id").limit(1).execute()
        if response.data is None:
            raise RuntimeError("Supabase readiness query returned no data")

    return create_app(
        auth_provider=auth,
        job_store=SupabaseResearchJobStore(client),
        dataset_store=SupabaseDatasetStore(client),
        dataset_storage=SupabaseDatasetStorage(
            client,
            supabase_url=url,
            publishable_key=os.environ["SUPABASE_ANON_KEY"],
        ),
        job_queue=SupabaseResearchJobQueue(client),
        idempotency_store=SupabaseIdempotencyStore(client),
        claim_store=SupabaseResearchClaimStore(client),
        evidence_store=SupabaseResearchEvidenceStore(client),
        validation_store=SupabaseResearchValidationStore(client),
        finding_store=SupabaseResearchFindingStore(client),
        billing_store=SupabaseBillingEventStore(client),
        entitlement_store=SupabaseEntitlementStore(client),
        plan_rate_limiters={
            Plan.FREE: SupabaseRateLimiter(client, limit=100, window_seconds=60),
            Plan.PRO: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
            Plan.TEAM: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
            Plan.ENTERPRISE: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
        },
        billing_webhook_secret=os.environ.get("BILLING_WEBHOOK_SECRET"),
        metrics_token=os.environ.get("QROS_METRICS_TOKEN"),
        rate_limiter=SupabaseRateLimiter(client, limit=120, window_seconds=60),
        readiness_probe=readiness_probe,
        workspace_provisioner=SupabaseWorkspaceProvisioner(client),
        supabase_url=url,
        supabase_publishable_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY"),
    )


app = build_production_app()
