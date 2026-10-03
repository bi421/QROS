-- Atomically provision the first customer workspace from a verified server identity.
-- The application obtains p_user_id only from Supabase-verified authentication claims.
-- The RPC is callable only by the server-side service role.

create or replace function public.provision_workspace(
    p_user_id uuid,
    p_name text
)
returns table(workspace_id uuid, role text, plan text)
language plpgsql
security definer
set search_path = public
as $$
declare
    new_workspace_id uuid;
    normalized_name text := trim(p_name);
begin
    if p_user_id is null then
        raise exception 'workspace owner identity is required';
    end if;
    if not exists (select 1 from auth.users where id = p_user_id) then
        raise exception 'workspace owner identity does not exist';
    end if;
    if normalized_name = '' or length(normalized_name) > 256 then
        raise exception 'invalid workspace name';
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    if exists (select 1 from public.workspace_member where user_id = p_user_id) then
        raise exception 'workspace already provisioned';
    end if;

    insert into public.workspace (name)
    values (normalized_name)
    returning id into new_workspace_id;

    insert into public.workspace_member (workspace_id, user_id, role)
    values (new_workspace_id, p_user_id, 'owner');

    insert into public.subscription (workspace_id, plan, status)
    values (new_workspace_id, 'free', 'active');

    return query
    select new_workspace_id, 'owner'::text, 'free'::text;
end;
$$;

revoke all on function public.provision_workspace(uuid, text) from public, anon, authenticated;
grant execute on function public.provision_workspace(uuid, text) to service_role;
