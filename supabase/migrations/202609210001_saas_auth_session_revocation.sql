-- Enforce revocation-aware authentication for the production API.
-- The Auth schema is intentionally not exposed through the Data API, so the
-- production service uses this narrowly-scoped RPC with its server-only key.
create or replace function public.qros_session_is_active(
    p_user_id uuid,
    p_session_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1
        from auth.sessions as s
        where s.id = p_session_id
          and s.user_id = p_user_id
    );
$$;

revoke all on function public.qros_session_is_active(uuid, uuid) from public;
revoke all on function public.qros_session_is_active(uuid, uuid) from anon;
revoke all on function public.qros_session_is_active(uuid, uuid) from authenticated;
grant execute on function public.qros_session_is_active(uuid, uuid) to service_role;
