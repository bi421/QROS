-- Forward-only reconciliation of the dataset-version feed and retention guard contract.
-- Historical dataset-registry migration names are not rewritten.

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