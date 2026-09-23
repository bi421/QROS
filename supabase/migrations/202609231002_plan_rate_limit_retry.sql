-- Return a retry window for workspace-scoped plan rate limiting.
create or replace function public.consume_api_rate_limit_with_retry(
    p_rate_key text,
    p_limit integer,
    p_window_seconds integer
)
returns table(allowed boolean, retry_after integer)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_window_start timestamptz;
    v_count integer;
    v_expires timestamptz;
begin
    if p_rate_key is null or length(p_rate_key) < 1 or length(p_rate_key) > 128
       or p_limit < 1 or p_window_seconds < 1 then
        raise exception 'invalid rate limit arguments';
    end if;

    insert into public.api_rate_limit(rate_key, window_started_at, request_count, expires_at)
    values (p_rate_key, v_now, 1, v_now + make_interval(secs => p_window_seconds))
    on conflict (rate_key) do update
    set
      window_started_at = case when public.api_rate_limit.expires_at <= v_now then v_now else public.api_rate_limit.window_started_at end,
      request_count = case when public.api_rate_limit.expires_at <= v_now then 1
                           when public.api_rate_limit.request_count < p_limit then public.api_rate_limit.request_count + 1
                           else public.api_rate_limit.request_count end,
      expires_at = case when public.api_rate_limit.expires_at <= v_now then v_now + make_interval(secs => p_window_seconds)
                        else public.api_rate_limit.expires_at end
    returning window_started_at, request_count, expires_at
    into v_window_start, v_count, v_expires;

    allowed := v_count <= p_limit;
    retry_after := case
      when allowed then 0
      else greatest(1, ceil(extract(epoch from (v_expires - v_now)))::integer)
    end;
    return next;
end;
$$;

revoke all on function public.consume_api_rate_limit_with_retry(text, integer, integer) from public, anon, authenticated;
grant execute on function public.consume_api_rate_limit_with_retry(text, integer, integer) to service_role;
