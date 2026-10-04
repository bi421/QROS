-- Tenant-bound RLS contract hardening.
-- Every tenant-owned public table has a materialized tenant_id UUID and exactly
-- four authenticated policies. The claim is issued by the trusted auth hook;
-- authorization data must live in app metadata, not user metadata.

-- Add the canonical tenant key to all tenant-owned tables.
alter table public.workspace add column if not exists tenant_id uuid;
alter table public.workspace_member add column if not exists tenant_id uuid;
alter table public.subscription add column if not exists tenant_id uuid;
alter table public.dataset add column if not exists tenant_id uuid;
alter table public.dataset_version add column if not exists tenant_id uuid;
alter table public.research_run add column if not exists tenant_id uuid;
alter table public.artifact add column if not exists tenant_id uuid;
alter table public.evidence add column if not exists tenant_id uuid;
alter table public.usage_event add column if not exists tenant_id uuid;
alter table public.audit_log add column if not exists tenant_id uuid;
alter table public.billing_event add column if not exists tenant_id uuid;
alter table public.api_idempotency add column if not exists tenant_id uuid;
alter table public.research_claim add column if not exists tenant_id uuid;
alter table public.research_validation add column if not exists tenant_id uuid;
alter table public.research_finding add column if not exists tenant_id uuid;
alter table public.research_run_result add column if not exists tenant_id uuid;
alter table public.research_run_artifact add column if not exists tenant_id uuid;
alter table public.audit_event add column if not exists tenant_id uuid;
alter table public.retention_deletion_operation add column if not exists tenant_id uuid;
alter table public.workspace_retention_policy add column if not exists tenant_id uuid;
alter table public.tenant_deletion_tombstone add column if not exists tenant_id uuid;

-- Backfill from the existing canonical workspace relationship.
update public.workspace set tenant_id = id where tenant_id is null;
update public.workspace_member set tenant_id = workspace_id where tenant_id is null;
update public.subscription set tenant_id = workspace_id where tenant_id is null;
update public.dataset set tenant_id = workspace_id where tenant_id is null;
update public.dataset_version dv
set tenant_id = d.workspace_id
from public.dataset d
where d.id = dv.dataset_id and dv.tenant_id is null;
update public.research_run set tenant_id = workspace_id where tenant_id is null;
update public.artifact set tenant_id = workspace_id where tenant_id is null;
update public.evidence set tenant_id = workspace_id where tenant_id is null;
update public.usage_event set tenant_id = workspace_id where tenant_id is null;
update public.audit_log set tenant_id = workspace_id where tenant_id is null;
update public.billing_event set tenant_id = workspace_id where tenant_id is null;
update public.api_idempotency set tenant_id = workspace_id where tenant_id is null;
update public.research_claim set tenant_id = workspace_id where tenant_id is null;
update public.research_validation set tenant_id = workspace_id where tenant_id is null;
update public.research_finding set tenant_id = workspace_id where tenant_id is null;
update public.research_run_result set tenant_id = workspace_id where tenant_id is null;
update public.research_run_artifact set tenant_id = workspace_id where tenant_id is null;
update public.audit_event set tenant_id = workspace_id where tenant_id is null;
update public.retention_deletion_operation set tenant_id = workspace_id where tenant_id is null;
update public.workspace_retention_policy set tenant_id = workspace_id where tenant_id is null;
update public.tenant_deletion_tombstone set tenant_id = workspace_id where tenant_id is null;

do $$
declare
  missing_count bigint;
begin
  select count(*) into missing_count
  from (
    select tenant_id from public.workspace where tenant_id is null
    union all select tenant_id from public.workspace_member where tenant_id is null
    union all select tenant_id from public.subscription where tenant_id is null
    union all select tenant_id from public.dataset where tenant_id is null
    union all select tenant_id from public.dataset_version where tenant_id is null
    union all select tenant_id from public.research_run where tenant_id is null
    union all select tenant_id from public.artifact where tenant_id is null
    union all select tenant_id from public.evidence where tenant_id is null
    union all select tenant_id from public.usage_event where tenant_id is null
    union all select tenant_id from public.audit_log where tenant_id is null
    union all select tenant_id from public.billing_event where tenant_id is null
    union all select tenant_id from public.api_idempotency where tenant_id is null
    union all select tenant_id from public.research_claim where tenant_id is null
    union all select tenant_id from public.research_validation where tenant_id is null
    union all select tenant_id from public.research_finding where tenant_id is null
    union all select tenant_id from public.research_run_result where tenant_id is null
    union all select tenant_id from public.research_run_artifact where tenant_id is null
    union all select tenant_id from public.audit_event where tenant_id is null
    union all select tenant_id from public.workspace_retention_policy where tenant_id is null
    union all select tenant_id from public.tenant_deletion_tombstone where tenant_id is null
  ) missing;
  if missing_count > 0 then
    raise exception 'tenant_id backfill incomplete: % rows', missing_count;
  end if;
