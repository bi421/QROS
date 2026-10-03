-- Immutable, content-addressed dataset hardening.
-- Adds canonical storage path, experiment lineage, and retention guard.

alter table public.dataset_version
    drop constraint if exists dataset_version_storage_path_contract;

alter table public.dataset_version
    add constraint dataset_version_storage_path_contract
    check (
        storage_path ~ '^tenant/[0-9a-fA-F-]{36}/datasets/[0-9a-f]{64}/[1-9][0-9]*/$'
        and content_sha256 ~ '^[0-9a-f]{64}$'
    );

alter table public.research_finding
    add column if not exists deleted_at timestamptz;

create table if not exists public.dataset_version_feed (
    dataset_version_id uuid not null references public.dataset_version(id) on delete restrict,
    experiment_id text not null,
    created_at timestamptz not null default now(),
    primary key (dataset_version_id, experiment_id)
);

alter table public.dataset_version_feed enable row level security;
alter table public.dataset_version_feed force row level security;

create index if not exists idx_dataset_version_feed_version
    on public.dataset_version_feed(dataset_version_id);

create or replace function public.prevent_referenced_dataset_delete()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if exists (
        select 1
        from public.research_run rr
        join public.dataset_version dv on dv.id = rr.dataset_version_id
        join public.research_finding rf on rf.research_run_id = rr.id
        where dv.dataset_id = old.id
          and rf.deleted_at is null
    ) then
        raise exception 'DATASET_REFERENCED'
            using errcode = '23514';
    end if;
    return old;
end;
$$;

drop trigger if exists dataset_retention_guard on public.dataset;
create trigger dataset_retention_guard
before delete on public.dataset
for each row execute function public.prevent_referenced_dataset_delete();

revoke all on table public.dataset_version_feed from anon, authenticated;
grant all on table public.dataset_version_feed to service_role;
drop policy if exists dataset_version_feed_service_role on public.dataset_version_feed;
create policy dataset_version_feed_service_role on public.dataset_version_feed
    for all to service_role using (true) with check (true);

create or replace function public.validate_dataset_version_storage_path()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
    dataset_workspace uuid;
begin
    select d.workspace_id into dataset_workspace
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
for each row execute function public.validate_dataset_version_storage_path();
