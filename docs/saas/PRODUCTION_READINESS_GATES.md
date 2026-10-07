# Production Readiness Gates

This document records the current executable release gates for QROS SaaS.

## Verified on main

- FastAPI production composition exists at `researchos.saas.runtime:create_production_app` via Uvicorn `--factory`.
- Supabase is the canonical persistence and migration authority.
- `supabase/migrations/` is version-controlled and validated in CI.
- Production Docker image builds in CI.
- Docker Compose provides a local container wrapper.
- `/healthz` and `/readyz` are defined.
- Authentication, tenant-scoped persistence, durable jobs, claims, evidence, billing, and request-correlation contracts have automated coverage.

## Production schema parity gate

The repository includes `.github/workflows/production-schema-parity.yml`. It is a manual, production-environment workflow and is intentionally non-destructive: it links to the configured production project, lists remote migration history, runs `supabase db push --linked --dry-run`, verifies required durable objects, and checks RLS on the QROS tenant/server tables. It requires the repository's production GitHub environment to provide `SUPABASE_ACCESS_TOKEN`, `PRODUCTION_DB_PASSWORD`, and `PRODUCTION_PROJECT_ID`.

The gate must report **up to date** before a release can be called migration-compatible. A dry-run that reports pending migrations is a release blocker; it must not be bypassed by manually applying SQL outside migration history.

## Divergent-history forward migration gate

Production migration history may contain legacy live-only entries that are not present in the repository. The repository must not repair, delete, rename, or recreate those historical entries as part of a forward deployment.

The governed forward-only reconciliation path is `.github/workflows/production-forward-migration.yml`. The workflow is manual, protected by the `production` Environment, and accepts only the explicitly allowlisted M1 reconciliation migrations. It creates a temporary Supabase CLI workdir containing exactly one selected migration file, verifies the target project ref, runs `supabase db push --linked --include-all --dry-run`, and refuses to continue unless exactly that migration is the only pending item in the isolated bundle. An apply requires the explicit `APPLY` confirmation input.

This controlled use of `--include-all` is intentionally different from running `supabase db push --include-all` against the full repository: the isolated bundle prevents unrelated repository-only migrations from being selected. Supabase documents `--include-all` as applying migrations not found in the remote history table. The CLI records applied migration versions in the remote migration history, preserving the selected file's timestamp rather than creating a server-generated version.

The Supabase Management API `POST /v1/projects/{ref}/database/migrations` is not the QROS production transport for these repository migrations. That endpoint creates a migration with a server-generated version and therefore cannot be used here to preserve the exact repository migration timestamp. This avoids creating new remote-only history entries.

## Current migration ledger recheck — 2026-09-30

A fresh read-only recheck against the current repository and target projects found a
new repository-to-environment delta after the earlier staging baseline:

- Repository `supabase/migrations/`: **48** canonical SQL files.
- Staging: **45** migration rows.
- Staging contains execution version `20260928103556` for the worker migration, but
  the remote display name remains the historical
  `20260928103225_saas_worker_queue_consumer`; this is preserved and not rewritten.
- Staging does not yet contain the three newer reconciliation migrations:
  `20260928120000_storage_authorization_workspace_membership_reconciliation.sql`,
  `20260928123000_dataset_version_storage_path_reconciliation.sql`, and
  `20260928124500_workspace_billing_admin_role_reconciliation.sql`.
- Production has since advanced beyond that older snapshot and now reports a live
  execution entry `20261007035414` named
  `202610060001_production_forward_reconciliation`, corresponding to the repository
  migration `supabase/migrations/202610060001_production_forward_reconciliation.sql`.
  This current production fact supersedes the older statement that production had not
  received the forward reconciliation.

The 2026-09-30 staging delta remains open: staging still lacks the three reconciliation
migrations above. The production execution fact is recorded separately from workflow
authorization/evidence; this document does not infer that a governed workflow run
occurred from the database history alone. The governed forward-migration workflow
remains the repository's authorized transport path.

## Current migration ledger state — 2026-09-28

The current production project contains seven live-only migration-history entries after `202609210001`. This later audit supersedes the older 2026-09-21 parity snapshot below. The historical entries are retained as historical evidence and must not be reconstructed or repaired as part of the current forward deployment.

Production forward reconciliation is governed by `.github/workflows/production-forward-migration.yml`; the workflow does not attempt to make the full repository history equal to the live history.

## Historical production audit — 2026-09-21

The production project was independently queried during hardening. The observed migration-history drift was repaired to the repository's canonical versions, and the durable `public.research_claim` and `public.audit_event` objects were restored using their existing repository migrations.

The authoritative Supabase session boundary is now also implemented and applied as migration `202609210001_saas_auth_session_revocation`. The production RPC `public.qros_session_is_active(uuid,uuid)` checks the JWT `session_id` against `auth.sessions` for the authenticated user. Direct verification confirmed: `service_role` has EXECUTE, `anon` and `authenticated` do not; the function is SECURITY DEFINER with an empty search path; and an unknown session returns false.

The application production composition wires this validator into `SupabaseJwtAuthProvider`, so a revoked/missing session is rejected with 401 and a session-store validation outage fails closed with 503. PR #133 exact-head CI and Supabase Database Security Tests are green, and the change is merged to main.

### Migration-version parity recheck — 2026-09-21

A fresh production migration-history query was compared against the 37 versioned SQL migrations on `main`. After repairing the production history entries for the already-present rate-limit cleanup, result client-grant deny, content-addressed artifact, and auth-session migrations, the version sets are now exactly equal: **37 repository versions / 37 production versions / 0 missing / 0 extra**.

The production database was also directly verified for the content-addressed artifact boundary: `public.artifact` has the `artifact_content_addressed_path` check constraint and `idx_artifact_workspace_content_sha256` unique index. The existing artifact table contained zero rows at the time of verification, so the migration's duplicate/non-canonical preconditions were satisfied before enforcement.

The remaining production migration names for four historical entries use shorter labels than the repository filenames, but their migration versions are identical; release parity is therefore tracked by the canonical migration version set, not by display-name text.

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

## Legacy public-table access audit — 2026-10-07

A direct production schema/security recheck reviewed the nine legacy public tables that have RLS disabled: `User`, `Like`, `Dislike`, `Referral`, `users`, `avatars`, `albums`, `album_consents`, and `face_embeddings`.

Observed on production project `pvhdsngxyoiqhqwujfjt`:

- RLS is disabled on all nine legacy tables.
- Current approximate row count is **0 on all nine tables**.
- The current Supabase Security Advisor does **not** report these nine tables as an active security finding.
- The current Security Advisor findings are limited to two intentional QROS server-only tables with RLS enabled and no policies, plus the separate Auth leaked-password-protection warning.
- No production mutation was performed.

Conclusion: the nine tables remain legacy schema-hardening debt, but the current evidence does not justify calling them an exposed Data API surface or blindly enabling RLS without first identifying a legitimate legacy application access contract. Any future RLS enablement must establish explicit policies and preserve that contract.

