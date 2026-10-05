-- A provider subscription must identify exactly one QROS workspace.
-- This prevents a signed webhook for an already-bound Stripe subscription
-- from being rebound to a second workspace through provider metadata.
create unique index if not exists subscription_provider_subscription_id_key
    on public.subscription (provider_subscription_id)
    where provider_subscription_id is not null;

comment on index public.subscription_provider_subscription_id_key is
    'Each non-null provider subscription id may belong to only one workspace.';
