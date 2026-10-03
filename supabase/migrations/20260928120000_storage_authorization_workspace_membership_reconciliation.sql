-- Forward-only reconciliation of qros-datasets authorization.
-- This does not recreate or supersede the historical 202609230005 migration.
-- It reconciles the currently live JWT-tenant policies to workspace membership.

do $$
declare
    p record;
    canonical_count integer;
begin
    if not exists (
        select 1
        from storage.buckets
        where id = 'qros-datasets'
          and public = false
    ) then
        raise exception 'Storage reconciliation precondition failed: qros-datasets bucket is missing or public';
    end if;

    select count(*)
      into canonical_count
      from pg_policies
     where schemaname = 'storage'
       and tablename = 'objects'
       and policyname in (
           'qros_datasets_tenant_select',
           'qros_datasets_tenant_insert',
           'qros_datasets_tenant_update',
           'qros_datasets_tenant_delete'
       )
       and roles::text = '{authenticated}'
       and permissive = 'PERMISSIVE'
       and (
           coalesce(qual, '') like '%private.is_workspace_member%'
           or coalesce(with_check, '') like '%private.is_workspace_member%'
       )
       and coalesce(qual, '') not like '%auth.jwt()%'
       and coalesce(with_check, '') not like '%auth.jwt()%'
       and coalesce(qual, '') not like '%tenant_id%'
       and coalesce(with_check, '') not like '%tenant_id%';

    if canonical_count = 4 then
        return;
    end if;

    if (select count(*)
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname in (
              'qros_datasets_tenant_select',
              'qros_datasets_tenant_insert',
              'qros_datasets_tenant_update',
              'qros_datasets_tenant_delete'
          )) <> 4 then
        raise exception 'Storage reconciliation precondition failed: expected exactly four target policies';
    end if;

    for p in
        select policyname, cmd, roles::text as roles, permissive, qual, with_check
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname in (
              'qros_datasets_tenant_select',
              'qros_datasets_tenant_insert',
              'qros_datasets_tenant_update',
              'qros_datasets_tenant_delete'
          )
    loop
        if p.permissive <> 'PERMISSIVE'
           or p.roles <> '{authenticated}' then
            raise exception 'Storage reconciliation precondition failed: policy % has unexpected mode or roles', p.policyname;
        end if;

        if p.policyname = 'qros_datasets_tenant_select'
           and (p.cmd <> 'SELECT'
                or p.qual is null
                or p.with_check is not null
                or position('auth.jwt()' in p.qual) = 0
                or position('tenant_id' in p.qual) = 0) then
            raise exception 'Storage reconciliation precondition failed: unexpected SELECT policy contract';
        end if;

        if p.policyname = 'qros_datasets_tenant_insert'
           and (p.cmd <> 'INSERT'
                or p.qual is not null
                or p.with_check is null
                or position('auth.jwt()' in p.with_check) = 0
                or position('tenant_id' in p.with_check) = 0) then
            raise exception 'Storage reconciliation precondition failed: unexpected INSERT policy contract';
        end if;

        if p.policyname = 'qros_datasets_tenant_update'
           and (p.cmd <> 'UPDATE'
                or p.qual is null
                or p.with_check is null
                or position('auth.jwt()' in p.qual) = 0
                or position('tenant_id' in p.qual) = 0
                or position('auth.jwt()' in p.with_check) = 0
                or position('tenant_id' in p.with_check) = 0) then
            raise exception 'Storage reconciliation precondition failed: unexpected UPDATE policy contract';
        end if;

        if p.policyname = 'qros_datasets_tenant_delete'
           and (p.cmd <> 'DELETE'
                or p.qual is null
                or p.with_check is not null
                or position('auth.jwt()' in p.qual) = 0
                or position('tenant_id' in p.qual) = 0) then
            raise exception 'Storage reconciliation precondition failed: unexpected DELETE policy contract';
        end if;
    end loop;
end
$$;

drop policy qros_datasets_tenant_select on storage.objects;
create policy qros_datasets_tenant_select
on storage.objects
for select
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and private.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy qros_datasets_tenant_insert on storage.objects;
create policy qros_datasets_tenant_insert
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and private.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy qros_datasets_tenant_update on storage.objects;
create policy qros_datasets_tenant_update
on storage.objects
for update
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and private.is_workspace_member(((storage.foldername(name))[2])::uuid)
)
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and private.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy qros_datasets_tenant_delete on storage.objects;
create policy qros_datasets_tenant_delete
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and private.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

do $$
declare
    bad_count integer;
begin
    select count(*) into bad_count
    from pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname in (
          'qros_datasets_tenant_select',
          'qros_datasets_tenant_insert',
          'qros_datasets_tenant_update',
          'qros_datasets_tenant_delete'
      )
      and (
          roles::text <> '{authenticated}'
          or permissive <> 'PERMISSIVE'
          or coalesce(qual, '') like '%auth.jwt()%'
          or coalesce(with_check, '') like '%auth.jwt()%'
          or coalesce(qual, '') like '%tenant_id%'
          or coalesce(with_check, '') like '%tenant_id%'
      );

    if bad_count <> 0 then
        raise exception 'Storage reconciliation postcondition failed: JWT tenant authorization remains';
    end if;

    if (select count(*)
        from pg_policies
        where schemaname = 'storage'
          and tablename = 'objects'
          and policyname in (
              'qros_datasets_tenant_select',
              'qros_datasets_tenant_insert',
              'qros_datasets_tenant_update',
              'qros_datasets_tenant_delete'
          )) <> 4 then
        raise exception 'Storage reconciliation postcondition failed: target policy count is not four';
    end if;
end
$$;
