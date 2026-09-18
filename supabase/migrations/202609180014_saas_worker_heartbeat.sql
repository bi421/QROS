-- Renewable fenced worker leases prevent long-running jobs from expiring mid-execution.
create or replace function public.renew_research_run(
    p_research_run_id uuid,
    p_workspace_id uuid,
    p_lease_token uuid,
    p_lease_seconds integer
)
returns table (
    id uuid,
    workspace_id uuid,
    dataset_version_id uuid,
    workflow_id text,
    status text,
    created_by uuid
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
    if p_lease_seconds < 1 or p_lease_seconds > 86400 then
        raise exception 'invalid worker lease duration';
    end if;

    return query
    update public.research_run rr
       set lease_expires_at = clock_timestamp() + make_interval(secs => p_lease_seconds)
     where rr.id = p_research_run_id
       and rr.workspace_id = p_workspace_id
       and rr.status = 'running'
       and rr.lease_token = p_lease_token
       and rr.lease_expires_at > clock_timestamp()
    returning rr.id, rr.workspace_id, rr.dataset_version_id, rr.workflow_id,
              rr.status, rr.created_by;
end;
$$;

revoke all on function public.renew_research_run(uuid, uuid, uuid, integer)
    from public, anon, authenticated;
grant execute on function public.renew_research_run(uuid, uuid, uuid, integer)
    to service_role;
