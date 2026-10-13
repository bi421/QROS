-- Reconcile RLS if the earlier 20261008050300 migration was applied in an
-- environment before its workspace-scope correction.
--
-- Fail closed: remove only the known legacy policy names. Do not fabricate
-- tenant IDs, loosen RLS, or grant client access. Existing canonical member
-- policies and server-only policies must be present after reconciliation.

DO $$
DECLARE
    target_table text;
    policy_name text;
    remaining_legacy integer;
    missing_contracts text[] := ARRAY[]::text[];
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'artifact',
        'audit_log',
        'dataset',
        'dataset_version',
        'evidence',
        'research_claim',
        'research_finding',
        'research_run',
        'research_validation',
        'subscription',
        'tenant_deletion_tombstone',
        'usage_event',
        'workspace',
        'workspace_member',
        'workspace_retention_policy'
    ]
    LOOP
        FOREACH policy_name IN ARRAY ARRAY[
            'tenant_select',
            'tenant_insert',
            'tenant_update',
            'tenant_delete'
        ]
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', policy_name, target_table);
        END LOOP;
    END LOOP;

    -- Required workspace-membership policies must remain after legacy cleanup.
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workspace' AND policyname='workspace_member_select') THEN missing_contracts := array_append(missing_contracts, 'workspace.workspace_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='workspace_member' AND policyname='workspace_member_self_select') THEN missing_contracts := array_append(missing_contracts, 'workspace_member.workspace_member_self_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='subscription' AND policyname='subscription_member_select') THEN missing_contracts := array_append(missing_contracts, 'subscription.subscription_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='dataset' AND policyname='dataset_member_select') THEN missing_contracts := array_append(missing_contracts, 'dataset.dataset_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='dataset_version' AND policyname='dataset_version_member_select') THEN missing_contracts := array_append(missing_contracts, 'dataset_version.dataset_version_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run' AND policyname='research_run_member_select') THEN missing_contracts := array_append(missing_contracts, 'research_run.research_run_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='artifact' AND policyname='artifact_member_select') THEN missing_contracts := array_append(missing_contracts, 'artifact.artifact_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='evidence' AND policyname='evidence_member_select') THEN missing_contracts := array_append(missing_contracts, 'evidence.evidence_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='usage_event' AND policyname='usage_event_member_select') THEN missing_contracts := array_append(missing_contracts, 'usage_event.usage_event_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='audit_log' AND policyname='audit_log_member_select') THEN missing_contracts := array_append(missing_contracts, 'audit_log.audit_log_member_select'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_claim' AND policyname='research_claim_member_select') THEN missing_contracts := array_append(missing_contracts, 'research_claim.research_claim_member_select'); END IF;

    -- Server-only research projections must retain an explicit client deny.
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_validation' AND policyname='research validation client deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing_contracts := array_append(missing_contracts, 'research_validation client deny'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_finding' AND policyname='research finding client deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing_contracts := array_append(missing_contracts, 'research_finding client deny'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='api_idempotency' AND policyname='api_idempotency_no_client_access' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing_contracts := array_append(missing_contracts, 'api_idempotency client deny'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='billing_event' AND policyname='billing_event_no_client_access' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing_contracts := array_append(missing_contracts, 'billing_event client deny'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='audit_event' AND policyname='audit_event_client_deny' AND cmd='ALL' AND lower(coalesce(qual,''))='false' AND lower(coalesce(with_check,''))='false') THEN missing_contracts := array_append(missing_contracts, 'audit_event client deny'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run_result' AND policyname='research_run_result_service_role' AND roles::text='{service_role}') THEN missing_contracts := array_append(missing_contracts, 'research_run_result service-role-only policy'); END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='research_run_artifact' AND policyname='research_run_artifact_service_role' AND roles::text='{service_role}') THEN missing_contracts := array_append(missing_contracts, 'research_run_artifact service-role-only policy'); END IF;

    -- These retention tables are server-only: no client policy is allowed.
    IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename IN ('workspace_retention_policy','tenant_deletion_tombstone') AND roles && ARRAY['anon'::name,'authenticated'::name,'public'::name]) THEN
        missing_contracts := array_append(missing_contracts, 'retention tables must remain server-only');
    END IF;

    SELECT count(*) INTO remaining_legacy
      FROM pg_policies
     WHERE schemaname='public'
       AND tablename IN (
          'artifact','audit_log','dataset','dataset_version','evidence',
          'research_claim','research_finding','research_run','research_validation',
          'subscription','tenant_deletion_tombstone','usage_event','workspace',
          'workspace_member','workspace_retention_policy'
       )
       AND policyname IN ('tenant_select','tenant_insert','tenant_update','tenant_delete');

    IF remaining_legacy <> 0 THEN
        RAISE EXCEPTION 'RLS reconciliation failed: % legacy policy names remain', remaining_legacy;
    END IF;

    IF cardinality(missing_contracts) > 0 THEN
        RAISE EXCEPTION 'RLS reconciliation blocked; required canonical policy contracts missing: %', array_to_string(missing_contracts, ', ');
    END IF;
END
$$;
