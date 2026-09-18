-- Result provenance is an internal/server-owned boundary.
-- Clients consume research results through the versioned API, not PostgREST/GraphQL.
revoke select on table public.research_run_result, public.research_run_artifact from authenticated;
drop policy if exists research_run_result_member_select on public.research_run_result;
drop policy if exists research_run_artifact_member_select on public.research_run_artifact;
