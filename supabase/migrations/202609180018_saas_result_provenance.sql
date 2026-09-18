-- Bind every research run to immutable dataset content and persist its scientific result manifest.
-- This is the durable provenance boundary between SaaS execution and the research core.

alter table public.research_run
    add column if not exists source_dataset_sha256 text;

update public.research_run rr
   set source_dataset_sha256 = dv.content_sha256
  from public.dataset_version dv
 where dv.id = rr.dataset_version_id
   and rr.source_dataset_sha256 is null;

do $$
begin
    if exists (
        select 1
          from public.research_run
         where source_dataset_sha256 is null
    ) then
        raise exception 'cannot enforce research_run.source_dataset_sha256: existing run has no dataset provenance';
    end if;
end;
$$;

alter table public.research_run
    alter column source_dataset_sha256 set not null;

alter table public.research_run
    add constraint research_run_source_dataset_sha256_format
    check (source_dataset_sha256 ~ '^[0-9a-f]{64}$');

create table if not exists public.research_run_result (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    research_run_id uuid not null unique references public.research_run(id) on delete cascade,
    source_dataset_sha256 text not null,
    status text not null check (status in ('SUCCEEDED', 'FAILED')),
    manifest_sha256 text not null check (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    failures jsonb not null default '[]'::jsonb check (jsonb_typeof(failures) = 'array'),
    created_at timestamptz not null default now(),
    constraint research_run_result_source_sha256_format
        check (source_dataset_sha256 ~ '^[0-9a-f]{64}$')
);

create table if not exists public.research_run_artifact (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    research_run_id uuid not null references public.research_run(id) on delete cascade,
    artifact_id text not null,
    kind text not null,
    content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    unique (research_run_id, artifact_id)
);

create index if not exists research_run_result_workspace_idx
    on public.research_run_result (workspace_id, created_at desc);
create index if not exists research_run_artifact_workspace_idx
    on public.research_run_artifact (workspace_id, research_run_id);

alter table public.research_run_result enable row level security;
alter table public.research_run_artifact enable row level security;

drop policy if exists research_run_result_service_role on public.research_run_result;
create policy research_run_result_service_role
    on public.research_run_result
    for all
    to service_role
    using (true)
    with check (true);

drop policy if exists research_run_artifact_service_role on public.research_run_artifact;
create policy research_run_artifact_service_role
    on public.research_run_artifact
    for all
    to service_role
    using (true)
    with check (true);

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
returns table (job jsonb, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_existing public.api_idempotency%rowtype;
    v_job public.research_run%rowtype;
    v_source_sha256 text;
begin
    if p_research_run_id is null or p_workspace_id is null or p_dataset_version_id is null
       or p_created_by is null or p_workflow_id is null
       or length(trim(p_workflow_id)) < 1 or length(p_workflow_id) > 128
       or p_idempotency_key is null or length(trim(p_idempotency_key)) < 1
       or length(p_idempotency_key) > 128
       or p_request_fingerprint is null or p_request_fingerprint !~ '^[0-9a-f]{64}$'
       or p_response_body is null then
        raise exception 'invalid idempotent research run arguments';
    end if;

    select dv.content_sha256
      into v_source_sha256
      from public.dataset_version dv
      join public.dataset d on d.id = dv.dataset_id
     where dv.id = p_dataset_version_id
       and d.workspace_id = p_workspace_id;

    if v_source_sha256 is null then
        raise exception 'dataset version is not owned by workspace';
    end if;

    delete from public.api_idempotency
     where workspace_id = p_workspace_id
       and key = p_idempotency_key
       and expires_at <= clock_timestamp();

    insert into public.api_idempotency(workspace_id, key, request_fingerprint, status_code, response_body)
    values (p_workspace_id, p_idempotency_key, p_request_fingerprint, 202, p_response_body)
    on conflict (workspace_id, key) do nothing
    returning * into v_existing;

    if not found then
        select * into v_existing
          from public.api_idempotency
         where workspace_id = p_workspace_id and key = p_idempotency_key
         for update;

        if v_existing.request_fingerprint <> p_request_fingerprint then
            raise exception 'idempotency key reused with different request' using errcode = '23505';
        end if;

        select * into v_job
          from public.research_run
         where id = (v_existing.response_body->>'id')::uuid
           and workspace_id = p_workspace_id;

        if not found then
            raise exception 'idempotency record references missing research run';
        end if;

        return query select to_jsonb(v_job), true;
        return;
    end if;

    insert into public.research_run(
        id, workspace_id, dataset_version_id, source_dataset_sha256,
        workflow_id, status, created_by
    )
    values (
        p_research_run_id, p_workspace_id, p_dataset_version_id, v_source_sha256,
        p_workflow_id, 'queued', p_created_by
    )
    returning * into v_job;

    return query select to_jsonb(v_job), false;
end;
$$;

revoke all on function public.create_research_run_idempotent(uuid, uuid, uuid, text, uuid, text, text, jsonb)
    from public, anon, authenticated;
grant execute on function public.create_research_run_idempotent(uuid, uuid, uuid, text, uuid, text, text, jsonb)
    to service_role;

drop function if exists public.record_research_run_result(uuid, uuid, uuid, text, text, jsonb, jsonb);

create function public.record_research_run_result(
    p_workspace_id uuid,
    p_research_run_id uuid,
    p_lease_token uuid,
    p_status text,
    p_manifest_sha256 text,
    p_artifacts jsonb,
    p_failures jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_run public.research_run%rowtype;
    v_existing public.research_run_result%rowtype;
    v_result_id uuid;
begin
    if p_workspace_id is null or p_research_run_id is null or p_lease_token is null
       or p_status not in ('SUCCEEDED', 'FAILED')
       or p_manifest_sha256 !~ '^[0-9a-f]{64}$'
       or p_artifacts is null or jsonb_typeof(p_artifacts) <> 'array'
       or p_failures is null or jsonb_typeof(p_failures) <> 'array' then
        raise exception 'invalid research result arguments';
    end if;

    select * into v_run
      from public.research_run
     where id = p_research_run_id
       and workspace_id = p_workspace_id
       and status = 'running'
       and lease_token = p_lease_token
       and lease_expires_at > clock_timestamp()
     for update;

    if not found then
        raise exception 'stale or invalid worker lease';
    end if;

    select * into v_existing
      from public.research_run_result
     where research_run_id = p_research_run_id
     for update;

    if found then
        if v_existing.manifest_sha256 <> p_manifest_sha256 then
            raise exception 'research result already persisted with a different manifest';
        end if;
        return jsonb_build_object('id', v_existing.id, 'replayed', true);
    end if;

    if v_run.source_dataset_sha256 is null then
        raise exception 'research run has no source dataset provenance';
    end if;

    insert into public.research_run_result(
        workspace_id, research_run_id, source_dataset_sha256,
        status, manifest_sha256, failures
    )
    values (
        p_workspace_id, p_research_run_id, v_run.source_dataset_sha256,
        p_status, p_manifest_sha256, p_failures
    )
    returning id into v_result_id;

    insert into public.research_run_artifact(
        workspace_id, research_run_id, artifact_id, kind, content_sha256
    )
    select p_workspace_id, p_research_run_id,
           item->>'artifact_id', item->>'kind', item->>'content_sha256'
      from jsonb_array_elements(p_artifacts) item;

    return jsonb_build_object('id', v_result_id, 'replayed', false);
end;
$$;

revoke all on function public.record_research_run_result(uuid, uuid, uuid, text, text, jsonb, jsonb)
    from public, anon, authenticated;
grant execute on function public.record_research_run_result(uuid, uuid, uuid, text, text, jsonb, jsonb)
    to service_role;
