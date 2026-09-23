-- Explicit fail-closed browser boundary for every durable tenant-owned projection.
-- Browser roles never receive write access to these server-owned persistence tables.
-- Service-role/server execution remains available and is intentionally outside browser RLS.

alter table public.api_idempotency force row level security;
alter table public.research_run_result force row level security;
alter table public.research_run_artifact force row level security;
alter table public.research_validation force row level security;
alter table public.research_finding force row level security;

revoke all on table
    public.api_idempotency,
    public.research_run_result,
    public.research_run_artifact,
    public.research_validation,
    public.research_finding
from public, anon, authenticated;

drop policy if exists api_idempotency_no_client_access on public.api_idempotency;
create policy api_idempotency_no_client_access
on public.api_idempotency
for all to anon, authenticated
using (false)
with check (false);

drop policy if exists research_run_result_no_client_access on public.research_run_result;
create policy research_run_result_no_client_access
on public.research_run_result
for all to anon, authenticated
using (false)
with check (false);

drop policy if exists research_run_artifact_no_client_access on public.research_run_artifact;
create policy research_run_artifact_no_client_access
on public.research_run_artifact
for all to anon, authenticated
using (false)
with check (false);

drop policy if exists research_validation_no_client_access on public.research_validation;
create policy research_validation_no_client_access
on public.research_validation
for all to anon, authenticated
using (false)
with check (false);

drop policy if exists research_finding_no_client_access on public.research_finding;
create policy research_finding_no_client_access
on public.research_finding
for all to anon, authenticated
using (false)
with check (false);

comment on policy api_idempotency_no_client_access on public.api_idempotency
is 'Fail-closed browser boundary: idempotency state is server-owned and never exposed through PostgREST.';

comment on policy research_run_result_no_client_access on public.research_run_result
is 'Fail-closed browser boundary: canonical research results are server-owned.';

comment on policy research_run_artifact_no_client_access on public.research_run_artifact
is 'Fail-closed browser boundary: result artifact lineage is server-owned.';

comment on policy research_validation_no_client_access on public.research_validation
is 'Fail-closed browser boundary: validation projections are server-owned.';

comment on policy research_finding_no_client_access on public.research_finding
is 'Fail-closed browser boundary: governed findings are server-owned.';
