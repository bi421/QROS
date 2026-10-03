-- Forward-only reconciliation of the workspace billing-admin role contract.
-- This preserves existing membership rows and does not alter historical migrations.

do $$
begin
    if exists (
        select 1
        from public.workspace_member
        where role not in ('owner','admin','researcher','viewer','billing_admin')
    ) then
        raise exception
            'workspace_member role reconciliation blocked: existing rows contain an unsupported role';
    end if;
end
$$;

alter table public.workspace_member
    drop constraint if exists workspace_member_role_check;

alter table public.workspace_member
    add constraint workspace_member_role_check
    check (role in ('owner','admin','researcher','viewer','billing_admin'));
