-- Forward-only restoration of the tracked workspace RLS contract.
-- The 20261008050300 migration replaced workspace-member policies with
-- tenant_id JWT policies. This migration restores policy definitions from the
-- tracked canonical migrations and keeps server-owned projections client-denied.
-- Apply to staging first; production apply remains gated on provenance parity.

DO $$
DECLARE t text;
BEGIN
  IF to_regprocedure('private.is_workspace_member(uuid)') IS NULL THEN
    RAISE EXCEPTION 'workspace RLS repair blocked: private.is_workspace_member(uuid) missing';
  END IF;
  FOREACH t IN ARRAY ARRAY[
    'artifact','audit_log','dataset','dataset_version','evidence','research_claim',
    'research_finding','research_run','research_validation','subscription',
    'tenant_deletion_tombstone','usage_event','workspace','workspace_member',
    'workspace_retention_policy'
  ] LOOP
    IF to_regclass(format('public.%I', t)) IS NULL THEN
      RAISE EXCEPTION 'workspace RLS repair blocked: public.% missing', t;
    END IF;
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_select ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_insert ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_update ON public.%I', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_delete ON public.%I', t);
  END LOOP;
END
$$;

-- Restore membership-based reads using the tracked private helper.
DROP POLICY IF EXISTS workspace_member_select ON public.workspace;
CREATE POLICY workspace_member_select ON public.workspace
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(id)));

DROP POLICY IF EXISTS workspace_member_self_select ON public.workspace_member;
CREATE POLICY workspace_member_self_select ON public.workspace_member
  FOR SELECT TO authenticated
  USING (user_id = (SELECT auth.uid()) OR (SELECT private.is_workspace_member(workspace_id)));

DROP POLICY IF EXISTS subscription_member_select ON public.subscription;
CREATE POLICY subscription_member_select ON public.subscription
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));

DROP POLICY IF EXISTS dataset_member_select ON public.dataset;
CREATE POLICY dataset_member_select ON public.dataset
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));

-- Keep attempted client UPDATEs visible to RLS long enough for WITH CHECK to
-- reject them with 42501, while never permitting the write itself. This also
-- makes workspace_id rebind attempts fail loudly instead of returning zero rows.
DROP POLICY IF EXISTS dataset_member_update_guard ON public.dataset;
CREATE POLICY dataset_member_update_guard ON public.dataset
  FOR UPDATE TO authenticated
  USING ((SELECT private.is_workspace_member(workspace_id)))
  WITH CHECK (false);

DROP POLICY IF EXISTS dataset_version_member_select ON public.dataset_version;
CREATE POLICY dataset_version_member_select ON public.dataset_version
  FOR SELECT TO authenticated USING (
    EXISTS (SELECT 1 FROM public.dataset d
      WHERE d.id = dataset_version.dataset_id
        AND (SELECT private.is_workspace_member(d.workspace_id)))
  );

DROP POLICY IF EXISTS research_run_member_select ON public.research_run;
CREATE POLICY research_run_member_select ON public.research_run
  FOR SELECT TO authenticated USING (
    (SELECT private.is_workspace_member(workspace_id))
    AND EXISTS (
      SELECT 1 FROM public.dataset_version dv
      JOIN public.dataset d ON d.id = dv.dataset_id
      WHERE dv.id = research_run.dataset_version_id
        AND d.workspace_id = research_run.workspace_id)
  );

DROP POLICY IF EXISTS artifact_member_select ON public.artifact;
CREATE POLICY artifact_member_select ON public.artifact
  FOR SELECT TO authenticated USING (
    (SELECT private.is_workspace_member(workspace_id))
    AND EXISTS (SELECT 1 FROM public.research_run rr
      WHERE rr.id = artifact.research_run_id
        AND rr.workspace_id = artifact.workspace_id)
  );

DROP POLICY IF EXISTS evidence_member_select ON public.evidence;
CREATE POLICY evidence_member_select ON public.evidence
  FOR SELECT TO authenticated USING (
    (SELECT private.is_workspace_member(workspace_id))
    AND EXISTS (SELECT 1 FROM public.research_run rr
      WHERE rr.id = evidence.research_run_id
        AND rr.workspace_id = evidence.workspace_id)
    AND (artifact_id IS NULL OR EXISTS (
      SELECT 1 FROM public.artifact a
      WHERE a.id = evidence.artifact_id
        AND a.workspace_id = evidence.workspace_id
        AND a.research_run_id = evidence.research_run_id))
  );

DROP POLICY IF EXISTS usage_event_member_select ON public.usage_event;
CREATE POLICY usage_event_member_select ON public.usage_event
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));

DROP POLICY IF EXISTS audit_log_member_select ON public.audit_log;
CREATE POLICY audit_log_member_select ON public.audit_log
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));

