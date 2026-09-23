-- Forward-only RLS hardening for the QROS SaaS tenant boundary.
--
-- QROS uses workspace_id as the durable tenant key. Authorization is derived
-- from auth.uid() through private.is_workspace_member(workspace_id), rather
-- than trusting a client-supplied tenant_id JWT claim.
--
-- Browser writes remain intentionally disabled: the application server is the
-- sole write path. Explicit deny policies make that contract auditable and
-- fail-closed even if table grants are changed later.

alter table public.workspace force row level security;
alter table public.workspace_member force row level security;
alter table public.subscription force row level security;
alter table public.dataset force row level security;
alter table public.dataset_version force row level security;
alter table public.research_run force row level security;
alter table public.research_run_result force row level security;
alter table public.research_run_artifact force row level security;
alter table public.artifact force row level security;
alter table public.evidence force row level security;
alter table public.usage_event force row level security;
alter table public.audit_log force row level security;
alter table public.api_idempotency force row level security;
alter table public.api_rate_limit force row level security;
alter table public.billing_event force row level security;
alter table public.audit_event force row level security;
alter table public.retention_deletion_operation force row level security;
alter table public.research_claim force row level security;
alter table public.research_validation force row level security;
alter table public.research_finding force row level security;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'workspace',
        'workspace_member',
        'subscription',
        'dataset',
        'dataset_version',
        'research_run',
        'artifact',
        'evidence',
        'usage_event',
        'audit_log',
        'research_claim'
    ]
    loop
        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_insert_deny', table_name);
        execute format('create policy %I on public.%I for insert to anon, authenticated with check (false)',
            'qros_' || table_name || '_client_insert_deny', table_name);

        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_update_deny', table_name);
        execute format('create policy %I on public.%I for update to anon, authenticated using (false) with check (false)',
            'qros_' || table_name || '_client_update_deny', table_name);

        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_delete_deny', table_name);
        execute format('create policy %I on public.%I for delete to anon, authenticated using (false)',
            'qros_' || table_name || '_client_delete_deny', table_name);
    end loop;
end
$$;

do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'research_run_result',
        'research_run_artifact',
        'research_validation',
        'research_finding',
        'api_idempotency',
        'api_rate_limit',
        'billing_event',
        'audit_event',
        'retention_deletion_operation'
    ]
    loop
        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_select_deny', table_name);
        execute format('create policy %I on public.%I for select to anon, authenticated using (false)',
            'qros_' || table_name || '_client_select_deny', table_name);

        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_insert_deny', table_name);
        execute format('create policy %I on public.%I for insert to anon, authenticated with check (false)',
            'qros_' || table_name || '_client_insert_deny', table_name);

        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_update_deny', table_name);
        execute format('create policy %I on public.%I for update to anon, authenticated using (false) with check (false)',
            'qros_' || table_name || '_client_update_deny', table_name);

        execute format('drop policy if exists %I on public.%I',
            'qros_' || table_name || '_client_delete_deny', table_name);
        execute format('create policy %I on public.%I for delete to anon, authenticated using (false)',
            'qros_' || table_name || '_client_delete_deny', table_name);
    end loop;
end
$$;

comment on policy qros_dataset_client_insert_deny on public.dataset
is 'Server-only write boundary; tenant authorization is resolved from auth.uid() via workspace membership.';

comment on policy qros_research_run_client_update_deny on public.research_run
is 'Server-only write boundary; UPDATE cannot rebind workspace_id across tenants.';

comment on policy qros_research_finding_client_select_deny on public.research_finding
is 'Server-owned governed finding projection; browser access is fail-closed.';
