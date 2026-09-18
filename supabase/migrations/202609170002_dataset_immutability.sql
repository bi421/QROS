-- Dataset versions are append-only. Version numbers are allocated under a
-- per-dataset transaction lock so concurrent uploads cannot reuse a number.

create or replace function public.allocate_dataset_version_no()
returns trigger
language plpgsql
set search_path = public
as $$
declare
    next_no integer;
begin
    perform pg_advisory_xact_lock(hashtextextended(new.dataset_id::text, 0));
    select coalesce(max(version_no), 0) + 1
      into next_no
      from public.dataset_version
     where dataset_id = new.dataset_id;
    new.version_no := next_no;
    return new;
end;
$$;

drop trigger if exists dataset_version_allocate_no on public.dataset_version;
create trigger dataset_version_allocate_no
before insert on public.dataset_version
for each row
execute function public.allocate_dataset_version_no();

create or replace function public.prevent_dataset_version_mutation()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if tg_op = 'DELETE' then
        raise exception 'dataset versions are immutable and cannot be deleted';
    end if;

    if new.dataset_id <> old.dataset_id
       or new.version_no <> old.version_no
       or new.content_sha256 <> old.content_sha256
       or new.storage_path <> old.storage_path
       or new.byte_size <> old.byte_size
       or new.created_by <> old.created_by
       or new.created_at <> old.created_at then
        raise exception 'dataset versions are immutable';
    end if;

    return new;
end;
$$;

drop trigger if exists dataset_version_immutable on public.dataset_version;
create trigger dataset_version_immutable
before update or delete on public.dataset_version
for each row
execute function public.prevent_dataset_version_mutation();

insert into storage.buckets (id, name, public)
values ('qros-datasets', 'qros-datasets', false)
on conflict (id) do update set public = false;
