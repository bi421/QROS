-- Align the durable entitlement schema with the application billing contract.
-- The subscription schema already permits the team plan, and billing.py
-- already maps team to the same limits as pro. Keep the database contract
-- consistent so team billing events cannot be rejected by the entitlement
-- check constraint.

alter table public.entitlement
    drop constraint if exists entitlement_plan_check;

alter table public.entitlement
    add constraint entitlement_plan_check
    check (plan in ('free', 'pro', 'team', 'enterprise'));

update public.entitlement e
set
    plan = 'team',
    max_datasets = 1000,
    max_jobs_per_month = 1000,
    max_storage_mb = 10240,
    updated_at = now()
from public.subscription s
where s.workspace_id = e.tenant_id
  and s.plan = 'team';
