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
  role text CHECK (owner|admin|researcher|viewer|billing)
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
  CHECK storage_path follows tenant/{tenant_id}/datasets/{sha256(content)}/{version}/

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

research_finding
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  validation_id uuid FK research_validation
  finding_sha256 text
  status text
  payload jsonb
  contract_version text
  created_at timestamptz
  deleted_at timestamptz nullable

audit_log
  id uuid PK
  workspace_id uuid FK workspace
  user_id uuid FK auth.users
  action text
  resource_type text
  resource_id uuid
  metadata jsonb
  created_at timestamptz

dataset_version_feed
  dataset_version_id uuid FK dataset_version
  experiment_id text
  created_at timestamptz
  PK (dataset_version_id, experiment_id)
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

Content is identified by lowercase SHA-256 and duplicate content is deduplicated per dataset. The API hashes the upload before persistence, writes only to the canonical immutable path, then re-reads the stored object and verifies its SHA-256 before recording the version. If identical content already exists, the existing version/path is returned; a concurrent duplicate is reconciled to that same existing version rather than creating a second object.

## Storage contract

The `qros-datasets` bucket is private. Server-side code uses the privileged Supabase client; browser code never receives service-role/secret credentials.

Canonical object path contract:

```text
tenant/{tenant_id}/datasets/{sha256(content)}/{version}/
```

The path is immutable and content-addressed. `tenant_id` is the authenticated workspace/tenant identifier. The canonical path is exactly `tenant/{tenant_id}/datasets/{sha256(content)}/{version}/`; the database validates that the path tenant matches the dataset workspace and that the path digest matches `content_sha256`. Upload computes SHA-256 and byte size before persistence, verifies the persisted bytes again, and never overwrites an existing object. Download verifies the stored object SHA-256 against `dataset_version.content_sha256` before issuing a signed URL.

Dataset versions are append-only. Updating a dataset means creating a new version; the previous version remains readable and its storage object is never overwritten or deleted by an update. Version numbers are unique per dataset and immutable.

`dataset_version_feed` records the immutable lineage edge from a dataset version to an Experiment identifier, exposed by `DatasetVersion.feeds`. Finding retention is enforced by a database trigger: a dataset cannot be deleted while a non-deleted `research_finding` references a research run backed by one of its versions. The API maps this condition to HTTP `409` with the stable message/code `DATASET_REFERENCED`.

Supabase recommends resumable/TUS upload flows for large files; those will replace the current server-side multipart path before large-plan production rollout.

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
