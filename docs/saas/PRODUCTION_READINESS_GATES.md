# Production Readiness Gates

This document records the current executable release gates for QROS SaaS.

## Verified on main

- FastAPI production composition exists at `researchos.saas.runtime:app`.
- Supabase is the canonical persistence and migration authority.
- `supabase/migrations/` is version-controlled and validated in CI.
- Production Docker image builds in CI.
- Docker Compose provides a local container wrapper.
- `/healthz` and `/readyz` are defined.
- Authentication, tenant-scoped persistence, durable jobs, claims, evidence, billing, and request-correlation contracts have automated coverage.

## Production schema parity gate

The repository includes `.github/workflows/production-schema-parity.yml`. It is a manual, production-environment workflow and is intentionally non-destructive: it links to the configured production project, lists remote migration history, runs `supabase db push --linked --dry-run`, verifies required durable objects, and checks RLS on the QROS tenant/server tables. It requires the repository's production GitHub environment to provide `SUPABASE_ACCESS_TOKEN`, `PRODUCTION_DB_PASSWORD`, and `PRODUCTION_PROJECT_ID`.

The gate must report **up to date** before a release can be called migration-compatible. A dry-run that reports pending migrations is a release blocker; it must not be bypassed by manually applying SQL outside migration history.

## Current production audit — 2026-09-21

The production project was independently queried during hardening. The observed migration-history drift was repaired to the repository's canonical versions, and the durable `public.research_claim` and `public.audit_event` objects were restored using their existing repository migrations.

The authoritative Supabase session boundary is now also implemented and applied as migration `202609210001_saas_auth_session_revocation`. The production RPC `public.qros_session_is_active(uuid,uuid)` checks the JWT `session_id` against `auth.sessions` for the authenticated user. Direct verification confirmed: `service_role` has EXECUTE, `anon` and `authenticated` do not; the function is SECURITY DEFINER with an empty search path; and an unknown session returns false.

The application production composition wires this validator into `SupabaseJwtAuthProvider`, so a revoked/missing session is rejected with 401 and a session-store validation outage fails closed with 503. PR #133 exact-head CI and Supabase Database Security Tests are green, and the change is merged to main.

The current Supabase Security Advisor reports one Auth configuration warning: leaked-password protection is disabled. This is a separate Auth hardening item and is not treated as resolved by repository code.

## Not yet verified

These remain release blockers until executed against a real staging/production environment:

1. Target-environment migration execution and schema compatibility through the release workflow.
2. Real JWT authentication against the target Supabase project.
3. Cross-workspace isolation against the target database.
4. Dataset upload/version/download against durable storage.
5. Research job enqueue/worker execution/result persistence.
6. Claim and evidence persistence in the target environment.
7. Billing webhook delivery with a real provider.
8. Backup/restore exercise.
9. Queue/job recovery exercise.
10. Production deployment and exact-release smoke test.

A passing container build is not a deployment.

## Release rule

Do not mark production-ready from repository tests alone. The exact release commit must have CI success and an observed end-to-end workflow in the target environment.
