# QROS database migration policy

## Canonical system

QROS does **not** use Alembic. The canonical database schema is PostgreSQL on
Supabase, and schema evolution is version-controlled under
`supabase/migrations/`.

This avoids maintaining two independent migration authorities.

## Required migration rules

- Every schema change is a new timestamped SQL migration.
- Never edit an already-applied production migration in place.
- Use forward-only, reversible changes where practical.
- Destructive or irreversible production operations require an explicit
  release decision and backup/rollback plan.
- RLS and tenant-boundary changes must include regression coverage.
- CI must validate migration file integrity and repository text integrity.
- Production migration application must be verified against the target
  Supabase project before release.

## Current state

The repository already contains the SaaS core, worker lease/heartbeat,
idempotency, result provenance, tenant-boundary, and research-claim migration
series. Therefore adding an Alembic tree would create a second source of
truth and is intentionally rejected.
