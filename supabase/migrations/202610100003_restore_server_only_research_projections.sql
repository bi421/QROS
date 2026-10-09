-- Restore the documented server-only boundary for governed research projections.
-- The 20261008050300 hardening migration recreated tenant_id client policies on
-- research_validation and research_finding, conflicting with the server-only contract.
-- This forward-only migration preserves RLS and removes direct client grants/policies.
-- Apply only after staging API/provenance tests pass.

do $$
declare
    target_table text;
begin
    foreach target_table in array array['research_validation', 'research_finding']
    loop
        if not exists (
            select 1 from pg_class c
            where c.oid = format('public.%I', target_table)::regclass
              and c.relrowsecurity
              and c.relforcerowsecurity
        ) then
            raise exception 'server-only reconciliation blocked: RLS is not enabled and forced on %', target_table;
        end if;

        if exists (
            select 1
            from pg_policies p
            where p.schemaname = 'public'
              and p.tablename = target_table
              and p.policyname not in (
                  'tenant_select', 'tenant_insert', 'tenant_update', 'tenant_delete',
                  'research validation client deny', 'research finding client deny'
              )
        ) then
            raise exception 'server-only reconciliation blocked: unexpected policy exists on %', target_table;
        end if;
    end loop;
end
$$;

drop policy if exists tenant_select on public.research_validation;
drop policy if exists tenant_insert on public.research_validation;
drop policy if exists tenant_update on public.research_validation;
drop policy if exists tenant_delete on public.research_validation;
drop policy if exists "research validation client deny" on public.research_validation;

drop policy if exists tenant_select on public.research_finding;
drop policy if exists tenant_insert on public.research_finding;
drop policy if exists tenant_update on public.research_finding;
drop policy if exists tenant_delete on public.research_finding;
drop policy if exists "research finding client deny" on public.research_finding;

revoke all on table public.research_validation, public.research_finding
    from public, anon, authenticated;

create policy "research validation client deny"
    on public.research_validation
    for all
    to anon, authenticated
    using (false)
    with check (false);

create policy "research finding client deny"
    on public.research_finding
    for all
    to anon, authenticated
    using (false)
    with check (false);

do $$
declare
    target_table text;
    client_policy_count integer;
begin
    foreach target_table in array array['research_validation', 'research_finding']
    loop
        if not exists (
            select 1 from pg_class c
            where c.oid = format('public.%I', target_table)::regclass
              and c.relrowsecurity
              and c.relforcerowsecurity
        ) then
            raise exception 'server-only reconciliation postcondition failed: RLS not forced on %', target_table;
        end if;

        select count(*) into client_policy_count
        from pg_policies p
        where p.schemaname = 'public'
          and p.tablename = target_table
          and p.roles && array['anon'::name, 'authenticated'::name, 'public'::name];

        if client_policy_count <> 1 then
            raise exception 'server-only reconciliation postcondition failed: expected one client-deny policy on %, found %',
                target_table, client_policy_count;
        end if;

        if not exists (
            select 1 from pg_policies p
            where p.schemaname = 'public'
              and p.tablename = target_table
              and p.policyname = case
                  when target_table = 'research_validation' then 'research validation client deny'
                  else 'research finding client deny'
              end
              and p.cmd = 'ALL'
              and lower(coalesce(p.qual, '')) = 'false'
              and lower(coalesce(p.with_check, '')) = 'false'
        ) then
            raise exception 'server-only reconciliation postcondition failed: explicit deny policy missing on %', target_table;
        end if;
    end loop;
end
$$;
