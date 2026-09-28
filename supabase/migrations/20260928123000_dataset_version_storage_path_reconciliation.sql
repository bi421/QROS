-- Forward-only reconciliation of the canonical dataset-version storage path contract.
-- This does not recreate or modify historical dataset-registry migrations.

do $$
begin
    if exists (
        select 1
        from public.dataset_version
        where storage_path !~ '^tenant/[0-9a-f-]{36}/datasets/[0-9a-f]{64}/[1-9][0-9]*/$'
    ) then
        raise exception
            'dataset_version storage-path reconciliation blocked: existing rows violate canonical path syntax';
    end if;
end
$$;

alter table public.dataset_version
    drop constraint if exists dataset_version_storage_path_contract;

alter table public.dataset_version
    add constraint dataset_version_storage_path_contract
    check (
        storage_path ~ '^tenant/[0-9a-f-]{36}/datasets/[0-9a-f]{64}/[1-9][0-9]*/$'
    );

create or replace function public.validate_dataset_version_storage_path()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    dataset_workspace uuid;
begin
    select d.workspace_id
      into dataset_workspace
      from public.dataset d
     where d.id = new.dataset_id;

    if dataset_workspace is null then
        raise exception 'dataset not found for version';
    end if;

    if new.content_sha256 <> lower(new.content_sha256)
       or new.content_sha256 !~ '^[0-9a-f]{64}$' then
        raise exception 'content_sha256 must be lowercase SHA-256';
    end if;

    if new.storage_path <> format(
        'tenant/%s/datasets/%s/%s/',
        dataset_workspace,
        lower(new.content_sha256),
        new.version_no
    ) then
        raise exception 'dataset storage path does not match canonical content-addressed path';
    end if;

    return new;
end;
$$;

drop trigger if exists dataset_version_storage_path_contract on public.dataset_version;

create trigger dataset_version_storage_path_contract
before insert on public.dataset_version
for each row
execute function public.validate_dataset_version_storage_path();
