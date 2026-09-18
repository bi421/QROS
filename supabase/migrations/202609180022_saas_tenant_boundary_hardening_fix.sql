-- Correct tenant-boundary trigger semantics for nullable usage_event.research_run_id.
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
revoke all on function public.enforce_run_child_workspace() from public, anon, authenticated;