end $$;

alter table public.workspace alter column tenant_id set not null;
alter table public.workspace_member alter column tenant_id set not null;
alter table public.subscription alter column tenant_id set not null;
alter table public.dataset alter column tenant_id set not null;
alter table public.dataset_version alter column tenant_id set not null;
alter table public.research_run alter column tenant_id set not null;
alter table public.artifact alter column tenant_id set not null;
alter table public.evidence alter column tenant_id set not null;
alter table public.usage_event alter column tenant_id set not null;
alter table public.audit_log alter column tenant_id set not null;
alter table public.billing_event alter column tenant_id set not null;
alter table public.api_idempotency alter column tenant_id set not null;
alter table public.research_claim alter column tenant_id set not null;
alter table public.research_validation alter column tenant_id set not null;
alter table public.research_finding alter column tenant_id set not null;
alter table public.research_run_result alter column tenant_id set not null;
alter table public.research_run_artifact alter column tenant_id set not null;
alter table public.audit_event alter column tenant_id set not null;
alter table public.workspace_retention_policy alter column tenant_id set not null;
alter table public.tenant_deletion_tombstone alter column tenant_id set not null;

create or replace function public.set_qros_tenant_from_workspace()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.workspace_id is not null then
    new.tenant_id := new.workspace_id;
  end if;
  return new;
end;
$$;

create or replace function public.set_qros_tenant_from_dataset()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  select d.workspace_id
    into new.tenant_id
    from public.dataset d
   where d.id = new.dataset_id;
  return new;
end;
$$;

create or replace function public.set_qros_workspace_tenant()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.tenant_id := new.id;
  return new;
end;
$$;

drop trigger if exists set_qros_tenant_id on public.workspace;
create trigger set_qros_tenant_id
before insert or update on public.workspace
for each row execute function public.set_qros_workspace_tenant();

drop trigger if exists set_qros_tenant_id on public.dataset_version;
create trigger set_qros_tenant_id
before insert or update on public.dataset_version
for each row execute function public.set_qros_tenant_from_dataset();

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'workspace_member','subscription','dataset','research_run','artifact',
    'evidence','usage_event','audit_log','billing_event','api_idempotency',
    'research_claim','research_validation','research_finding','research_run_result',
    'research_run_artifact','audit_event','retention_deletion_operation',
    'workspace_retention_policy','tenant_deletion_tombstone'
  ] loop
    execute format('drop trigger if exists set_qros_tenant_id on public.%I', table_name);
    execute format(
      'create trigger set_qros_tenant_id
       before insert or update on public.%I
       for each row execute function public.set_qros_tenant_from_workspace()',
      table_name
    );
  end loop;
end $$;

create index if not exists idx_workspace_tenant_id on public.workspace(tenant_id);
create index if not exists idx_dataset_tenant_id on public.dataset(tenant_id);
create index if not exists idx_research_run_tenant_id on public.research_run(tenant_id);
create index if not exists idx_evidence_tenant_id on public.evidence(tenant_id);

do $$
declare
  table_name text;
  policy_name text;
  existing_policy record;
begin
  foreach table_name in array array[
    'workspace','workspace_member','subscription','dataset','dataset_version',
    'research_run','artifact','evidence','usage_event','audit_log',
    'billing_event','api_idempotency','research_claim','research_validation',
    'research_finding','research_run_result','research_run_artifact','audit_event',
    'retention_deletion_operation','workspace_retention_policy','tenant_deletion_tombstone'
  ] loop
    execute format('alter table public.%I enable row level security', table_name);

    for existing_policy in
      select policyname
      from pg_policies
      where schemaname = 'public'
        and tablename = table_name
    loop
      execute format(
        'drop policy if exists %I on public.%I',
        existing_policy.policyname,
        table_name
      );
    end loop;

    execute format(
      'create policy tenant_select on public.%I for select to authenticated using (auth.jwt() ->> ''tenant_id'' = tenant_id::text)',
      table_name
    );
    execute format(
      'create policy tenant_insert on public.%I for insert to authenticated with check (auth.jwt() ->> ''tenant_id'' = tenant_id::text)',
      table_name
    );
    execute format(
      'create policy tenant_update on public.%I for update to authenticated using (auth.jwt() ->> ''tenant_id'' = tenant_id::text) with check (auth.jwt() ->> ''tenant_id'' = tenant_id::text)',
      table_name
    );
    execute format(
      'create policy tenant_delete on public.%I for delete to authenticated using (auth.jwt() ->> ''tenant_id'' = tenant_id::text)',
      table_name
    );
  end loop;
end $$;

comment on column public.workspace.tenant_id is 'Canonical tenant identifier; for workspace rows tenant_id equals workspace.id.';
comment on column public.dataset.tenant_id is 'Materialized tenant boundary used by the canonical RLS policy contract.';
