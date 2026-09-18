-- Fenced worker leases prevent concurrent execution and allow stale work recovery.
alter table public.research_run
    add column if not exists lease_token uuid,
    add column if not exists lease_owner text,
    add column if not exists lease_expires_at timestamptz;

create index if not exists idx_research_run_lease_expiry
    on public.research_run(lease_expires_at)
    where status = 'running';

create or replace function public.claim_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_lease_owner text,
    p_lease_seconds integer
)
returns table (
    id uuid,
    workspace_id uuid,
    dataset_version_id uuid,
    workflow_id text,
    status text,
    created_by uuid,
    lease_token uuid
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    if p_lease_seconds < 1 or p_lease_seconds > 86400
       or p_lease_owner is null or length(trim(p_lease_owner)) < 1
       or length(p_lease_owner) > 128 then
        raise exception 'invalid worker lease arguments';
    end if;

    return query
    update public.research_run rr
       set status = 'running',
           attempt_count = rr.attempt_count + 1,
           started_at = coalesce(rr.started_at, clock_timestamp()),
           lease_token = gen_random_uuid(),
           lease_owner = trim(p_lease_owner),
           lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
     where rr.id = p_research_run_id
       and rr.workspace_id = p_workspace_id
       and (
           rr.status = 'queued'
           or (rr.status = 'running' and rr.lease_expires_at <= clock_timestamp())
       )
    returning rr.id, rr.workspace_id, rr.dataset_version_id, rr.workflow_id,
              rr.status, rr.created_by, rr.lease_token;
end;
$$;

revoke all on function public.claim_research_run(uuid, uuid, text, integer)
    from public, anon, authenticated;
grant execute on function public.claim_research_run(uuid, uuid, text, integer)
    to service_role;

create or replace function public.finish_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_lease_token uuid,
    p_target_status text,
    p_error_code text default null
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_updated integer;
begin
    if p_target_status not in ('succeeded', 'failed') then
        raise exception 'invalid terminal research status';
    end if;

    update public.research_run
       set status = p_target_status,
           error_code = p_error_code,
           finished_at = clock_timestamp(),
           lease_token = null,
           lease_owner = null,
           lease_expires_at = null
     where id = p_research_run_id
       and workspace_id = p_workspace_id
       and status = 'running'
       and lease_token = p_lease_token;

    get diagnostics v_updated = row_count;
    return v_updated = 1;
end;
$$;

revoke all on function public.finish_research_run(uuid, uuid, uuid, text, text)
    from public, anon, authenticated;
grant execute on function public.finish_research_run(uuid, uuid, uuid, text, text)
    to service_role;

comment on table public.research_run is
    'Tenant-scoped asynchronous scientific execution record with fenced worker leases for stale-work recovery.';
