-- QROS production forward reconciliation (2026-10-06)
--
-- Purpose: close verified current-main/live-Supabase schema gaps with one
-- forward-only migration. Historical migration files and live migration
-- history are intentionally not rewritten.
--
-- Required current-main effects proven absent in the live schema:
--   * tenant retention lifecycle controls
--   * billing_admin workspace role constraint
--   * request-correlated enqueue RPC
--   * governed queue receive/ack RPCs
--   * provider subscription uniqueness
--
-- Effects intentionally excluded because live schema already contains the
-- current canonical behavior despite historical filename/version drift:
--   storage membership authorization, dataset registry/feed guard,
--   dataset-version storage-path reconciliation, research client-deny
--   policies, team entitlement contract, and first-workspace provisioning.
--
-- Legacy tenant_id RLS and pgTAP are intentionally not part of the current
-- production architecture/remediation.

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

-- The deletion-operation row is an audit/control record, not tenant content.
-- Keep it after workspace purge by detaching the workspace foreign key.
alter table public.retention_deletion_operation
    drop constraint if exists retention_deletion_operation_workspace_id_fkey;
alter table public.retention_deletion_operation
    alter column workspace_id drop not null;
alter table public.retention_deletion_operation
    add constraint retention_deletion_operation_workspace_id_fkey
    foreign key (workspace_id) references public.workspace(id) on delete set null;

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
        'audit_event'
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
        'audit_event'
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
        select 'workspace', w.id::text, w.id,
               encode(digest(coalesce(w.id::text,'') || '|' || coalesce(w.created_at::text,''), 'sha256'), 'hex'),
               w.deleted_at, p_now
          from public.workspace w
         where w.id = workspace_row.id
           and w.deleted_at is not null
        on conflict (table_name, row_id) do nothing;

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
        -- Remove the retention policy before deleting its referenced workspace.
        -- The policy intentionally uses ON DELETE RESTRICT so an active policy
        -- cannot disappear implicitly; purge explicitly owns this lifecycle.
        delete from public.workspace_retention_policy where workspace_id = workspace_row.id;

        delete from public.workspace where id = workspace_row.id and deleted_at is not null;
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


-- Forward-only production reconciliation: current SaaS authorization uses billing_admin.
-- Existing membership rows are preserved; only the allowed-role constraint is widened.
alter table public.workspace_member drop constraint if exists workspace_member_role_check;
alter table public.workspace_member add constraint workspace_member_role_check
    check (role in ('owner','admin','researcher','viewer','billing_admin'));


-- Persist API correlation IDs with durable research queue messages.
-- The request_id is diagnostic metadata only; tenant authorization remains
-- bound to the workspace/job relationship and database RLS.

create or replace function public.enqueue_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_request_id text default null
)
returns bigint
language plpgsql
security definer
set search_path = pgmq, public
as $$
declare
    message_id bigint;
begin
    if p_request_id is not null and length(p_request_id) > 128 then
        raise exception 'request_id exceeds 128 characters';
    end if;

    if not exists (
        select 1
        from public.research_run rr
        where rr.id = p_research_run_id
          and rr.workspace_id = p_workspace_id
    ) then
        raise exception 'research run not found for workspace';
    end if;

    select pgmq.send(
        'qros-research-runs',
        jsonb_build_object(
            'research_run_id', p_research_run_id,
            'workspace_id', p_workspace_id,
            'request_id', p_request_id
        )
    ) into message_id;

    return message_id;
end;
$$;

revoke all on function public.enqueue_research_run(uuid, uuid, text) from public, anon, authenticated;
grant execute on function public.enqueue_research_run(uuid, uuid, text) to service_role;

create or replace function public.enqueue_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid
)
returns bigint
language sql
security definer
set search_path = pgmq, public
as $$
    select public.enqueue_research_run(p_research_run_id, p_workspace_id, null);
$$;

revoke all on function public.enqueue_research_run(uuid, uuid) from public, anon, authenticated;
grant execute on function public.enqueue_research_run(uuid, uuid) to service_role;

comment on function public.enqueue_research_run(uuid, uuid, text)
is 'Server-only enqueue primitive; payload carries tenant-bound job identifiers and request correlation metadata.';


-- Governed server-side consumer boundary for the existing research pgmq queue.
-- Queue name and identifier-only payload semantics are fixed; clients cannot select arbitrary queues.

create or replace function public.receive_research_run(
    p_visibility_timeout integer default 1200
)
returns table (
    msg_id bigint,
    read_ct bigint,
    enqueued_at timestamptz,
    vt timestamptz,
    message jsonb,
    workspace_id uuid,
    research_run_id uuid
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_message pgmq.message_record;
begin
    if p_visibility_timeout < 1 or p_visibility_timeout > 86400 then
        raise exception 'invalid queue visibility timeout';
    end if;

    select *
      into v_message
      from pgmq.read_with_poll(
          'qros-research-runs',
          p_visibility_timeout,
          1,
          5,
          100
      );

    if not found then
        return;
    end if;

    if pg_catalog.jsonb_typeof(v_message.message) <> 'object'
       or not (v_message.message ? 'workspace_id')
       or not (v_message.message ? 'research_run_id')
       or (v_message.message - 'workspace_id' - 'research_run_id') <> '{}'::jsonb
       or pg_catalog.jsonb_typeof(v_message.message -> 'workspace_id') <> 'string'
       or pg_catalog.jsonb_typeof(v_message.message -> 'research_run_id') <> 'string' then
        raise exception 'malformed research queue message';
    end if;

    msg_id := v_message.msg_id;
    read_ct := v_message.read_ct;
    enqueued_at := v_message.enqueued_at;
    vt := v_message.vt;
    message := v_message.message;
    workspace_id := (v_message.message ->> 'workspace_id')::uuid;
    research_run_id := (v_message.message ->> 'research_run_id')::uuid;
    return next;
exception
    when invalid_text_representation then
        raise exception 'malformed research queue identifier payload';
end;
$$;

revoke all on function public.receive_research_run(integer) from public, anon, authenticated;
grant execute on function public.receive_research_run(integer) to service_role;

create or replace function public.ack_research_run(
    p_message_id bigint
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_message_id < 1 then
        raise exception 'invalid research queue message id';
    end if;
    return pgmq.delete('qros-research-runs', p_message_id);
end;
$$;

revoke all on function public.ack_research_run(bigint) from public, anon, authenticated;
grant execute on function public.ack_research_run(bigint) to service_role;

comment on function public.receive_research_run(integer)
is 'Server-only receive primitive for the fixed qros-research-runs queue; validates identifier-only payloads and preserves pgmq visibility semantics.';

comment on function public.ack_research_run(bigint)
is 'Server-only acknowledgement primitive for the fixed qros-research-runs queue.';


-- A provider subscription must identify exactly one QROS workspace.
-- This prevents a signed webhook for an already-bound Stripe subscription
-- from being rebound to a second workspace through provider metadata.
create unique index if not exists subscription_provider_subscription_id_key
    on public.subscription (provider_subscription_id)
    where provider_subscription_id is not null;

comment on index public.subscription_provider_subscription_id_key is
    'Each non-null provider subscription id may belong to only one workspace.';
