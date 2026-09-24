-- Helper function to check workspace membership for RLS policies
create or replace function public.is_workspace_member(target_workspace_id uuid)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1
    from public.workspace_members
    where workspace_id = target_workspace_id
      and user_id = auth.uid()
  );
$$;

-- Grant execute permission to authenticated users (and anon if needed)
grant execute on function public.is_workspace_member(uuid) to authenticated;
-- Tenant-scoped Supabase Storage authorization for private dataset objects.
-- Object namespace: tenant/{workspace_id}/datasets/{sha256(content)}/{version}/.
-- Authorization is derived from workspace membership, not editable JWT metadata.

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
    and public.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy if exists qros_datasets_tenant_insert on storage.objects;
create policy qros_datasets_tenant_insert
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and public.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy if exists qros_datasets_tenant_update on storage.objects;
create policy qros_datasets_tenant_update
on storage.objects
for update
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and public.is_workspace_member(((storage.foldername(name))[2])::uuid)
)
with check (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and public.is_workspace_member(((storage.foldername(name))[2])::uuid)
);

drop policy if exists qros_datasets_tenant_delete on storage.objects;
create policy qros_datasets_tenant_delete
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'qros-datasets'
    and (storage.foldername(name))[1] = 'tenant'
    and public.is_workspace_member(((storage.foldername(name))[2])::uuid)
);
