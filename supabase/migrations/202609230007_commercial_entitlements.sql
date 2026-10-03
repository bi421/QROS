create table if not exists public.entitlement (
    tenant_id uuid primary key references public.workspace(id) on delete cascade,
    plan text not null check (plan in ('free', 'pro', 'enterprise')),
    max_datasets bigint not null check (max_datasets >= 0),
    max_jobs_per_month bigint not null check (max_jobs_per_month >= 0),
    max_storage_mb bigint not null check (max_storage_mb >= 0),
    updated_at timestamptz not null default now()
);

alter table public.entitlement enable row level security;
revoke all on table public.entitlement from anon, authenticated;

create policy entitlement_no_client_access
on public.entitlement
for all
to anon, authenticated
using (false)
with check (false);

create index if not exists entitlement_plan_idx
on public.entitlement (plan);

insert into public.entitlement (
    tenant_id, plan, max_datasets, max_jobs_per_month, max_storage_mb
)
select
    w.id,
    case
        when s.plan in ('free', 'pro', 'enterprise') then s.plan
        else 'free'
    end,
    case when s.plan = 'pro' then 1000 when s.plan = 'enterprise' then 0 else 10 end,
    case when s.plan = 'pro' then 1000 when s.plan = 'enterprise' then 0 else 100 end,
    case when s.plan = 'pro' then 10240 when s.plan = 'enterprise' then 0 else 1024 end
from public.workspace w
left join public.subscription s on s.workspace_id = w.id
on conflict (tenant_id) do nothing;

comment on table public.entitlement is 'Server-authoritative commercial entitlements for tenant-scoped API enforcement.';
