-- Durable server-side idempotency records for tenant-scoped API mutations.
-- Browser roles receive no privileges; the trusted API/worker uses the service role.
create table if not exists public.api_idempotency (
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    key text not null check (length(key) between 1 and 128),
    request_fingerprint text not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
    status_code integer not null check (status_code between 100 and 599),
    response_body jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null default (now() + interval '24 hours'),
    primary key (workspace_id, key)
);

create index if not exists idx_api_idempotency_expires_at
    on public.api_idempotency(expires_at);

alter table public.api_idempotency enable row level security;

revoke all on table public.api_idempotency from anon, authenticated;

comment on table public.api_idempotency is
    'Server-only idempotency records. Key scope is workspace + key; records expire after 24 hours.';
