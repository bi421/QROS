-- Explicitly deny browser roles on server-only operational tables.
-- Service-role/server access remains available because service_role bypasses RLS.
create policy api_idempotency_no_client_access
on public.api_idempotency
for all
to anon, authenticated
using (false)
with check (false);

create policy billing_event_no_client_access
on public.billing_event
for all
to anon, authenticated
using (false)
with check (false);
