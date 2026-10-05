-- Billing provider identity invariant: one provider subscription cannot be rebound
-- across QROS workspaces.
create extension if not exists pgtap;
begin;

select plan(2);

insert into auth.users (id, email)
values
  ('11111111-1111-1111-1111-111111111111', 'billing-a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'billing-b@test.invalid');

insert into public.workspace (id, name)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Billing workspace A'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'Billing workspace B');

select ok(
  exists (
    select 1
      from pg_indexes
     where schemaname = 'public'
       and tablename = 'subscription'
       and indexname = 'subscription_provider_subscription_id_key'
  ),
  'provider subscription identity index exists'
);

insert into public.subscription (
  workspace_id, plan, status, provider, provider_subscription_id
)
values (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'pro', 'active', 'stripe', 'sub_identity_test'
);

select throws_ok(
  $$
    insert into public.subscription (
      workspace_id, plan, status, provider, provider_subscription_id
    )
    values (
      'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'pro', 'active', 'stripe', 'sub_identity_test'
    )
  $$,
  '23505',
  'duplicate provider subscription id is rejected across workspaces'
);

select * from finish();
rollback;
