-- Verify least-privilege defaults for objects created by postgres.
-- All probe objects are rolled back; this test leaves no persistent data or schema.
create extension if not exists pgtap;
begin;

select plan(20);

select ok(
  (select c.relrowsecurity from pg_class c where c.oid = 'public.research_claim'::regclass),
  'research_claim keeps RLS enabled'
);
select ok(
  exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'research_claim' and policyname = 'research_claim_member_select' and cmd = 'SELECT'),
  'research_claim keeps its member-scoped SELECT policy'
);
select ok(not has_table_privilege('anon', 'public.research_claim', 'SELECT'), 'anon cannot select research_claim');
select ok(has_table_privilege('authenticated', 'public.research_claim', 'SELECT'), 'authenticated retains member SELECT on research_claim');
select ok(not has_table_privilege('authenticated', 'public.research_claim', 'INSERT'), 'authenticated cannot insert research_claim directly');
select ok(not has_table_privilege('authenticated', 'public.research_claim', 'UPDATE'), 'authenticated cannot update research_claim directly');
select ok(not has_table_privilege('authenticated', 'public.research_claim', 'DELETE'), 'authenticated cannot delete research_claim directly');
select ok(has_table_privilege('service_role', 'public.research_claim', 'INSERT'), 'service_role retains research_claim writes');

create table public.qros_default_acl_probe_postgres (id bigserial primary key);
create function public.qros_default_acl_probe_postgres()
returns integer
language sql
security definer
set search_path = ''
as $$ select 1 $$;

select ok(not has_table_privilege('anon', 'public.qros_default_acl_probe_postgres', 'SELECT'), 'postgres-created table is not readable by anon');
select ok(not has_table_privilege('authenticated', 'public.qros_default_acl_probe_postgres', 'SELECT'), 'postgres-created table is not readable by authenticated');
select ok(not has_table_privilege('anon', 'public.qros_default_acl_probe_postgres', 'INSERT'), 'postgres-created table is not writable by anon');
select ok(not has_table_privilege('authenticated', 'public.qros_default_acl_probe_postgres', 'INSERT'), 'postgres-created table is not writable by authenticated');
select ok(has_table_privilege('service_role', 'public.qros_default_acl_probe_postgres', 'SELECT'), 'service_role retains access to postgres-created tables');
select ok(has_table_privilege('service_role', 'public.qros_default_acl_probe_postgres', 'INSERT'), 'service_role retains writes to postgres-created tables');
select ok(not has_sequence_privilege('anon', 'public.qros_default_acl_probe_postgres_id_seq', 'USAGE'), 'postgres-created sequence is not usable by anon');
select ok(not has_sequence_privilege('authenticated', 'public.qros_default_acl_probe_postgres_id_seq', 'USAGE'), 'postgres-created sequence is not usable by authenticated');
select ok(has_sequence_privilege('service_role', 'public.qros_default_acl_probe_postgres_id_seq', 'USAGE'), 'service_role retains postgres-created sequence usage');
select ok(not has_function_privilege('anon', 'public.qros_default_acl_probe_postgres()', 'EXECUTE'), 'postgres-created SECURITY DEFINER function is not executable by anon');
select ok(not has_function_privilege('authenticated', 'public.qros_default_acl_probe_postgres()', 'EXECUTE'), 'postgres-created SECURITY DEFINER function is not executable by authenticated');
select ok(has_function_privilege('service_role', 'public.qros_default_acl_probe_postgres()', 'EXECUTE'), 'service_role retains postgres-created function execution');

rollback;
