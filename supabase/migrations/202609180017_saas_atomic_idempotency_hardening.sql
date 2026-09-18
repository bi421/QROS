-- Harden atomic idempotent research-run creation.
-- Determine insert-vs-replay from INSERT ... RETURNING, never by comparing
-- response JSON. This remains correct when the same server-generated job id
-- is retried and when concurrent requests race on the same workspace/key.

drop function if exists public.create_research_run_idempotent(uuid, uuid, uuid, text, uuid, text, text, jsonb);

create function public.create_research_run_idempotent(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_dataset_version_id uuid,
    p_workflow_id text,
    p_created_by uuid,
    p_idempotency_key text,
    p_request_fingerprint text,
    p_response_body jsonb
)
returns table (
    job jsonb,
    replayed boolean
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_existing public.api_idempotency%rowtype;
    v_job public.research_run%rowtype;
begin
    if p_research_run_id is null
       or p_workspace_id is null
       or p_dataset_version_id is null
       or p_created_by is null
       or p_workflow_id is null
       or length(trim(p_workflow_id)) < 1
       or length(p_workflow_id) > 128
       or p_idempotency_key is null
       or length(trim(p_idempotency_key)) < 1
       or length(p_idempotency_key) > 128
       or p_request_fingerprint is null
       or p_request_fingerprint !~ '^[0-9a-f]{64}$'
       or p_response_body is null then
        raise exception 'invalid idempotent research run arguments';
    end if;

    delete from public.api_idempotency
     where workspace_id = p_workspace_id
       and key = p_idempotency_key
       and expires_at <= clock_timestamp();

    insert into public.api_idempotency(
        workspace_id, key, request_fingerprint, status_code, response_body
    )
    values (
        p_workspace_id, p_idempotency_key, p_request_fingerprint, 202, p_response_body
    )
    on conflict (workspace_id, key) do nothing
    returning * into v_existing;

    if not found then
        select *
          into v_existing
          from public.api_idempotency
         where workspace_id = p_workspace_id
           and key = p_idempotency_key
         for update;

        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key reused with different request'
                using errcode = '23505';
        end if;

        select *
          into v_job
          from public.research_run
         where id = (v_existing.response_body->>'id')::uuid
           and workspace_id = p_workspace_id;

        if not found then
            raise exception 'idempotency record references missing research run';
        end if;

        return query
        select to_jsonb(v_job), true;
        return;
    end if;

    insert into public.research_run(
        id, workspace_id, dataset_version_id, workflow_id, status, created_by
    )
    values (
        p_research_run_id, p_workspace_id, p_dataset_version_id,
        p_workflow_id, 'queued', p_created_by
    )
    returning * into v_job;

    return query
    select to_jsonb(v_job), false;
end;
$$;

revoke all on function public.create_research_run_idempotent(
    uuid, uuid, uuid, text, uuid, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.create_research_run_idempotent(
    uuid, uuid, uuid, text, uuid, text, text, jsonb
) to service_role;
