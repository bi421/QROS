"""Production composition root for QROS SaaS."""
from __future__ import annotations

import os


from supabase import create_client
from fastapi import FastAPI

from researchos.saas.api import create_app
from researchos.saas.contracts import Plan
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
from researchos.saas.billing import SupabaseBillingEventStore, SupabaseEntitlementStore, StripeBillingProvider
from researchos.saas.rate_limit import SupabaseRateLimiter
from researchos.saas.workspace import SupabaseWorkspaceProvisioner
from researchos.saas.persistence import SupabaseTenantPersistence


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

    stripe_secret = os.environ.get("STRIPE_SECRET_KEY")
    public_base_url = os.environ.get("QROS_PUBLIC_BASE_URL")
    billing_webhook_secret = os.environ.get("BILLING_WEBHOOK_SECRET")
    stripe_prices = {
        Plan.PRO.value: os.environ.get("STRIPE_PRICE_PRO", ""),
        Plan.TEAM.value: os.environ.get("STRIPE_PRICE_TEAM", ""),
        Plan.ENTERPRISE.value: os.environ.get("STRIPE_PRICE_ENTERPRISE", ""),
    }
    billing_plan_by_price_id = {
        price_id: plan for plan, price_id in stripe_prices.items() if price_id
    }
    billing_provider = None
    if (
        stripe_secret
        and public_base_url
        and billing_webhook_secret
        and all(stripe_prices.values())
    ):
        billing_provider = StripeBillingProvider(
            secret_key=stripe_secret,
            public_base_url=public_base_url,
            price_ids=stripe_prices,
        )

    return create_app(
        auth_provider=auth,
        job_store=SupabaseResearchJobStore(client),
        dataset_store=SupabaseDatasetStore(client),
        dataset_storage=SupabaseDatasetStorage(client),
        job_queue=SupabaseResearchJobQueue(client),
        idempotency_store=SupabaseIdempotencyStore(client),
        claim_store=SupabaseResearchClaimStore(client),
        evidence_store=SupabaseResearchEvidenceStore(client),
        validation_store=SupabaseResearchValidationStore(client),
        finding_store=SupabaseResearchFindingStore(client),
        billing_store=SupabaseBillingEventStore(client),
        billing_provider=billing_provider,
        billing_plan_by_price_id=billing_plan_by_price_id,
        entitlement_store=SupabaseEntitlementStore(client),
        plan_rate_limiters={
            Plan.FREE: SupabaseRateLimiter(client, limit=100, window_seconds=60),
            Plan.PRO: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
            Plan.TEAM: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
            Plan.ENTERPRISE: SupabaseRateLimiter(client, limit=1000, window_seconds=60),
        },
        billing_webhook_secret=billing_webhook_secret,
        metrics_token=os.environ.get("QROS_METRICS_TOKEN"),
        rate_limiter=SupabaseRateLimiter(client, limit=120, window_seconds=60),
        readiness_probe=readiness_probe,
        workspace_provisioner=SupabaseWorkspaceProvisioner(client),
        tenant_persistence=SupabaseTenantPersistence(client),
        supabase_url=url,
        supabase_publishable_key=os.environ.get("SUPABASE_PUBLISHABLE_KEY"),
    )


# Uvicorn loads this factory with --factory so importing this module performs no
# production configuration, network connection, or secret lookup.
create_production_app = build_production_app

__all__ = ["build_production_app", "create_production_app"]
