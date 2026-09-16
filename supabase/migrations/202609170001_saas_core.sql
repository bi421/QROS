-- QROS SaaS core schema.
-- Tenant identity is derived from auth.uid(); request payloads never select a workspace.

create extension if not exists pgcrypto;

create table if not exists public.workspace (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(trim(name)) > 0),
    created_at timestamptz not null default now()
);

create table if not exists public.workspace_member (
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null check (role in ('owner','admin','researcher','viewer')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create table if not exists public.subscription (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null unique references public.workspace(id) on delete cascade,
    plan text not null check (plan in ('free','pro','team','enterprise')),
    status text not null check (status in ('trialing','active','past_due','cancelled','incomplete')),
    provider text,
    provider_customer_id text,
    provider_subscription_id text,
    current_period_end timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.dataset (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    name text not null check (length(trim(name)) > 0),
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now()
);

create table if not exists public.dataset_version (
    id uuid primary key default gen_random_uuid(),
    dataset_id uuid not null references public.dataset(id) on delete cascade,
    version_no integer not null check (version_no > 0),
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    storage_path text not null,
    byte_size bigint not null check (byte_size >= 0),
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now(),
    unique (dataset_id, version_no),
    unique (dataset_id, content_sha256)
);

create table if not exists public.research_run (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    dataset_version_id uuid not null references public.dataset_version(id),
    workflow_id text not null,
    status text not null check (status in ('queued','running','succeeded','failed','cancelled')),
    attempt_count integer not null default 0 check (attempt_count >= 0),
    error_code text,
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now(),
    started_at timestamptz,
    finished_at timestamptz
);

create table if not exists public.artifact (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    research_run_id uuid not null references public.research_run(id) on delete cascade,
    kind text not null,
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    storage_path text not null,
    byte_size bigint not null check (byte_size >= 0),
    created_at timestamptz not null default now(),
    unique (research_run_id, content_sha256)
);

create table if not exists public.evidence (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    research_run_id uuid not null references public.research_run(id) on delete cascade,
    artifact_id uuid references public.artifact(id),
    claim text not null check (length(trim(claim)) > 0),
    status text not null check (status in ('proven','rejected','inconclusive','unverified')),
    provenance jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.usage_event (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    user_id uuid references auth.users(id),
    event_type text not null,
    quantity bigint not null default 1 check (quantity > 0),
    research_run_id uuid references public.research_run(id),
    created_at timestamptz not null default now()
);

create table if not exists public.audit_log (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid references public.workspace(id) on delete cascade,
    user_id uuid references auth.users(id),
    action text not null,
    resource_type text,
    resource_id uuid,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_workspace_member_user on public.workspace_member(user_id, workspace_id);
create index if not exists idx_dataset_workspace on public.dataset(workspace_id, created_at desc);
create index if not exists idx_research_run_workspace_created on public.research_run(workspace_id, created_at desc);
create index if not exists idx_research_run_active on public.research_run(workspace_id, status) where status in ('queued','running');
create index if not exists idx_artifact_run on public.artifact(research_run_id);
create index if not exists idx_evidence_run on public.evidence(research_run_id);
create index if not exists idx_usage_workspace_created on public.usage_event(workspace_id, created_at desc);

create or replace function public.is_workspace_member(target_workspace uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select exists (
        select 1
        from public.workspace_member wm
        where wm.workspace_id = target_workspace
          and wm.user_id = auth.uid()
    );
$$;

revoke all on function public.is_workspace_member(uuid) from public;
grant execute on function public.is_workspace_member(uuid) to authenticated;

alter table public.workspace enable row level security;
alter table public.workspace_member enable row level security;
alter table public.subscription enable row level security;
alter table public.dataset enable row level security;
alter table public.dataset_version enable row level security;
alter table public.research_run enable row level security;
alter table public.artifact enable row level security;
alter table public.evidence enable row level security;
alter table public.usage_event enable row level security;
alter table public.audit_log enable row level security;

create policy workspace_member_select on public.workspace
for select to authenticated using (public.is_workspace_member(id));

create policy workspace_member_self_select on public.workspace_member
for select to authenticated using (user_id = auth.uid() or public.is_workspace_member(workspace_id));

create policy subscription_member_select on public.subscription
for select to authenticated using (public.is_workspace_member(workspace_id));

create policy dataset_member_all on public.dataset
for all to authenticated using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));

create policy dataset_version_member_all on public.dataset_version
for all to authenticated using (
    exists (select 1 from public.dataset d where d.id = dataset_id and public.is_workspace_member(d.workspace_id))
) with check (
    exists (select 1 from public.dataset d where d.id = dataset_id and public.is_workspace_member(d.workspace_id))
);

create policy research_run_member_all on public.research_run
for all to authenticated using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));

create policy artifact_member_all on public.artifact
for all to authenticated using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));

create policy evidence_member_all on public.evidence
for all to authenticated using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));

create policy usage_event_member_select on public.usage_event
for select to authenticated using (public.is_workspace_member(workspace_id));

create policy audit_log_member_select on public.audit_log
for select to authenticated using (public.is_workspace_member(workspace_id));

comment on table public.dataset_version is 'Immutable dataset version. Application must never mutate content_sha256 or storage_path after creation.';
comment on table public.research_run is 'Tenant-scoped asynchronous scientific execution record; completion does not imply a positive finding.';
comment on table public.evidence is 'Persisted evidence linked to a research run and provenance; scientific status remains evidence-derived.';
