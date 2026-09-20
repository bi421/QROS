-- Explicit client deny boundary for the server-only audit event table.
-- Direct Data API access remains forbidden even if future default privileges change.

drop policy if exists audit_event_client_deny on public.audit_event;
create policy audit_event_client_deny
on public.audit_event
for all
to anon, authenticated
using (false)
with check (false);

revoke all on table public.audit_event from anon, authenticated;
