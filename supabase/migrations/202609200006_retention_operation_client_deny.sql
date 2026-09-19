-- Explicit client deny policy for the server-only retention operation table.
-- RLS remains defense-in-depth even though direct table privileges are revoked.

create policy retention_deletion_operation_no_client_access
    on public.retention_deletion_operation
    for all
    to anon, authenticated
    using (false)
    with check (false);

comment on policy retention_deletion_operation_no_client_access
    on public.retention_deletion_operation is
    'Explicit deny boundary: retention deletion operation state is server-only.';
