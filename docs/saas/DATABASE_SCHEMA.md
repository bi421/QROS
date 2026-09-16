# QROS SaaS database contract

**Target:** Supabase Postgres 17  
**Status:** Implemented by migrations `202609170001_saas_core` through `202609170005_saas_fk_indexes` and verified on the active Supabase project.

## Tables

```text
dataset_version
  id uuid PK
  dataset_id uuid FK dataset
  version_no integer
  content_sha256 text
  storage_path text
  byte_size bigint
  created_by uuid FK auth.users
  created_at timestamptz
  UNIQUE (dataset_id, version_no)
  UNIQUE (dataset_id, content_sha256)
```

The remaining SaaS tables are `workspace`, `workspace_member`, `subscription`, `dataset`, `research_run`, `artifact`, `evidence`, `usage_event`, and `audit_log`; their tenant relationships and constraints are defined by the migrations.

## Tenant isolation contract

Every customer-owned table has `workspace_id`, directly or through its parent relation. RLS is enabled on all SaaS tables. Authorization is resolved through `workspace_member`; request-body workspace identifiers are never trusted.

The server-side application uses the privileged Supabase client for writes and membership/subscription resolution. `anon` and `authenticated` have no table grants for these SaaS tables, so the browser cannot bypass the application API through PostgREST. RLS remains enabled as defense-in-depth.

The membership helper is `private.is_workspace_member(...)`, a `SECURITY DEFINER` function with a pinned empty `search_path`; it is not exposed in the public Data API.

Cross-resource policies additionally require research runs to reference a dataset version belonging to the same workspace, artifacts to reference runs in the same workspace, and evidence to reference matching runs/artifacts.

## Dataset immutability

`dataset_version` is append-only. PostgreSQL enforces two invariants:

1. `dataset_version_allocate_no` allocates the next `version_no` under a per-dataset transaction advisory lock.
2. `dataset_version_immutable` rejects UPDATE/DELETE operations that would mutate or remove a version.

Content is identified by lowercase SHA-256 and duplicate content is rejected per dataset. The API creates a new version and content-addressed object path rather than overwriting an existing scientific source.

## Storage contract

The `qros-datasets` bucket is private. Server-side code uses the privileged Supabase client; browser code never receives service-role/secret credentials.

Current object path contract:

```text
{workspace_id}/datasets/{dataset_id}/sha256/{sha256}
```

The API computes SHA-256 and byte size before persistence and removes an uploaded object if metadata persistence fails. Supabase recommends resumable/TUS upload flows for large files; those will replace the current server-side multipart path before large-plan production rollout.

## Queue contract

Use a durable Supabase Queue backed by `pgmq` for `research-runs`. Queue messages should contain identifiers only:

```json
{
  "research_run_id": "...",
  "workspace_id": "..."
}
```

The worker reloads the authoritative database record and verifies workspace ownership before reading storage or invoking the scientific core.

## Security constraints

- Never expose `service_role` or secret keys to browser code.
- Do not use `raw_user_meta_data` for authorization.
- Do not expose `pgmq` tables directly to clients.
- Keep queue messages free of credentials and raw dataset contents.
- Keep raw source files private.
- Preserve content hashes in the database and evidence artifacts.
- Treat subscription state as server-authoritative.
- Enable leaked-password protection in Supabase Auth before production auth rollout.
