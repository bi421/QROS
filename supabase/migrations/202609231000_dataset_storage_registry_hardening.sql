-- Tenant-bound private Storage and immutable content-addressed dataset registry.
insert into storage.buckets (id, name, public)
values ('qros-datasets', 'qros-datasets', false)
on conflict (id) do update set public = false;

drop policy if exists qros_datasets_tenant_select on storage.objects;
drop policy if exists qros_datasets_tenant_insert on storage.objects;
drop policy if exists qros_datasets_tenant_update on storage.objects;
drop policy if exists qros_datasets_tenant_delete on storage.objects;

create policy qros_datasets_tenant_select
on storage.objects
for select to authenticated
using (
  bucket_id = 'qros-datasets'
  and (storage.foldername(name))[1] = 'tenant'
  and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

create policy qros_datasets_tenant_insert
on storage.objects
for insert to authenticated
with check (
  bucket_id = 'qros-datasets'
  and (storage.foldername(name))[1] = 'tenant'
  and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

create policy qros_datasets_tenant_update
on storage.objects
for update to authenticated
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

create policy qros_datasets_tenant_delete
on storage.objects
for delete to authenticated
using (
  bucket_id = 'qros-datasets'
  and (storage.foldername(name))[1] = 'tenant'
  and (storage.foldername(name))[2] = (select auth.jwt() ->> 'tenant_id')
);

alter table public.dataset_version
  drop constraint if exists dataset_version_storage_path_contract;

alter table public.dataset_version
  add constraint dataset_version_storage_path_contract
  check (
    storage_path ~ '^tenant/[0-9a-fA-F-]{36}/datasets/[0-9a-f]{64}/[1-9][0-9]*$'
  );

create or replace function public.prevent_dataset_version_mutation()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if old.dataset_id <> new.dataset_id
     or old.version_no <> new.version_no
     or old.content_sha256 <> new.content_sha256
     or old.storage_path <> new.storage_path
     or old.byte_size <> new.byte_size
     or old.created_by <> new.created_by then
    raise exception using
      errcode = 'P0001',
      message = 'DATASET_VERSION_IMMUTABLE';
  end if;
  return new;
end;
$$;

drop trigger if exists dataset_version_immutable on public.dataset_version;
create trigger dataset_version_immutable
before update on public.dataset_version
for each row execute function public.prevent_dataset_version_mutation();

comment on table public.dataset_version is 'Immutable content-addressed dataset versions; duplicate content is deduplicated by dataset_id + content_sha256.';
