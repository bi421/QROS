create extension if not exists pg_cron;
select cron.schedule('qros-hard-purge-expired-tenants','15 * * * *','select public.purge_deleted_workspaces();');
