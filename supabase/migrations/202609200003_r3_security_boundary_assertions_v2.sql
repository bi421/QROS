-- R3 release gate: fail deployment if QROS SaaS security boundaries drift.
-- This migration contains assertions only; it does not change runtime behavior.

do $$
declare
    missing_rls text;
    exposed_grants text;
    unsafe_definers text;
begin
    select string_agg(c.relname, ', ' order by c.relname)
      into missing_rls
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r'
      and c.relname in ('workspace','workspace_member','subscription','dataset','dataset_version','research_run','research_run_result','research_run_artifact','artifact','evidence','usage_event','audit_log','api_rate_limit','billing_event')
      and not c.relrowsecurity;
    if missing_rls is not null then raise exception 'R3 security gate: RLS disabled on: %', missing_rls; end if;

    select string_agg(format('%s.%s:%s:%s', table_schema, table_name, grantee, privilege_type), ', ' order by table_name, grantee, privilege_type)
      into exposed_grants
    from information_schema.role_table_grants
    where table_schema='public' and grantee in ('anon','authenticated')
      and table_name in ('workspace','workspace_member','subscription','dataset','dataset_version','research_run','research_run_result','research_run_artifact','artifact','evidence','usage_event','audit_log','api_rate_limit','billing_event');
    if exposed_grants is not null then raise exception 'R3 security gate: client table grants detected: %', exposed_grants; end if;

    select string_agg(format('%s.%s', n.nspname, p.proname), ', ' order by n.nspname, p.proname)
      into unsafe_definers
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where p.prosecdef
      and n.nspname in ('public','private')
      and not ('search_path=""' = any(coalesce(p.proconfig, ARRAY[]::text[])));
    if unsafe_definers is not null then raise exception 'R3 security gate: SECURITY DEFINER function without pinned empty search_path: %', unsafe_definers; end if;

    if not exists (select 1 from storage.buckets where id='qros-datasets' and public=false)
      then raise exception 'R3 security gate: qros-datasets bucket must remain private'; end if;

    if not exists (select 1 from pg_policies where schemaname='public' and tablename='api_rate_limit' and policyname='api_rate_limit_no_client_access' and qual='false' and with_check='false')
      then raise exception 'R3 security gate: api_rate_limit explicit deny policy missing'; end if;

    if not exists (select 1 from pg_policies where schemaname='public' and tablename='billing_event' and policyname='billing_event_no_client_access' and qual='false' and with_check='false')
      then raise exception 'R3 security gate: billing_event explicit deny policy missing'; end if;
end $$;
