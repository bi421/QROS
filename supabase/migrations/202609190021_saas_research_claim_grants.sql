-- Explicit Data API privilege boundary for the server-side claim adapter.
-- Customer clients must not access this table directly; the API authorizes
-- workspace ownership before using the trusted service-role client.

grant select, insert, update, delete on public.research_claim to service_role;
