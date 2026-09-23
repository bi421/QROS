-- Tenant-scoped Supabase Storage authorization for private dataset objects.
-- Folder prefix is the authoritative tenant boundary:
-- tenant/{tenant_id}/datasets/{sha256(content)}/{version}/

insert into storage.buckets (id, name, public)
values ('qros-datasets', 'qros-datasets', false)
on conflict (id) do update set public = false;

drop policy if exists qros_datasets_tenant_select on storage.objects;
create policy qros_datasets_tenant_select
on storage.objects
for select
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

drop policy if exists qros_datasets_tenant_insert on storage.objects;
create policy qros_datasets_tenant_insert
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

drop policy if exists qros_datasets_tenant_update on storage.objects;
create policy qros_datasets_tenant_update
on storage.objects
for update
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
)
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

drop policy if exists qros_datasets_tenant_delete on storage.objects;
create policy qros_datasets_tenant_delete
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);
