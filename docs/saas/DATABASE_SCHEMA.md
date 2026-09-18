# QROS SaaS database contract

**Target:** Supabase Postgres 17  
**Status:** Implemented by migrations through `202609180020_saas_result_server_only` and verified on the active Supabase project.

## Tables

```text
workspace
  id uuid PK
  name text
  created_at timestamptz

workspace_member
  workspace_id uuid FK workspace
  user_id uuid FK auth.users
  role text CHECK (owner|admin|researcher|viewer)
  created_at timestamptz
  PK (workspace_id, user_id)

subscription
  id uuid PK
  workspace_id uuid UNIQUE FK workspace
  plan text CHECK (free|pro|team|enterprise)
  status text CHECK (trialing|active|past_due|cancelled|incomplete)
  provider text
  provider_customer_id text
  provider_subscription_id text
  current_period_end timestamptz
  created_at timestamptz
  updated_at timestamptz

dataset
  id uuid PK
  workspace_id uuid FK workspace
  name text
  created_by uuid FK auth.users
  created_at timestamptz

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

research_run
  id uuid PK
  workspace_id uuid FK workspace
  dataset_version_id uuid FK dataset_version
  workflow_id text
  status text CHECK (queued|running|succeeded|failed|cancelled)
  source_dataset_sha256 text
  attempt_count integer
  error_code text
  created_by uuid FK auth.users
  created_at timestamptz
  started_at timestamptz
  finished_at timestamptz

research_run_result
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid UNIQUE FK research_run
  source_dataset_sha256 text
  status text CHECK (SUCCEEDED|FAILED)
  manifest_sha256 text
  failures jsonb
  created_at timestamptz

research_run_artifact
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  artifact_id text
  kind text
  content_sha256 text
  created_at timestamptz
  UNIQUE (research_run_id, artifact_id)

artifact
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  kind text
  content_sha256 text
  storage_path text
  byte_size bigint
  created_at timestamptz
  UNIQUE (research_run_id, content_sha256)

evidence
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  artifact_id uuid FK artifact
  claim text
  status text CHECK (proven|rejected|inconclusive|unverified)
  provenance jsonb
  created_at timestamptz

usage_event
  id uuid PK
  workspace_id uuid FK workspace
  user_id uuid FK auth.users
  event_type text
  quantity bigint
  research_run_id uuid FK research_run
  created_at timestamptz

audit_log
  id uuid PK
  workspace_id uuid FK workspace
  user_id uuid FK auth.users
  action text
  resource_type text
  resource_id uuid
  metadata jsonb
  created_at timestamptz
```

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
