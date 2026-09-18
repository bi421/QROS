-- Shared server-side fixed-window rate limiting for multi-instance API deployments.
create table if not exists public.api_rate_limit (
    rate_key text primary key check (length(rate_key) between 1 and 128),
    window_started_at timestamptz not null,
    request_count integer not null check (request_count >= 0),
    expires_at timestamptz not null
);

alter table public.api_rate_limit enable row level security;
revoke all on table public.api_rate_limit from anon, authenticated;

create or replace function public.consume_api_rate_limit(
    p_rate_key text,
    p_limit integer,
    p_window_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_window_start timestamptz;
    v_count integer;
begin
    if p_rate_key is null or length(p_rate_key) < 1 or length(p_rate_key) > 128
       or p_limit < 1 or p_window_seconds < 1 then
        raise exception 'invalid rate limit arguments';
    end if;

    insert into public.api_rate_limit(rate_key, window_started_at, request_count, expires_at)
    values (
        p_rate_key,
        v_now,
        1,
        v_now + make_interval(secs => p_window_seconds)
    )
    on conflict (rate_key) do update
    set
        window_started_at = case
            when public.api_rate_limit.expires_at <= v_now then v_now
            else public.api_rate_limit.window_started_at
        end,
        request_count = case
            when public.api_rate_limit.expires_at <= v_now then 1
            when public.api_rate_limit.request_count < p_limit then public.api_rate_limit.request_count + 1
            else public.api_rate_limit.request_count
        end,
        expires_at = case
            when public.api_rate_limit.expires_at <= v_now
                then v_now + make_interval(secs => p_window_seconds)
            else public.api_rate_limit.expires_at
        end
    returning window_started_at, request_count into v_window_start, v_count;

    return v_count <= p_limit;
end;
$$;

revoke all on function public.consume_api_rate_limit(text, integer, integer) from public, anon, authenticated;
grant execute on function public.consume_api_rate_limit(text, integer, integer) to service_role;

create index if not exists idx_api_rate_limit_expires_at
    on public.api_rate_limit(expires_at);

comment on table public.api_rate_limit is
    'Server-only shared fixed-window API rate-limit state for multi-instance deployments.';
