-- Tenant compliance lifecycle controls.
-- Soft deletion is the public lifecycle boundary. Physical purge is a
-- privileged, post-retention operation; audit tombstones remain immutable.

create extension if not exists pgcrypto;

alter table public.workspace add column if not exists deleted_at timestamptz;
alter table public.workspace add column if not exists purge_at timestamptz;

create table if not exists public.workspace_retention_policy (
    workspace_id uuid primary key references public.workspace(id) on delete restrict,
    retention_days integer not null default 30 check (retention_days between 1 and 3650),
    deleted_at timestamptz,
    purge_at timestamptz,
    receipt_id uuid not null default gen_random_uuid(),
    updated_at timestamptz not null default now()
);

create table if not exists public.tenant_deletion_tombstone (
    table_name text not null,
    row_id text not null,
    workspace_id uuid not null,
    historical_hash text not null check (historical_hash ~ '^[0-9a-f]{64}$'),
    deleted_at timestamptz not null,
    purged_at timestamptz not null default now(),
    primary key (table_name, row_id)
);

revoke all on table public.workspace_retention_policy, public.tenant_deletion_tombstone
    from public, anon, authenticated;
grant all on table public.workspace_retention_policy, public.tenant_deletion_tombstone
    to service_role;

alter table public.workspace_retention_policy enable row level security;
alter table public.workspace_retention_policy force row level security;
alter table public.tenant_deletion_tombstone enable row level security;
alter table public.tenant_deletion_tombstone force row level security;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'workspace',
        'workspace_member',
        'subscription',
        'dataset',
        'dataset_version',
        'research_run',
        'artifact',
        'evidence',
        'usage_event',
        'audit_log',
        'billing_event',
        'api_idempotency',
        'research_claim',
        'research_validation',
        'research_finding',
        'research_run_result',
        'research_run_artifact',
        'audit_event',
        'retention_deletion_operation'
    ]
    loop
        execute format('alter table public.%I add column if not exists deleted_at timestamptz', table_name);
    end loop;
end $$;

create index if not exists idx_workspace_deleted_at
    on public.workspace(deleted_at, purge_at);
create index if not exists idx_dataset_workspace_deleted
    on public.dataset(workspace_id, deleted_at);
create index if not exists idx_research_run_workspace_deleted
    on public.research_run(workspace_id, deleted_at);
create index if not exists idx_evidence_workspace_deleted
    on public.evidence(workspace_id, deleted_at);
create index if not exists idx_research_finding_workspace_deleted
    on public.research_finding(workspace_id, deleted_at);

create or replace function public.prevent_deleted_row_resurrection()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if old.deleted_at is not null then
        raise exception 'DELETED_RESOURCE_IMMUTABLE'
            using errcode = '55000';
    end if;
    return new;
end;
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'workspace',
        'workspace_member',
        'subscription',
        'dataset',
        'dataset_version',
        'research_run',
        'artifact',
        'evidence',
        'usage_event',
        'audit_log',
        'billing_event',
        'api_idempotency',
        'research_claim',
        'research_validation',
        'research_finding',
        'research_run_result',
        'research_run_artifact',
        'audit_event',
        'retention_deletion_operation'
    ]
    loop
        execute format('drop trigger if exists prevent_deleted_row_resurrection on public.%I', table_name);
        execute format(
            'create trigger prevent_deleted_row_resurrection
             before update on public.%I
             for each row execute function public.prevent_deleted_row_resurrection()',
            table_name
        );
    end loop;
end $$;

create or replace function public.prevent_dataset_version_mutation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if tg_op = 'DELETE' then
        if current_setting('qros.retention_purge', true) = 'on' then
            return old;
        end if;
        raise exception 'dataset versions are immutable and cannot be deleted';
    end if;

    if old.deleted_at is not null then
        raise exception 'DELETED_RESOURCE_IMMUTABLE';
    end if;

    if new.dataset_id <> old.dataset_id
       or new.version_no <> old.version_no
       or new.content_sha256 <> old.content_sha256
       or new.storage_path <> old.storage_path
       or new.byte_size <> old.byte_size
       or new.created_by <> old.created_by
       or new.created_at <> old.created_at then
        raise exception 'dataset versions are immutable';
    end if;

    return new;
