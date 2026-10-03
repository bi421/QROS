-- Enforce tenant-scoped content-addressed research artifacts.
-- Canonical object path: <workspace_uuid>/artifacts/<sha256>.
-- The digest is immutable content identity; the tenant prefix preserves isolation.

do $$
begin
    if exists (
        select 1
          from public.artifact a
         where a.storage_path <> a.workspace_id::text || '/artifacts/' || a.content_sha256
    ) then
        raise exception 'cannot enforce artifact content-addressed path: existing artifact has non-canonical storage_path';
    end if;

    if exists (
        select 1
          from public.artifact
         group by workspace_id, content_sha256
        having count(*) > 1
    ) then
        raise exception 'cannot enforce artifact content-addressed identity: duplicate workspace/content_sha256 artifacts exist';
    end if;
end;
$$;

alter table public.artifact
    add constraint artifact_content_addressed_path
    check (storage_path = workspace_id::text || '/artifacts/' || content_sha256);

create unique index if not exists idx_artifact_workspace_content_sha256
    on public.artifact(workspace_id, content_sha256);

comment on column public.artifact.content_sha256 is
    'Immutable SHA-256 content identity; storage_path is canonically derived from workspace_id and this digest.';

comment on column public.artifact.storage_path is
    'Canonical tenant-scoped content-addressed path: <workspace_uuid>/artifacts/<sha256>.';
