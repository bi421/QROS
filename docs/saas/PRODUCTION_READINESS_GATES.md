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

## Not yet verified

These remain release blockers until executed against a real staging/production environment:

1. Target-environment migration execution and schema compatibility.
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