end;
$$;

create or replace function public.prevent_tombstoned_insert()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
    workspace_value uuid;
    row_key text;
begin
    if tg_table_name = 'workspace' then
        workspace_value := new.id;
        row_key := new.id::text;
    elsif tg_table_name = 'workspace_member' then
        workspace_value := new.workspace_id;
        row_key := new.workspace_id::text || ':' || new.user_id::text;
    elsif tg_table_name = 'research_claim' then
        workspace_value := new.workspace_id;
        row_key := new.id::text;
    elsif tg_table_name = 'api_idempotency' then
        workspace_value := new.workspace_id;
        row_key := new.workspace_id::text || ':' || new.key;
    elsif tg_table_name = 'dataset_version' then
        select d.workspace_id into workspace_value
          from public.dataset d
         where d.id = new.dataset_id;
        row_key := new.id::text;
    else
        workspace_value := new.workspace_id;
        row_key := new.id::text;
    end if;

    if exists (
        select 1
          from public.tenant_deletion_tombstone
         where table_name = tg_table_name
           and row_id = row_key
    ) then
        raise exception 'DELETED_RESOURCE_CANNOT_BE_RESURRECTED'
            using errcode = '55000';
    end if;

    return new;
end;
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'workspace',
        'workspace_member',
        'dataset',
        'research_run',
        'artifact',
        'evidence',
        'research_claim',
        'research_validation',
        'research_finding',
        'research_run_result',
        'research_run_artifact',
        'dataset_version',
        'audit_event',
        'retention_deletion_operation'
    ]
    loop
        execute format('drop trigger if exists prevent_tombstoned_insert on public.%I', table_name);
        execute format(
            'create trigger prevent_tombstoned_insert
             before insert on public.%I
             for each row execute function public.prevent_tombstoned_insert()',
            table_name
        );
    end loop;
end $$;

