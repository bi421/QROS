-- Pin every QROS SECURITY DEFINER function to an empty search_path.
-- Function bodies already schema-qualify application relations; built-ins resolve
-- through pg_catalog, while an empty path prevents caller-controlled shadowing.
alter function private.is_workspace_member(uuid) set search_path = '';
alter function public.claim_research_run(uuid, uuid, text, integer) set search_path = '';
alter function public.consume_api_rate_limit(text, integer, integer) set search_path = '';
alter function public.create_research_run_idempotent(uuid, uuid, uuid, text, uuid, text, text, jsonb) set search_path = '';
alter function public.enforce_research_run_workspace() set search_path = '';
alter function public.enforce_run_child_workspace() set search_path = '';
alter function public.enqueue_research_run(uuid, uuid) set search_path = '';
alter function public.finish_research_run(uuid, uuid, uuid, text, text) set search_path = '';
alter function public.record_research_run_result(uuid, uuid, uuid, text, text, jsonb, jsonb) set search_path = '';
alter function public.renew_research_run(uuid, uuid, uuid, integer) set search_path = '';

comment on function public.enqueue_research_run(uuid, uuid) is
'Server-only tenant-scoped queue enqueue primitive; SECURITY DEFINER uses an empty search_path and schema-qualified application/queue relations.';
