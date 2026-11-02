-- QROS application data is server-side by default. Browser-readable surfaces
-- must receive explicit grants and RLS policies. Keep service_role defaults
-- because the API and worker use this server-only principal; it is never
-- shipped to browser clients. Apply to both public-object owner roles.

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;

-- research_claim is the one existing public table with browser grants. Keep
-- member-scoped SELECT only; writes are performed by the server-side API.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'research_claim'
      AND c.relrowsecurity
  ) THEN
    RAISE EXCEPTION 'research_claim must have RLS enabled before browser grants are tightened';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'research_claim'
      AND policyname = 'research_claim_member_select'
      AND cmd = 'SELECT'
  ) THEN
    RAISE EXCEPTION 'research_claim_member_select policy is required before granting member SELECT';
  END IF;
END;
$$;

REVOKE ALL ON TABLE public.research_claim FROM anon, authenticated;
GRANT SELECT ON TABLE public.research_claim TO authenticated;
GRANT ALL ON TABLE public.research_claim TO service_role;

DO $$
BEGIN
  IF has_table_privilege('anon', 'public.research_claim', 'SELECT')
     OR has_table_privilege('authenticated', 'public.research_claim', 'INSERT')
     OR has_table_privilege('authenticated', 'public.research_claim', 'UPDATE')
     OR has_table_privilege('authenticated', 'public.research_claim', 'DELETE') THEN
    RAISE EXCEPTION 'research_claim browser grants are broader than member SELECT';
  END IF;

  IF NOT has_table_privilege('authenticated', 'public.research_claim', 'SELECT')
     OR NOT has_table_privilege('service_role', 'public.research_claim', 'INSERT') THEN
    RAISE EXCEPTION 'research_claim required authenticated/service_role grants are missing';
  END IF;
END;
$$;