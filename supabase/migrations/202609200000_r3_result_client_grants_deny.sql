-- R3 server-only boundary: result provenance is consumed through the
-- versioned application API, not directly through PostgREST/GraphQL.
-- Keep RLS enabled as defense-in-depth, but remove direct client table grants.

revoke all on table
    public.research_run_result,
    public.research_run_artifact
from anon, authenticated;
