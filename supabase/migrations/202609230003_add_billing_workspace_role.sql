-- Forward-only compatibility migration for the billing workspace role.
-- Existing owner/admin/researcher/viewer rows remain valid.

alter table public.workspace_member
    drop constraint if exists workspace_member_role_check;

alter table public.workspace_member
    add constraint workspace_member_role_check
    check (role in ('owner', 'admin', 'researcher', 'viewer', 'billing'));

comment on column public.workspace_member.role
is 'Server-authoritative workspace role: owner, admin, researcher, viewer, or billing.';
