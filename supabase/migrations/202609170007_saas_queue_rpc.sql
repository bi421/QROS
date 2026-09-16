-- Server-only queue enqueue primitive.
-- The browser never receives execute permission for this function.

create or replace function public.enqueue_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid
)
returns bigint
language plpgsql
security definer
set search_path = pgmq, public
as $$
declare
    message_id bigint;
begin
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
            'workspace_id', p_workspace_id
        )
    ) into message_id;

    return message_id;
end;
$$;

revoke all on function public.enqueue_research_run(uuid, uuid) from public;
grant execute on function public.enqueue_research_run(uuid, uuid) to service_role;

comment on function public.enqueue_research_run(uuid, uuid)
is 'Server-only enqueue primitive for tenant-scoped research jobs; payload contains identifiers only.';
