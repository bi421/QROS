-- Align the persistent entitlement contract with the subscription/billing plan contract.
-- The billing state machine and runtime entitlement map already support TEAM.
-- The original entitlement table constraint accidentally omitted TEAM, which would
-- make a valid TEAM subscription webhook fail at the database boundary.

alter table public.entitlement
    drop constraint if exists entitlement_plan_check;

alter table public.entitlement
    add constraint entitlement_plan_check
    check (plan in ('free', 'pro', 'team', 'enterprise'));

comment on constraint entitlement_plan_check on public.entitlement
    is 'Commercial entitlement plan must match the canonical SaaS plan set.';
