insert into storage.buckets (id, name, public)
values ('qros-datasets', 'qros-datasets', false)
on conflict (id) do update set public = false;

create table if not exists public.billing_event (
    event_id text primary key,
    workspace_id uuid not null references public.workspace(id) on delete cascade,
    provider text not null,
    payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz not null default now(),
    processed_at timestamptz
);

alter table public.billing_event enable row level security;
revoke all on table public.billing_event from anon, authenticated;
comment on table public.billing_event is 'Server-only billing webhook deduplication and audit boundary.';
