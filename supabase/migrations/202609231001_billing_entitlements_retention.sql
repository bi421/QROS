create table if not exists public.entitlements (
  tenant_id uuid primary key,
  plan text not null check (plan in ('free','pro','enterprise')),
  max_datasets integer not null check (max_datasets >= 0),
  max_jobs_per_month integer not null check (max_jobs_per_month >= 0),
  max_storage_mb integer not null check (max_storage_mb >= 0),
  max_members integer not null check (max_members >= 0),
  deleted_at timestamptz,
  updated_at timestamptz not null default now()
);

insert into public.entitlements (tenant_id, plan, max_datasets, max_jobs_per_month, max_storage_mb, max_members)
select w.id,
       case when s.plan in ('pro','enterprise') then s.plan else 'free' end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 100 else 3 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 1000 else 100 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 102400 else 1024 end,
       case when s.plan = 'enterprise' then 0 when s.plan = 'pro' then 50 else 5 end
from public.workspace w
left join public.subscription s on s.workspace_id = w.id
on conflict (tenant_id) do nothing;

alter table public.entitlements enable row level security;
revoke all on table public.entitlements from anon, authenticated;
grant all on table public.entitlements to service_role;
drop policy if exists tenant_select on public.entitlements;
drop policy if exists tenant_insert on public.entitlements;
drop policy if exists tenant_update on public.entitlements;
drop policy if exists tenant_delete on public.entitlements;
create policy tenant_select on public.entitlements for select to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text);
create policy tenant_insert on public.entitlements for insert to authenticated with check (auth.jwt() ->> 'tenant_id' = tenant_id::text);
create policy tenant_update on public.entitlements for update to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text and deleted_at is null) with check (auth.jwt() ->> 'tenant_id' = tenant_id::text and deleted_at is null);
create policy tenant_delete on public.entitlements for delete to authenticated using (auth.jwt() ->> 'tenant_id' = tenant_id::text);

create or replace function public.mark_entitlement_deleted()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if new.deleted_at is not null and old.deleted_at is null then
    update public.entitlements set deleted_at = new.deleted_at, updated_at = timezone('utc', now())
    where tenant_id = new.id and deleted_at is null;
  end if;
  return new;
end;
$$;

drop trigger if exists mark_entitlement_deleted on public.workspace;
create trigger mark_entitlement_deleted
after update of deleted_at on public.workspace
for each row execute function public.mark_entitlement_deleted();
