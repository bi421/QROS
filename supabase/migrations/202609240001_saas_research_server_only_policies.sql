-- Server-only governed research projections remain inaccessible to client roles.
-- service_role bypasses RLS and is the only role granted RPC execution above.

create policy "research validation client deny"
    on public.research_validation
    for all
    to anon, authenticated
    using (false)
    with check (false);

create policy "research finding client deny"
    on public.research_finding
    for all
    to anon, authenticated
    using (false)
    with check (false);
