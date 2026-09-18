-- Enforce tenant identity consistency across relational boundaries.
-- RLS protects visibility; these triggers prevent cross-workspace references.

create or replace function public.enforce_research_run_workspace()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  if not exists (
    select 1 from public.dataset_version dv
    join public.dataset d on d.id = dv.dataset_id
    where dv.id = new.dataset_version_id and d.workspace_id = new.workspace_id
  ) then raise exception 'research run workspace mismatch'; end if;
  return new;
end;
$$;

create or replace function public.enforce_run_child_workspace()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  if new.research_run_id is null then return new; end if;
  if not exists (
    select 1 from public.research_run rr
    where rr.id = new.research_run_id and rr.workspace_id = new.workspace_id
  ) then raise exception 'research child workspace mismatch'; end if;
  return new;
end;
$$;

drop trigger if exists trg_research_run_workspace on public.research_run;
create trigger trg_research_run_workspace before insert or update of workspace_id, dataset_version_id on public.research_run
for each row execute function public.enforce_research_run_workspace();

drop trigger if exists trg_artifact_workspace on public.artifact;
create trigger trg_artifact_workspace before insert or update of workspace_id, research_run_id on public.artifact
for each row execute function public.enforce_run_child_workspace();

drop trigger if exists trg_evidence_workspace on public.evidence;
create trigger trg_evidence_workspace before insert or update of workspace_id, research_run_id on public.evidence
for each row execute function public.enforce_run_child_workspace();

drop trigger if exists trg_usage_event_workspace on public.usage_event;
create trigger trg_usage_event_workspace before insert or update of workspace_id, research_run_id on public.usage_event
for each row execute function public.enforce_run_child_workspace();

revoke all on function public.enforce_research_run_workspace() from public, anon, authenticated;
revoke all on function public.enforce_run_child_workspace() from public, anon, authenticated;
