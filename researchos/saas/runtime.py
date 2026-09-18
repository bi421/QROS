"""Production composition root for QROS SaaS."""
from __future__ import annotations
import os
from supabase import create_client
from researchos.saas.api import create_app
from researchos.saas.supabase_auth import SupabaseJwtAuthProvider
from researchos.saas.supabase_membership import SupabaseWorkspaceMembershipResolver
from researchos.saas.datasets import SupabaseDatasetStorage, SupabaseDatasetStore
from researchos.saas.queue import SupabaseResearchJobQueue
from researchos.saas.supabase_job_store import SupabaseResearchJobStore
from researchos.saas.idempotency import SupabaseIdempotencyStore
from researchos.saas.billing import SupabaseBillingEventStore
from researchos.saas.rate_limit import SupabaseRateLimiter

def build_production_app():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)
    membership = SupabaseWorkspaceMembershipResolver(client)
    auth = SupabaseJwtAuthProvider(client, membership)
    return create_app(
        auth_provider=auth,
        job_store=SupabaseResearchJobStore(client),
        dataset_store=SupabaseDatasetStore(client),
        dataset_storage=SupabaseDatasetStorage(client),
        job_queue=SupabaseResearchJobQueue(client),
        idempotency_store=SupabaseIdempotencyStore(client),
        billing_store=SupabaseBillingEventStore(client),
        billing_webhook_secret=os.environ.get("BILLING_WEBHOOK_SECRET"),
        rate_limiter=SupabaseRateLimiter(client, limit=120, window_seconds=60),
    )

app = build_production_app()
