create table if not exists public.entitlements (
  tenant_id uuid primary key,
  plan text not null check (plan in ('free','pro','enterprise')),
  max_datasets integer not null check (max_datasets >= 0),
  max_jobs_per_month integer not null check (max_jobs_per_month >= 0),
  max_storage_mb integer not null check (max_storage_mb >= 0),
  max_members integer not null check (max_members >= 0),
  updated_at timestamptz not null default now()
);

insert into public.entitlements (tenant_id, plan, max_datasets, max_jobs_per_month, max_storage_mb, max_members)
select w.id, case when s.plan in ('pro','enterprise') then s.plan else 'free' end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 100 else 3 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 1000 else 100 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 102400 else 1024 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 50 else 5 end
from public.workspace w left join public.subscription s on s.workspace_id = w.id
on conflict (tenant_id) do nothing;

alter table public.entitlements enable row level security;
drop policy if exists tenant_select on public.entitlements;
drop policy if exists tenant_insert on public.entitlements;
drop policy if exists tenant_update on public.entitlements;
drop policy if exists tenant_delete on public.entitlements;
create policy tenant_select on public.entitlements for select to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text);
create policy tenant_insert on public.entitlements for insert to authenticated with check (auth.jwt() ->> 'tenant_id' = tenant_id::text);
create policy tenant_update on public.entitlements for update to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text) with check (auth.jwt() ->> 'tenant_id' = tenant_id::text);
create policy tenant_delete on public.entitlements for delete to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text);

alter table public.workspace add column if not exists deleted_at timestamptz;
alter table public.workspace_member add column if not exists deleted_at timestamptz;
alter table public.subscription add column if not exists deleted_at timestamptz;
alter table public.dataset add column if not exists deleted_at timestamptz;
alter table public.dataset_version add column if not exists deleted_at timestamptz;
alter table public.research_run add column if not exists deleted_at timestamptz;
alter table public.artifact add column if not exists deleted_at timestamptz;
alter table public.evidence add column if not exists deleted_at timestamptz;
alter table public.usage_event add column if not exists deleted_at timestamptz;
alter table public.audit_log add column if not exists deleted_at timestamptz;
alter table public.billing_event add column if not exists deleted_at timestamptz;
alter table public.api_idempotency add column if not exists deleted_at timestamptz;
alter table public.research_claim add column if not exists deleted_at timestamptz;
alter table public.research_validation add column if not exists deleted_at timestamptz;
alter table public.research_finding add column if not exists deleted_at timestamptz;
alter table public.research_run_result add column if not exists deleted_at timestamptz;
alter table public.research_run_artifact add column if not exists deleted_at timestamptz;
alter table public.audit_event add column if not exists deleted_at timestamptz;
alter table public.retention_deletion_operation add column if not exists deleted_at timestamptz;
alter table public.workspace_retention_policy add column if not exists deleted_at timestamptz;
alter table public.tenant_deletion_tombstone add column if not exists deleted_at timestamptz;

create index if not exists idx_workspace_deleted_at on public.workspace(deleted_at);
create index if not exists idx_dataset_deleted_at on public.dataset(tenant_id, deleted_at);
create index if not exists idx_research_run_deleted_at on public.research_run(tenant_id, deleted_at);
create index if not exists idx_evidence_deleted_at on public.evidence(tenant_id, deleted_at);

create or replace function public.soft_delete_workspace(p_workspace_id uuid, p_deleted_at timestamptz default now())
returns uuid language plpgsql security invoker set search_path = public as $$
declare receipt uuid := gen_random_uuid();
begin
  if not exists (select 1 from public.workspace where id = p_workspace_id and deleted_at is null) then raise exception 'WORKSPACE_NOT_FOUND'; end if;
  update public.workspace set deleted_at=p_deleted_at where id=p_workspace_id and deleted_at is null;
  update public.workspace_member set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.subscription set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.dataset set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.dataset_version set deleted_at=p_deleted_at where tenant_id=p_workspace_id and deleted_at is null;
  update public.research_run set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.artifact set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.evidence set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.usage_event set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.audit_log set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.billing_event set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.api_idempotency set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.research_claim set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.research_validation set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.research_finding set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.research_run_result set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.research_run_artifact set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.audit_event set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.retention_deletion_operation set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.workspace_retention_policy set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.tenant_deletion_tombstone set deleted_at=p_deleted_at where workspace_id=p_workspace_id and deleted_at is null;
  update public.entitlements set deleted_at=p_deleted_at where tenant_id=p_workspace_id and deleted_at is null;
  insert into public.tenant_deletion_tombstone (id,workspace_id,tenant_id,deleted_at,purge_after)
  values (receipt,p_workspace_id,p_workspace_id,p_deleted_at,p_deleted_at+interval '30 days') on conflict do nothing;
  return receipt;
end;
$$;

create or replace function public.hard_purge_expired_tenants(p_limit integer default 50)
returns integer language plpgsql security invoker set search_path = public as $$
declare purged integer := 0; tomb record;
begin
  for tomb in select id,workspace_id from public.tenant_deletion_tombstone where purge_after<=now() and deleted_at is not null order by purge_after limit greatest(p_limit,1) loop
    delete from public.research_run_result where workspace_id=tomb.workspace_id;
    delete from public.research_run_artifact where workspace_id=tomb.workspace_id;
    delete from public.evidence where workspace_id=tomb.workspace_id;
    delete from public.research_finding where workspace_id=tomb.workspace_id;
    delete from public.research_validation where workspace_id=tomb.workspace_id;
    delete from public.research_claim where workspace_id=tomb.workspace_id;
    delete from public.artifact where workspace_id=tomb.workspace_id;
    delete from public.usage_event where workspace_id=tomb.workspace_id;
    delete from public.api_idempotency where workspace_id=tomb.workspace_id;
    delete from public.billing_event where workspace_id=tomb.workspace_id;
    delete from public.audit_event where workspace_id=tomb.workspace_id;
    delete from public.audit_log where workspace_id=tomb.workspace_id;
    delete from public.research_run where workspace_id=tomb.workspace_id;
    delete from public.dataset_version where tenant_id=tomb.workspace_id;
    delete from public.dataset where workspace_id=tomb.workspace_id;
    delete from public.workspace_member where workspace_id=tomb.workspace_id;
    delete from public.subscription where workspace_id=tomb.workspace_id;
    delete from public.retention_deletion_operation where workspace_id=tomb.workspace_id;
    delete from public.workspace_retention_policy where workspace_id=tomb.workspace_id;
    delete from public.entitlements where tenant_id=tomb.workspace_id;
    delete from public.workspace where id=tomb.workspace_id;
    delete from public.tenant_deletion_tombstone where id=tomb.id;
    purged:=purged+1;
  end loop;
  return purged;
end;
$$;

revoke all on function public.soft_delete_workspace(uuid,timestamptz) from public,anon,authenticated;
revoke all on function public.hard_purge_expired_tenants(integer) from public,anon,authenticated;
grant execute on function public.soft_delete_workspace(uuid,timestamptz) to service_role;
grant execute on function public.hard_purge_expired_tenants(integer) to service_role;
