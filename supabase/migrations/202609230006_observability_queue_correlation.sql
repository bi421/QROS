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
