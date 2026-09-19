-- Durable, tenant-scoped audit events for security-sensitive SaaS actions.
-- This table is server-only: service-role persistence is intentional and the
-- absence of client policies prevents direct Data API access.

create table if not exists public.audit_event (
    id uuid primary key,
    workspace_id uuid not null references public.workspace(id) on delete restrict,
    action text not null check (char_length(action) between 1 and 128),
    resource_type text not null check (char_length(resource_type) between 1 and 128),
    resource_id text,
    actor_user_id uuid,
    request_id text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

alter table public.audit_event enable row level security;

create index if not exists idx_audit_event_workspace_created_at
    on public.audit_event(workspace_id, created_at desc, id desc);

create index if not exists idx_audit_event_resource
    on public.audit_event(workspace_id, resource_type, resource_id, created_at desc);

revoke all on table public.audit_event from anon, authenticated;

comment on table public.audit_event is
    'Immutable server-side audit trail for security-sensitive tenant actions; metadata must never contain secrets or raw authentication tokens.';

comment on column public.audit_event.metadata is
    'Structured non-secret context only. Never store passwords, API keys, access tokens, refresh tokens, or raw authentication credentials.';
