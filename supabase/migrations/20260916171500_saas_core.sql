-- ResearchOS SaaS core persistence and tenant isolation.
-- Scientific/research calculations remain outside this schema.

create extension if not exists pgcrypto;

create schema if not exists private;

create table if not exists public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(trim(name)) between 1 and 200),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('owner', 'admin', 'member', 'viewer')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create index if not exists idx_workspace_members_user
    on public.workspace_members(user_id, workspace_id);

create table if not exists public.datasets (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    external_id text not null,
    name text not null check (length(trim(name)) between 1 and 200),
    size_bytes bigint not null default 0 check (size_bytes >= 0),
    content_sha256 text,
    storage_path text,
    created_at timestamptz not null default now(),
    unique (workspace_id, external_id)
);

create index if not exists idx_datasets_workspace
    on public.datasets(workspace_id, created_at desc);

create table if not exists public.research_runs (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    dataset_id uuid not null references public.datasets(id) on delete restrict,
    workflow_id text not null,
    status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    input_sha256 text,
    software_version text,
    result_artifact_id uuid,
    error_code text,
    error_message text,
    created_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz
);

create index if not exists idx_research_runs_workspace_created
    on public.research_runs(workspace_id, created_at desc);
create index if not exists idx_research_runs_workspace_status
    on public.research_runs(workspace_id, status);

create table if not exists public.research_artifacts (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    research_run_id uuid not null references public.research_runs(id) on delete cascade,
    storage_path text not null,
    content_sha256 text not null,
    content_type text not null,
    size_bytes bigint not null check (size_bytes >= 0),
    created_at timestamptz not null default now(),
    unique (workspace_id, content_sha256)
);

create index if not exists idx_research_artifacts_run
    on public.research_artifacts(research_run_id);

alter table public.research_runs
    add constraint fk_research_run_result_artifact
    foreign key (result_artifact_id)
    references public.research_artifacts(id)
    on delete set null;

create table if not exists public.usage_ledger (
    id bigint generated always as identity primary key,
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    period_start date not null,
    metric text not null,
    quantity bigint not null check (quantity >= 0),
    source_id uuid,
    created_at timestamptz not null default now()
);

create index if not exists idx_usage_ledger_workspace_period
    on public.usage_ledger(workspace_id, period_start, metric);

create table if not exists public.idempotency_keys (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    key text not null check (length(trim(key)) between 8 and 200),
    request_hash text not null,
    response_status integer,
    response_body jsonb,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    primary key (workspace_id, key)
);

create index if not exists idx_idempotency_expiry
    on public.idempotency_keys(expires_at);

create table if not exists public.audit_events (
    id bigint generated always as identity primary key,
    workspace_id uuid references public.workspaces(id) on delete cascade,
    user_id uuid references auth.users(id) on delete set null,
    event_type text not null,
    request_id text,
    resource_type text,
    resource_id uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_audit_events_workspace_created
    on public.audit_events(workspace_id, created_at desc);

create table if not exists public.billing_customers (
    workspace_id uuid primary key references public.workspaces(id) on delete cascade,
    provider text not null,
    customer_id text not null unique,
    created_at timestamptz not null default now()
);

create table if not exists public.billing_subscriptions (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    provider text not null,
    provider_subscription_id text not null unique,
    plan text not null check (plan in ('free', 'pro', 'team', 'enterprise')),
    status text not null,
    current_period_start timestamptz,
    current_period_end timestamptz,
    cancel_at_period_end boolean not null default false,
    updated_at timestamptz not null default now()
);

create index if not exists idx_billing_subscriptions_workspace
    on public.billing_subscriptions(workspace_id);

-- Private authorization helpers. They intentionally use a fixed search_path and
-- are not exposed through the Data API.
create or replace function private.is_workspace_member(target_workspace uuid)
returns boolean
language sql
security definer
set search_path = public, pg_temp
stable
as $$
    select exists (
        select 1
        from public.workspace_members wm
        where wm.workspace_id = target_workspace
          and wm.user_id = auth.uid()
    );
$$;

create or replace function private.has_workspace_role(target_workspace uuid, allowed_roles text[])
returns boolean
language sql
security definer
set search_path = public, pg_temp
stable
as $$
    select exists (
        select 1
        from public.workspace_members wm
        where wm.workspace_id = target_workspace
          and wm.user_id = auth.uid()
          and wm.role = any(allowed_roles)
    );
$$;

revoke all on function private.is_workspace_member(uuid) from public, anon;
revoke all on function private.has_workspace_role(uuid, text[]) from public, anon;
grant execute on function private.is_workspace_member(uuid) to authenticated;
grant execute on function private.has_workspace_role(uuid, text[]) to authenticated;

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.datasets enable row level security;
alter table public.research_runs enable row level security;
alter table public.research_artifacts enable row level security;
alter table public.usage_ledger enable row level security;
alter table public.idempotency_keys enable row level security;
alter table public.audit_events enable row level security;
alter table public.billing_customers enable row level security;
alter table public.billing_subscriptions enable row level security;

create policy workspaces_select_member on public.workspaces
    for select to authenticated
    using (private.is_workspace_member(id));

create policy workspaces_update_admin on public.workspaces
    for update to authenticated
    using (private.has_workspace_role(id, array['owner', 'admin']))
    with check (private.has_workspace_role(id, array['owner', 'admin']));

create policy workspace_members_select_member on public.workspace_members
    for select to authenticated
    using (private.is_workspace_member(workspace_id));

create policy workspace_members_insert_admin on public.workspace_members
    for insert to authenticated
    with check (private.has_workspace_role(workspace_id, array['owner', 'admin']));

create policy workspace_members_update_admin on public.workspace_members
    for update to authenticated
    using (private.has_workspace_role(workspace_id, array['owner', 'admin']))
    with check (private.has_workspace_role(workspace_id, array['owner', 'admin']));

create policy workspace_members_delete_admin on public.workspace_members
    for delete to authenticated
    using (private.has_workspace_role(workspace_id, array['owner', 'admin']));

create policy datasets_member_all on public.datasets
    for all to authenticated
    using (private.is_workspace_member(workspace_id))
    with check (private.is_workspace_member(workspace_id));

create policy research_runs_member_all on public.research_runs
    for all to authenticated
    using (private.is_workspace_member(workspace_id))
    with check (private.is_workspace_member(workspace_id));

create policy research_artifacts_member_all on public.research_artifacts
    for all to authenticated
    using (private.is_workspace_member(workspace_id))
    with check (private.is_workspace_member(workspace_id));

create policy usage_ledger_member_select on public.usage_ledger
    for select to authenticated
    using (private.is_workspace_member(workspace_id));

create policy idempotency_keys_member_all on public.idempotency_keys
    for all to authenticated
    using (private.is_workspace_member(workspace_id))
    with check (private.is_workspace_member(workspace_id));

create policy audit_events_member_select on public.audit_events
    for select to authenticated
    using (workspace_id is null or private.is_workspace_member(workspace_id));

create policy billing_customers_member_select on public.billing_customers
    for select to authenticated
    using (private.is_workspace_member(workspace_id));

create policy billing_subscriptions_member_select on public.billing_subscriptions
    for select to authenticated
    using (private.is_workspace_member(workspace_id));

comment on schema private is 'Internal ResearchOS authorization helpers; not exposed through the Data API.';
comment on table public.research_runs is 'Tenant-scoped research execution records; scientific semantics remain in ResearchOS core.';