DROP POLICY IF EXISTS research_claim_member_select ON public.research_claim;
CREATE POLICY research_claim_member_select ON public.research_claim
  FOR SELECT TO authenticated USING ((SELECT private.is_workspace_member(workspace_id)));

-- Server-owned projections must never be directly accessible to browser roles.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'api_idempotency','billing_event','audit_event','research_finding',
    'research_validation','research_run_result','research_run_artifact'
  ] LOOP
    IF to_regclass(format('public.%I', t)) IS NULL THEN
      RAISE EXCEPTION 'workspace RLS repair blocked: server-only table public.% missing', t;
    END IF;
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', t);
  END LOOP;
END
$$;

DROP POLICY IF EXISTS api_idempotency_no_client_access ON public.api_idempotency;
CREATE POLICY api_idempotency_no_client_access ON public.api_idempotency
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS billing_event_no_client_access ON public.billing_event;
CREATE POLICY billing_event_no_client_access ON public.billing_event
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS audit_event_client_deny ON public.audit_event;
CREATE POLICY audit_event_client_deny ON public.audit_event
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS "research finding client deny" ON public.research_finding;
CREATE POLICY "research finding client deny" ON public.research_finding
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS "research validation client deny" ON public.research_validation;
CREATE POLICY "research validation client deny" ON public.research_validation
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS research_run_result_no_client_access ON public.research_run_result;
CREATE POLICY research_run_result_no_client_access ON public.research_run_result
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);
DROP POLICY IF EXISTS research_run_artifact_no_client_access ON public.research_run_artifact;
CREATE POLICY research_run_artifact_no_client_access ON public.research_run_artifact
  FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);

DROP POLICY IF EXISTS research_run_result_service_role ON public.research_run_result;
CREATE POLICY research_run_result_service_role ON public.research_run_result
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS research_run_artifact_service_role ON public.research_run_artifact;
CREATE POLICY research_run_artifact_service_role ON public.research_run_artifact
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Fail closed: do not silently leave any legacy tenant policy behind.
DO $$
DECLARE n integer; missing text[] := ARRAY[]::text[];
BEGIN
  SELECT count(*) INTO n FROM pg_policies
  WHERE schemaname='public'
    AND tablename IN (
      'artifact','audit_log','dataset','dataset_version','evidence','research_claim',
      'research_finding','research_run','research_validation','subscription',
      'tenant_deletion_tombstone','usage_event','workspace','workspace_member',
      'workspace_retention_policy')
    AND policyname IN ('tenant_select','tenant_insert','tenant_update','tenant_delete');
  IF n <> 0 THEN
    RAISE EXCEPTION 'workspace RLS repair failed: % legacy tenant policies remain', n;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workspace' AND policyname='workspace_member_select') THEN missing := array_append(missing,'workspace.workspace_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workspace_member' AND policyname='workspace_member_self_select') THEN missing := array_append(missing,'workspace_member.workspace_member_self_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='subscription' AND policyname='subscription_member_select') THEN missing := array_append(missing,'subscription.subscription_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='dataset' AND policyname='dataset_member_select') THEN missing := array_append(missing,'dataset.dataset_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='dataset_version' AND policyname='dataset_version_member_select') THEN missing := array_append(missing,'dataset_version.dataset_version_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run' AND policyname='research_run_member_select') THEN missing := array_append(missing,'research_run.research_run_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='artifact' AND policyname='artifact_member_select') THEN missing := array_append(missing,'artifact.artifact_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='evidence' AND policyname='evidence_member_select') THEN missing := array_append(missing,'evidence.evidence_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='usage_event' AND policyname='usage_event_member_select') THEN missing := array_append(missing,'usage_event.usage_event_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='audit_log' AND policyname='audit_log_member_select') THEN missing := array_append(missing,'audit_log.audit_log_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_claim' AND policyname='research_claim_member_select') THEN missing := array_append(missing,'research_claim.research_claim_member_select'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_validation' AND policyname='research validation client deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing := array_append(missing,'research_validation client deny'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_finding' AND policyname='research finding client deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing := array_append(missing,'research_finding client deny'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='api_idempotency' AND policyname='api_idempotency_no_client_access' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing := array_append(missing,'api_idempotency client deny'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='billing_event' AND policyname='billing_event_no_client_access' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing := array_append(missing,'billing_event client deny'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='audit_event' AND policyname='audit_event_client_deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing := array_append(missing,'audit_event client deny'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run_result' AND policyname='research_run_result_service_role' AND roles::text='{service_role}') THEN missing := array_append(missing,'research_run_result service-role policy'); END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run_artifact' AND policyname='research_run_artifact_service_role' AND roles::text='{service_role}') THEN missing := array_append(missing,'research_run_artifact service-role policy'); END IF;

  IF cardinality(missing) > 0 THEN
    RAISE EXCEPTION 'workspace RLS repair blocked; missing policy contracts: %', array_to_string(missing, ', ');
  END IF;
END
$$;
