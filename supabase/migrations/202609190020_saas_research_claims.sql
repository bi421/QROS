-- Durable tenant-scoped Research Claim persistence.
-- Claim semantics remain immutable/versioned in the domain layer; this table is
-- the SaaS persistence boundary and never falls back to the legacy SQLite store.

create table if not exists public.research_claim (
    id text primary key,
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    statement text not null check (length(trim(statement)) > 0),
    claim_type text not null,
    evidence_state text not null,
    version integer not null check (version > 0),
    parent_claim_id text,
    research_id text,
    creator text not null,
    plan_hash text,
    plan_locked_at timestamptz,
    claim_hash text not null check (claim_hash ~ '^[0-9a-f]{64}$'),
    payload jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (workspace_id, id),
    unique (workspace_id, claim_hash)
);

create index if not exists idx_research_claim_workspace_created
    on public.research_claim(workspace_id, created_at desc);

create index if not exists idx_research_claim_workspace_parent
    on public.research_claim(workspace_id, parent_claim_id);

create index if not exists idx_research_claim_workspace_research
    on public.research_claim(workspace_id, research_id);

alter table public.research_claim enable row level security;

-- The customer API uses a trusted server-side Supabase client. Do not expose
-- this table directly to anon/authenticated clients; the API performs the
-- tenant authorization before reaching this persistence adapter.
grant select, insert, update, delete on public.research_claim to service_role;

drop policy if exists research_claim_member_select on public.research_claim;
create policy research_claim_member_select
on public.research_claim
for select to authenticated
using (public.is_workspace_member(workspace_id));

comment on table public.research_claim is
    'Tenant-scoped durable Research Claim. Scientific semantics and version lineage are defined by the ResearchClaim domain contract.';

comment on column public.research_claim.payload is
    'Canonical serialized ResearchClaim including locked plan, evidence references, and lineage metadata.';

comment on column public.research_claim.claim_hash is
    'Deterministic ResearchClaim content hash used for provenance and integrity checks.';
