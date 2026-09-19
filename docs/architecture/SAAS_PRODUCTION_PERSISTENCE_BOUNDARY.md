# SaaS Production Persistence Boundary

## Purpose

QROS has two separate persistence concerns.

1. SaaS operational state: tenant workspaces, memberships, datasets, research runs, idempotency, billing events, rate limits, worker leases, and research-run result provenance.
2. Research-domain storage: reusable research/evidence/claim libraries used by offline research components.

## Production rule

researchos/saas/runtime.py is the production composition root. It must explicitly wire durable Supabase-backed adapters for every SaaS operational dependency. In-memory implementations are test doubles only.

The production composition root currently uses SupabaseJwtAuthProvider, SupabaseWorkspaceMembershipResolver, SupabaseResearchJobStore, SupabaseDatasetStore, SupabaseDatasetStorage, SupabaseResearchJobQueue, SupabaseIdempotencyStore, SupabaseBillingEventStore, and SupabaseRateLimiter.

create_app() may retain in-memory defaults because unit and local contract tests intentionally use them. Those defaults must never become the production composition root.

## Important boundary

The legacy ResearchRepository and EvidenceRepository are not yet multi-tenant Supabase SaaS services. ResearchClaim now has a dedicated tenant-scoped durable Supabase persistence adapter, but it is not yet exposed as a customer-facing API resource. Claims/evidence must not be treated as SaaS resources until the API boundary, authorization policy, and integration tests are implemented.

## Regression rule

Any future production runtime change that replaces a Supabase adapter with an InMemory implementation must fail the architecture test before merge.
