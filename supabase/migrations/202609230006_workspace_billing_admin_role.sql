-- Extend workspace roles for the SaaS authorization matrix.
-- Existing installations are upgraded without changing membership rows.

alter table public.workspace_member
    drop constraint if exists workspace_member_role_check;

alter table public.workspace_member
    add constraint workspace_member_role_check
    check (role in ('owner','admin','researcher','viewer','billing_admin'));
