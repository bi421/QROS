create extension if not exists pg_cron;
select cron.schedule('qros-hard-purge-expired-tenants','15 * * * *','select public.hard_purge_expired_tenants(50);');
