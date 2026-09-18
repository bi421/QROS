-- Expose immutable result provenance to workspace members while keeping all writes server-only.
grant select on table public.research_run_result, public.research_run_artifact to authenticated;

drop policy if exists research_run_result_member_select on public.research_run_result;
create policy research_run_result_member_select
on public.research_run_result
for select to authenticated
using (
    private.is_workspace_member(workspace_id)
    and exists (
        select 1 from public.research_run rr
        where rr.id = research_run_result.research_run_id
          and rr.workspace_id = research_run_result.workspace_id
    )
);

drop policy if exists research_run_artifact_member_select on public.research_run_artifact;
create policy research_run_artifact_member_select
on public.research_run_artifact
for select to authenticated
using (
    private.is_workspace_member(workspace_id)
    and exists (
        select 1 from public.research_run rr
        where rr.id = research_run_artifact.research_run_id
          and rr.workspace_id = research_run_artifact.workspace_id
    )
);
