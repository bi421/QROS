-- Atomic, tenant-scoped retention deletion state transitions.
-- Only service_role may execute this server-side coordination RPC.

create or replace function private.transition_retention_deletion_operation(
    p_workspace_id uuid,
    p_operation_id text,
    p_resource_type text,
    p_resource_id text,
    p_state text
)
returns public.retention_deletion_operation
language plpgsql
security definer
set search_path = ''
as $$
declare
    current_operation public.retention_deletion_operation;
begin
    if p_workspace_id is null then raise exception 'workspace_id is required'; end if;
    if p_operation_id is null or char_length(trim(p_operation_id)) = 0 then raise exception 'operation_id is required'; end if;
    if p_resource_type is null or char_length(trim(p_resource_type)) = 0 then raise exception 'resource_type is required'; end if;
    if p_resource_id is null or char_length(trim(p_resource_id)) = 0 then raise exception 'resource_id is required'; end if;

    select *
      into current_operation
      from public.retention_deletion_operation
     where workspace_id = p_workspace_id
       and operation_id = p_operation_id
       and resource_type = p_resource_type
       and resource_id = p_resource_id
     for update;

    if current_operation.id is null then
        raise exception 'retention operation not found';
    end if;

    if not (
        (current_operation.state = 'APPROVED' and p_state in ('DELETE_ATTEMPTED', 'RECONCILIATION_REQUIRED'))
        or (current_operation.state = 'DELETE_ATTEMPTED' and p_state in ('COMPLETED', 'RECONCILIATION_REQUIRED'))
        or current_operation.state = p_state
    ) then
        raise exception 'invalid retention operation state transition';
    end if;

    update public.retention_deletion_operation
       set state = p_state,
           updated_at = now()
     where id = current_operation.id
     returning * into current_operation;

    return current_operation;
end;
$$;

revoke all on function private.transition_retention_deletion_operation(uuid, text, text, text, text)
    from public, anon, authenticated;
grant execute on function private.transition_retention_deletion_operation(uuid, text, text, text, text)
    to service_role;

create or replace function public.transition_retention_deletion_operation(
    p_workspace_id uuid,
    p_operation_id text,
    p_resource_type text,
    p_resource_id text,
    p_state text
)
returns public.retention_deletion_operation
language sql
security invoker
set search_path = ''
as $$
    select * from private.transition_retention_deletion_operation(
        p_workspace_id, p_operation_id, p_resource_type, p_resource_id, p_state
    );
$$;

revoke all on function public.transition_retention_deletion_operation(uuid, text, text, text, text)
    from public, anon, authenticated;
grant execute on function public.transition_retention_deletion_operation(uuid, text, text, text, text)
    to service_role;

comment on function private.transition_retention_deletion_operation(uuid, text, text, text, text) is
    'Atomic tenant-scoped retention state transition; service-role only.';
comment on function public.transition_retention_deletion_operation(uuid, text, text, text, text) is
    'Server-only API wrapper for atomic retention state transition.';
