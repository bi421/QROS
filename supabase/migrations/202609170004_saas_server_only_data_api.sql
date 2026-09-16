-- The QROS browser surface is the application API, not PostgREST directly.
-- Keep tenant tables unreachable through the public Data API and retain RLS as
-- defense-in-depth for any future authenticated database access.

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

create schema if not exists private;

create or replace function private.is_workspace_member(target_workspace uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from public.workspace_member wm
        where wm.workspace_id = target_workspace
          and wm.user_id = (select auth.uid())
    );
$$;

revoke all on function public.is_workspace_member(uuid) from public;
drop function if exists public.is_workspace_member(uuid);
revoke all on function private.is_workspace_member(uuid) from public;
grant execute on function private.is_workspace_member(uuid) to authenticated;

-- Rebind policies to the non-exposed helper schema.
alter policy workspace_member_select on public.workspace
    using ((select private.is_workspace_member(id)));

alter policy workspace_member_self_select on public.workspace_member
    using (user_id = (select auth.uid()) or (select private.is_workspace_member(workspace_id)));

alter policy subscription_member_select on public.subscription
    using ((select private.is_workspace_member(workspace_id)));

alter policy dataset_member_select on public.dataset
    using ((select private.is_workspace_member(workspace_id)));

alter policy dataset_version_member_select on public.dataset_version
    using (
        exists (
            select 1
            from public.dataset d
            where d.id = dataset_version.dataset_id
              and (select private.is_workspace_member(d.workspace_id))
        )
    );

alter policy research_run_member_select on public.research_run
    using (
        (select private.is_workspace_member(workspace_id))
        and exists (
            select 1
            from public.dataset_version dv
            join public.dataset d on d.id = dv.dataset_id
            where dv.id = research_run.dataset_version_id
              and d.workspace_id = research_run.workspace_id
        )
    );

alter policy artifact_member_select on public.artifact
    using (
        (select private.is_workspace_member(workspace_id))
        and exists (
            select 1
            from public.research_run rr
            where rr.id = artifact.research_run_id
              and rr.workspace_id = artifact.workspace_id
        )
    );

alter policy evidence_member_select on public.evidence
    using (
        (select private.is_workspace_member(workspace_id))
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

alter policy usage_event_member_select on public.usage_event
    using ((select private.is_workspace_member(workspace_id)));

alter policy audit_log_member_select on public.audit_log
    using ((select private.is_workspace_member(workspace_id)));
