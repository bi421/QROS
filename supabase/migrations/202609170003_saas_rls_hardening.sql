-- Defense-in-depth for the SaaS Data API.
-- Browser clients may read tenant-owned data through RLS, but all writes are
-- performed by the server-side application using its privileged client.

revoke all on table
    public.workspace,
    public.workspace_member,
    public.subscription,
    public.dataset,
    public.dataset_version,
    public.research_run,
    public.artifact,
    public.evidence,
    public.usage_event,
    public.audit_log
from anon;

revoke all on table
    public.workspace,
    public.workspace_member,
    public.subscription,
    public.dataset,
    public.dataset_version,
    public.research_run,
    public.artifact,
    public.evidence,
    public.usage_event,
    public.audit_log
from authenticated;

grant select on table
    public.workspace,
    public.workspace_member,
    public.subscription,
    public.dataset,
    public.dataset_version,
    public.research_run,
    public.artifact,
    public.evidence,
    public.usage_event,
    public.audit_log
to authenticated;

drop policy if exists research_run_member_all on public.research_run;
create policy research_run_member_select on public.research_run
for select to authenticated
using (
    public.is_workspace_member(workspace_id)
    and exists (
        select 1
        from public.dataset_version dv
        join public.dataset d on d.id = dv.dataset_id
        where dv.id = research_run.dataset_version_id
          and d.workspace_id = research_run.workspace_id
    )
);

-- Browser clients do not receive INSERT/UPDATE/DELETE grants, so the server
-- remains the only write path for research runs.

drop policy if exists artifact_member_all on public.artifact;
create policy artifact_member_select on public.artifact
for select to authenticated
using (
    public.is_workspace_member(workspace_id)
    and exists (
        select 1
        from public.research_run rr
        where rr.id = artifact.research_run_id
          and rr.workspace_id = artifact.workspace_id
    )
);

drop policy if exists evidence_member_all on public.evidence;
create policy evidence_member_select on public.evidence
for select to authenticated
using (
    public.is_workspace_member(workspace_id)
    and exists (
        select 1
        from public.research_run rr
        where rr.id = evidence.research_run_id
          and rr.workspace_id = evidence.workspace_id
    )
    and (
        artifact_id is null
        or exists (
            select 1
            from public.artifact a
            where a.id = evidence.artifact_id
              and a.workspace_id = evidence.workspace_id
              and a.research_run_id = evidence.research_run_id
        )
    )
);

-- Dataset rows are only readable by workspace members. Dataset versions are
-- readable only through a dataset belonging to the same workspace.
drop policy if exists dataset_member_all on public.dataset;
create policy dataset_member_select on public.dataset
for select to authenticated
using (public.is_workspace_member(workspace_id));

drop policy if exists dataset_version_member_all on public.dataset_version;
create policy dataset_version_member_select on public.dataset_version
for select to authenticated
using (
    exists (
        select 1
        from public.dataset d
        where d.id = dataset_version.dataset_id
          and public.is_workspace_member(d.workspace_id)
    )
);
