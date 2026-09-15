# ResearchOS SaaS database contract

**Target:** Supabase Postgres
**Status:** Schema contract; executable migration must be generated with the Supabase CLI when the project is connected.

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
  workspace_id uuid PK FK workspace
  provider text
  provider_customer_id text
  provider_subscription_id text UNIQUE
  plan text
  status text
  current_period_end timestamptz

research_dataset
  id uuid PK
  workspace_id uuid FK workspace
  name text
  asset text
  timeframe text
  created_at timestamptz

research_dataset_version
  id uuid PK
  dataset_id uuid FK research_dataset
  workspace_id uuid FK workspace
  object_path text UNIQUE
  content_sha256 text
  rows_sha256 text
  row_count bigint
  created_at timestamptz

research_run
  id uuid PK
  workspace_id uuid FK workspace
  dataset_version_id uuid FK research_dataset_version
  workflow_id text
  status text
  created_at timestamptz
  started_at timestamptz
  finished_at timestamptz
  error_code text
  error_message text

research_artifact
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  kind text
  object_path text
  content_sha256 text
  created_at timestamptz

research_evidence
  id uuid PK
  workspace_id uuid FK workspace
  research_run_id uuid FK research_run
  evidence_json jsonb
  content_sha256 text
  created_at timestamptz

audit_event
  id bigint generated always as identity PK
  workspace_id uuid FK workspace
  actor_user_id uuid FK auth.users
  event_type text
  resource_type text
  resource_id uuid
  payload jsonb
  created_at timestamptz
```

## Tenant isolation contract

Every table containing customer-owned data has `workspace_id`. Every exposed table has RLS enabled. Policies must resolve authorization through `workspace_member` rather than trusting request-body workspace IDs or user-editable profile metadata.

Canonical policy shape:

```sql
using (
  exists (
    select 1
    from public.workspace_member wm
    where wm.workspace_id = <table>.workspace_id
      and wm.user_id = (select auth.uid())
  )
)
```

For writes, the corresponding `with check` predicate is required. UPDATE policies must have both `using` and `with check`.

## Storage contract

Use a private bucket for customer research data. Object paths are immutable and include the workspace and dataset version:

```text
research/{workspace_id}/{dataset_id}/{dataset_version_id}/source.csv
research/{workspace_id}/{research_run_id}/{artifact_id}.json
```

Never overwrite a scientific source object. A new upload creates a new dataset version. Large uploads should use resumable/signed upload flows rather than buffering the full object in the API process.

## Queue contract

Use a durable Supabase Queue backed by `pgmq` for `research-runs`. The queue message contains only identifiers:

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
