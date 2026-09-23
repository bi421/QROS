-- Schedule the retention hard-purge database job when pg_cron is available.
create extension if not exists pg_cron;
select cron.schedule(
  'qros-hard-purge-expired-tenants',
  '15 * * * *',
  $$select public.hard_purge_expired_tenants(50);$$
)
where not exists (
  select 1 from cron.job where jobname = 'qros-hard-purge-expired-tenants'
);
