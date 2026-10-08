-- QROS SaaS RLS performance hardening.
-- Preserve tenant isolation while using initplan-safe auth.jwt() evaluation.
-- Keep server-only tables client-denied; do not add client policies to those tables.

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'artifact','audit_log','dataset','dataset_version','evidence',
    'research_claim','research_finding','research_run','research_validation',
    'subscription','tenant_deletion_tombstone','usage_event','workspace',
    'workspace_member','workspace_retention_policy'
  ]
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_select ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_insert ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_update ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_delete ON public.%I', t);

    EXECUTE format('CREATE POLICY tenant_select ON public.%I FOR SELECT TO authenticated USING ((select auth.jwt() ->> ''tenant_id'') = tenant_id::text)', t);
    EXECUTE format('CREATE POLICY tenant_insert ON public.%I FOR INSERT TO authenticated WITH CHECK ((select auth.jwt() ->> ''tenant_id'') = tenant_id::text)', t);
    EXECUTE format('CREATE POLICY tenant_update ON public.%I FOR UPDATE TO authenticated USING ((select auth.jwt() ->> ''tenant_id'') = tenant_id::text) WITH CHECK ((select auth.jwt() ->> ''tenant_id'') = tenant_id::text)', t);
    EXECUTE format('CREATE POLICY tenant_delete ON public.%I FOR DELETE TO authenticated USING ((select auth.jwt() ->> ''tenant_id'') = tenant_id::text)', t);
  END LOOP;

  DROP POLICY IF EXISTS qros_api_rate_limit_client_delete_deny ON public.api_rate_limit;
  DROP POLICY IF EXISTS qros_api_rate_limit_client_insert_deny ON public.api_rate_limit;
  DROP POLICY IF EXISTS qros_api_rate_limit_client_select_deny ON public.api_rate_limit;
  DROP POLICY IF EXISTS qros_api_rate_limit_client_update_deny ON public.api_rate_limit;
END $$;

CREATE INDEX IF NOT EXISTS idx_billing_event_workspace_id
  ON public.billing_event (workspace_id);

CREATE INDEX IF NOT EXISTS idx_research_finding_research_run_id
  ON public.research_finding (research_run_id);

CREATE INDEX IF NOT EXISTS idx_research_finding_validation_id
  ON public.research_finding (validation_id);

CREATE INDEX IF NOT EXISTS idx_research_validation_research_run_id
  ON public.research_validation (research_run_id);
