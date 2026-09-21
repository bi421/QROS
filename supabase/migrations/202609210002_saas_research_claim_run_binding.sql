-- Bind a research execution to an immutable, tenant-scoped Research Claim plan.
-- The binding is optional for legacy runs but, when present, both identifiers
-- are persisted together and the database verifies the locked plan identity.

alter table public.research_run
    add column if not exists claim_id text,
    add column if not exists plan_hash text;

alter table public.research_run
    drop constraint if exists research_run_plan_hash_format;

alter table public.research_run
    add constraint research_run_plan_hash_format
    check (plan_hash is null or plan_hash ~ '^[0-9a-f]{64}$');

alter table public.research_run
    drop constraint if exists research_run_claim_plan_pair;

alter table public.research_run
    add constraint research_run_claim_plan_pair
    check ((claim_id is null) = (plan_hash is null));

alter table public.research_run
    drop constraint if exists research_run_claim_tenant_fk;

alter table public.research_run
    add constraint research_run_claim_tenant_fk
    foreign key (workspace_id, claim_id)
    references public.research_claim(workspace_id, id);

create index if not exists idx_research_run_claim
    on public.research_run(workspace_id, claim_id)
    where claim_id is not null;

create or replace function public.create_governed_research_run_idempotent(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_dataset_version_id uuid,
    p_workflow_id text,
    p_created_by uuid,
    p_idempotency_key text,
    p_request_fingerprint text,
    p_response_body jsonb,
    p_claim_id text,
    p_plan_hash text
)
returns table (job jsonb, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_existing public.api_idempotency%rowtype;
    v_job public.research_run%rowtype;
    v_claim public.research_claim%rowtype;
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
       or p_response_body is null
       or p_claim_id is null
       or length(trim(p_claim_id)) < 1
       or length(p_claim_id) > 256
       or p_plan_hash is null
       or p_plan_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid governed research run arguments';
    end if;

    select *
      into v_claim
      from public.research_claim
     where workspace_id = p_workspace_id
       and id = p_claim_id
     for share;

    if not found then
        raise exception 'research claim not found for workspace';
    end if;

    if v_claim.plan_hash is null or v_claim.plan_hash <> p_plan_hash or v_claim.plan_locked_at is null then
        raise exception 'research claim plan is not locked or does not match';
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
    on conflict (workspace_id, key) do nothing;

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

    if v_existing.response_body = p_response_body then
        insert into public.research_run(
            id, workspace_id, dataset_version_id, workflow_id, status,
            created_by, claim_id, plan_hash
        )
        values (
            p_research_run_id, p_workspace_id, p_dataset_version_id,
            p_workflow_id, 'queued', p_created_by, p_claim_id, p_plan_hash
        )
        returning * into v_job;

        return query select to_jsonb(v_job), false;
    end if;

    select *
      into v_job
      from public.research_run
     where id = (v_existing.response_body->>'id')::uuid
       and workspace_id = p_workspace_id;

    if not found then
        raise exception 'idempotency record references missing research run';
    end if;

    return query select to_jsonb(v_job), true;
end;
$$;

revoke all on function public.create_governed_research_run_idempotent(
    uuid, uuid, uuid, text, uuid, text, text, jsonb, text, text
) from public, anon, authenticated;

grant execute on function public.create_governed_research_run_idempotent(
    uuid, uuid, uuid, text, uuid, text, text, jsonb, text, text
) to service_role;

comment on column public.research_run.claim_id is
    'Tenant-scoped Research Claim identity governing this execution; immutable once set.';

comment on column public.research_run.plan_hash is
    'SHA-256 of the locked Research Plan governing this execution.';
