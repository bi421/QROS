-- QROS dataset version integrity and concurrency contract.
-- Version numbers are allocated atomically inside Postgres; content/storage identity is immutable.

create or replace function public.create_dataset_version(
    p_dataset_id uuid,
    p_content_sha256 text,
    p_storage_path text,
    p_byte_size bigint,
    p_created_by uuid
)
returns public.dataset_version
language plpgsql
security invoker
set search_path = public
as $$
declare
    next_version integer;
    created public.dataset_version;
begin
    if p_content_sha256 !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid content_sha256';
    end if;
    if p_byte_size < 0 then
        raise exception 'invalid byte_size';
    end if;

    -- Serialize version allocation per dataset without blocking unrelated datasets.
    perform pg_advisory_xact_lock(hashtextextended(p_dataset_id::text, 0));

    select coalesce(max(dv.version_no), 0) + 1
      into next_version
      from public.dataset_version dv
     where dv.dataset_id = p_dataset_id;

    insert into public.dataset_version (
        dataset_id,
        version_no,
        content_sha256,
        storage_path,
        byte_size,
        created_by
    )
    values (
        p_dataset_id,
        next_version,
        p_content_sha256,
        p_storage_path,
        p_byte_size,
        p_created_by
    )
    returning * into created;

    return created;
end;
$$;

-- This function is a server-side persistence primitive. Do not expose it to
-- authenticated browser clients, because p_created_by is intentionally supplied
-- by the trusted API service rather than derived from an end-user RPC payload.
revoke all on function public.create_dataset_version(uuid, text, text, bigint, uuid) from public;
grant execute on function public.create_dataset_version(uuid, text, text, bigint, uuid) to service_role;

create or replace function public.prevent_dataset_version_mutation()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
    raise exception 'dataset versions are immutable';
end;
$$;

revoke all on function public.prevent_dataset_version_mutation() from public;

create trigger dataset_version_immutable
before update or delete on public.dataset_version
for each row execute function public.prevent_dataset_version_mutation();

comment on function public.create_dataset_version(uuid, text, text, bigint, uuid)
is 'Server-side atomic allocator for immutable dataset versions.';
comment on function public.prevent_dataset_version_mutation()
is 'Prevents UPDATE and DELETE of dataset_version rows.';