create or replace function public.soft_delete_workspace(
    p_workspace_id uuid,
    p_deleted_at timestamptz default timezone('utc', now()),
    p_retention_days integer default 30
)
returns table (
    workspace_id uuid,
    deleted_at timestamptz,
    scheduled_purge_at timestamptz,
    retention_days integer,
    receipt_id uuid
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_receipt uuid;
    v_deleted timestamptz;
    v_purge timestamptz;
begin
    if p_workspace_id is null then
        raise exception 'workspace_id is required';
    end if;
    if p_retention_days < 1 or p_retention_days > 3650 then
        raise exception 'retention_days must be between 1 and 3650';
    end if;

    select coalesce(w.deleted_at, p_deleted_at)
      into v_deleted
      from public.workspace w
     where w.id = p_workspace_id
     for update;

    if v_deleted is null then
        raise exception 'workspace not found';
    end if;

    v_purge := v_deleted + make_interval(days => p_retention_days);

    select coalesce(wrp.receipt_id, gen_random_uuid())
      into v_receipt
      from public.workspace_retention_policy wrp
     where wrp.workspace_id = p_workspace_id;

    if v_receipt is null then
        v_receipt := gen_random_uuid();
    end if;

    update public.workspace
       set deleted_at = v_deleted,
           purge_at = v_purge
     where id = p_workspace_id
       and deleted_at is null;

    update public.workspace_retention_policy
       set retention_days = p_retention_days,
           deleted_at = v_deleted,
           purge_at = v_purge,
           receipt_id = v_receipt,
           updated_at = timezone('utc', now())
     where workspace_id = p_workspace_id;

    insert into public.workspace_retention_policy(
        workspace_id, retention_days, deleted_at, purge_at, receipt_id
    )
    select p_workspace_id, p_retention_days, v_deleted, v_purge, v_receipt
    where not exists (
        select 1 from public.workspace_retention_policy
         where workspace_id = p_workspace_id
    );

    update public.workspace_member set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.subscription set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.dataset set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.dataset_version dv
       set deleted_at = v_deleted
      from public.dataset d
     where d.id = dv.dataset_id and d.workspace_id = p_workspace_id and dv.deleted_at is null;
    update public.research_run set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.artifact set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.evidence set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.usage_event set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.billing_event set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.api_idempotency set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.research_claim set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.research_validation set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.research_finding set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.research_run_result set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;
    update public.research_run_artifact set deleted_at = v_deleted where workspace_id = p_workspace_id and deleted_at is null;

    return query
    select p_workspace_id, v_deleted, v_purge, p_retention_days, v_receipt;
end;
$$;

revoke all on function public.soft_delete_workspace(uuid, timestamptz, integer)
    from public, anon, authenticated;
grant execute on function public.soft_delete_workspace(uuid, timestamptz, integer)
    to service_role;

create or replace function public.purge_deleted_workspaces(
    p_now timestamptz default timezone('utc', now())
)
returns integer
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    workspace_row record;
    purged_count integer := 0;
begin
    perform set_config('qros.retention_purge', 'on', true);

    for workspace_row in
        select id
          from public.workspace
         where deleted_at is not null
           and purge_at is not null
           and purge_at <= p_now
         for update skip locked
    loop
        insert into public.tenant_deletion_tombstone(
            table_name, row_id, workspace_id, historical_hash, deleted_at, purged_at
        )
        select 'evidence', e.id::text, e.workspace_id,
               encode(digest(
                   coalesce(e.id::text,'') || '|' ||
                   coalesce(e.claim,'') || '|' ||
                   coalesce(e.status,'') || '|' ||
                   coalesce(e.provenance::text,''),
                   'sha256'
               ), 'hex'),
               e.deleted_at, p_now
          from public.evidence e
         where e.workspace_id = workspace_row.id
           and e.deleted_at is not null
        on conflict (table_name, row_id) do nothing;

        insert into public.tenant_deletion_tombstone(
            table_name, row_id, workspace_id, historical_hash, deleted_at, purged_at
        )
        select 'dataset_version', dv.id::text, d.workspace_id,
               encode(digest(
                   coalesce(dv.id::text,'') || '|' ||
                   coalesce(dv.content_sha256,'') || '|' ||
                   coalesce(dv.storage_path,''),
                   'sha256'
               ), 'hex'),
               dv.deleted_at, p_now
          from public.dataset_version dv
          join public.dataset d on d.id = dv.dataset_id
         where d.workspace_id = workspace_row.id
           and dv.deleted_at is not null
        on conflict (table_name, row_id) do nothing;

        insert into public.tenant_deletion_tombstone(
            table_name, row_id, workspace_id, historical_hash, deleted_at, purged_at
        )
        select 'dataset', d.id::text, d.workspace_id,
               encode(digest(coalesce(d.id::text,'') || '|' || coalesce(d.name,''), 'sha256'), 'hex'),
               d.deleted_at, p_now
          from public.dataset d
         where d.workspace_id = workspace_row.id and d.deleted_at is not null
        on conflict (table_name, row_id) do nothing;

        delete from public.research_finding where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.research_validation where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.research_run_artifact where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.research_run_result where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.evidence where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.artifact where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.research_claim where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.research_run where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.audit_event where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.retention_deletion_operation where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.usage_event where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.billing_event where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.api_idempotency where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.dataset_version dv
         using public.dataset d
         where dv.dataset_id = d.id and d.workspace_id = workspace_row.id and dv.deleted_at is not null;
        delete from public.dataset where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.subscription where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.workspace_member where workspace_id = workspace_row.id and deleted_at is not null;
        delete from public.workspace where id = workspace_row.id and deleted_at is not null;

        delete from public.workspace_retention_policy where workspace_id = workspace_row.id;
        purged_count := purged_count + 1;
    end loop;

    return purged_count;
end;
$$;

revoke all on function public.purge_deleted_workspaces(timestamptz)
    from public, anon, authenticated;
grant execute on function public.purge_deleted_workspaces(timestamptz)
    to service_role;

comment on table public.tenant_deletion_tombstone is
    'Immutable post-purge audit anchors. Evidence hashes survive physical deletion so historical lineage cannot be resurrected.';
comment on function public.soft_delete_workspace(uuid, timestamptz, integer) is
    'Tenant compliance boundary: atomically soft-deletes tenant rows and schedules physical purge.';
comment on function public.purge_deleted_workspaces(timestamptz) is
    'Privileged hard purge after workspace-specific retention period. Audit tombstones remain.';
