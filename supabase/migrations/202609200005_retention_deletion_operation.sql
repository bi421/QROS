-- Durable tenant-scoped retention deletion operation state.
-- This is a server-only coordination boundary. No browser/Data API access is granted.

create table if not exists public.retention_deletion_operation (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete restrict,
    operation_id text not null check (char_length(operation_id) between 1 and 128),
    resource_type text not null check (char_length(resource_type) between 1 and 128),
    resource_id text not null check (char_length(resource_id) between 1 and 256),
    state text not null check (
        state in (
            'APPROVED',
            'DELETE_ATTEMPTED',
            'COMPLETED',
            'RECONCILIATION_REQUIRED'
        )
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (workspace_id, operation_id)
);

alter table public.retention_deletion_operation enable row level security;

revoke all on table public.retention_deletion_operation from anon, authenticated;

comment on table public.retention_deletion_operation is
    'Server-only tenant-scoped state for idempotent destructive retention operations.';

create or replace function private.reserve_retention_deletion_operation(
    p_workspace_id uuid,
    p_operation_id text,
    p_resource_type text,
    p_resource_id text
)
returns public.retention_deletion_operation
language plpgsql
security definer
set search_path = ''
as $$
declare
    existing public.retention_deletion_operation;
begin
    if p_workspace_id is null then
        raise exception 'workspace_id is required';
    end if;
    if p_operation_id is null or char_length(trim(p_operation_id)) = 0 then
        raise exception 'operation_id is required';
    end if;
    if p_resource_type is null or char_length(trim(p_resource_type)) = 0 then
        raise exception 'resource_type is required';
    end if;
    if p_resource_id is null or char_length(trim(p_resource_id)) = 0 then
        raise exception 'resource_id is required';
    end if;

    insert into public.retention_deletion_operation (
        workspace_id, operation_id, resource_type, resource_id, state
    )
    values (
        p_workspace_id, p_operation_id, p_resource_type, p_resource_id, 'APPROVED'
    )
    on conflict (workspace_id, operation_id) do nothing
    returning * into existing;

    if existing.id is not null then
        return existing;
    end if;

    select *
      into existing
      from public.retention_deletion_operation
     where workspace_id = p_workspace_id
       and operation_id = p_operation_id
     for update;

    if existing.resource_type <> p_resource_type
       or existing.resource_id <> p_resource_id then
        raise exception 'retention operation key already bound to a different resource';
    end if;

    return existing;
end;
$$;

revoke all on function private.reserve_retention_deletion_operation(uuid, text, text, text)
    from public, anon, authenticated;
grant execute on function private.reserve_retention_deletion_operation(uuid, text, text, text)
    to service_role;

alter function private.reserve_retention_deletion_operation(uuid, text, text, text)
    set search_path = '';

comment on function private.reserve_retention_deletion_operation(uuid, text, text, text) is
    'Atomic tenant-scoped retention operation reservation; service-role only.';

create or replace function public.reserve_retention_deletion_operation(
    p_workspace_id uuid,
    p_operation_id text,
    p_resource_type text,
    p_resource_id text
)
returns public.retention_deletion_operation
language sql
security invoker
set search_path = ''
as $$
    select * from private.reserve_retention_deletion_operation(
        p_workspace_id, p_operation_id, p_resource_type, p_resource_id
    );
$$;

revoke all on function public.reserve_retention_deletion_operation(uuid, text, text, text)
    from public, anon, authenticated;
grant execute on function public.reserve_retention_deletion_operation(uuid, text, text, text)
    to service_role;

comment on function public.reserve_retention_deletion_operation(uuid, text, text, text) is
    'Server-only API wrapper for atomic tenant-scoped retention operation reservation.';
