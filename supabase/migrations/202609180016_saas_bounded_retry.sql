-- Bounded retry policy for durable research jobs.
-- A lease may be reclaimed only while attempts remain; otherwise the job
-- becomes a terminal failure instead of being retried indefinitely.

alter table public.research_run
    add column if not exists max_attempts integer not null default 3;

alter table public.research_run
    drop constraint if exists research_run_max_attempts_check;

alter table public.research_run
    add constraint research_run_max_attempts_check
    check (max_attempts between 1 and 100);

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
    lease_token uuid,
    attempt_count integer,
    max_attempts integer,
    error_code text
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_updated integer;
begin
    if p_lease_seconds < 1 or p_lease_seconds > 86400
       or p_lease_owner is null or length(trim(p_lease_owner)) < 1
       or length(p_lease_owner) > 128 then
        raise exception 'invalid worker lease arguments';
    end if;

    update public.research_run rr
       set status = 'failed',
           error_code = 'max_attempts_exceeded',
           finished_at = clock_timestamp(),
           lease_token = null,
           lease_owner = null,
           lease_expires_at = null
     where rr.id = p_research_run_id
       and rr.workspace_id = p_workspace_id
       and rr.attempt_count >= rr.max_attempts
       and (
           rr.status = 'queued'
           or (rr.status = 'running' and rr.lease_expires_at <= clock_timestamp())
       );

    get diagnostics v_updated = row_count;

    if v_updated > 0 then
        return;
    end if;

    return query
    update public.research_run rr
       set status = 'running',
           attempt_count = rr.attempt_count + 1,
           started_at = coalesce(rr.started_at, clock_timestamp()),
           error_code = null,
           lease_token = gen_random_uuid(),
           lease_owner = trim(p_lease_owner),
           lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
     where rr.id = p_research_run_id
       and rr.workspace_id = p_workspace_id
       and rr.attempt_count < rr.max_attempts
       and (
           rr.status = 'queued'
           or (rr.status = 'running' and rr.lease_expires_at <= clock_timestamp())
       )
    returning rr.id, rr.workspace_id, rr.dataset_version_id, rr.workflow_id,
              rr.status, rr.created_by, rr.lease_token,
              rr.attempt_count, rr.max_attempts, rr.error_code;
end;
$$;

revoke all on function public.claim_research_run(uuid, uuid, text, integer)
    from public, anon, authenticated;
grant execute on function public.claim_research_run(uuid, uuid, text, integer)
    to service_role;

comment on table public.research_run is
    'Tenant-scoped asynchronous scientific execution record with fenced worker leases, bounded stale-work recovery, and terminal retry exhaustion.';
