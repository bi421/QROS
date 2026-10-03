-- Make the server-only rate-limit boundary explicit to the PostgREST roles.
-- RLS remains enabled; this deny policy also satisfies the database linter
-- and documents that browser roles must never access rate-limit state.
create policy api_rate_limit_no_client_access
    on public.api_rate_limit
    for all
    to anon, authenticated
    using (false)
    with check (false);

comment on policy api_rate_limit_no_client_access on public.api_rate_limit is
    'Explicit deny boundary: API rate-limit state is server-only.';
