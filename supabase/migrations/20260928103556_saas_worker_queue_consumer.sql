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
