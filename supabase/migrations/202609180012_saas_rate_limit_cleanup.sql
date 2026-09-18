-- Retain bounded server-side rate-limit state and purge expired windows.
create extension if not exists pg_cron;

select cron.schedule(
    'qros-rate-limit-cleanup',
    '*/5 * * * *',
    $$delete from public.api_rate_limit where expires_at <= clock_timestamp()$$
);

comment on table public.api_rate_limit is
    'Server-only shared fixed-window API rate-limit state for multi-instance deployments; expired windows are purged every five minutes by pg_cron.';
