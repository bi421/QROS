-- Atomically claim and apply one billing event.
-- The whole operation runs in one PostgreSQL transaction so a failed side effect
-- rolls back the deduplication insert and the provider can safely retry.
create or replace function public.process_billing_event(
    p_event_id text,
    p_workspace_id uuid,
    p_provider text,
    p_payload_sha256 text,
    p_plan text,
    p_status text,
    p_current_period_end timestamptz default null,
    p_provider_customer_id text default null,
    p_provider_subscription_id text default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
    inserted_event_id text;
    existing_hash text;
    existing_processed_at timestamptz;
    effective_plan text;
    max_datasets bigint;
    max_jobs_per_month bigint;
    max_storage_mb bigint;
    normalized_status text;
begin
    if p_event_id is null or btrim(p_event_id) = '' then
        raise exception 'billing event id is required';
    end if;
    if p_workspace_id is null then
        raise exception 'billing workspace is required';
    end if;
    if p_provider is null or btrim(p_provider) = '' then
        raise exception 'billing provider is required';
    end if;
    if p_payload_sha256 !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid billing payload hash';
    end if;
    if p_plan not in ('free', 'pro', 'team', 'enterprise') then
        raise exception 'unsupported billing entitlement plan';
    end if;

    normalized_status := case when p_status = 'canceled' then 'cancelled' else p_status end;
    if normalized_status not in ('trialing', 'active', 'past_due', 'cancelled', 'incomplete') then
        raise exception 'unsupported billing subscription status';
    end if;

    insert into public.billing_event (
        event_id, workspace_id, provider, payload_sha256
    )
    values (
        p_event_id, p_workspace_id, p_provider, p_payload_sha256
    )
    on conflict (event_id) do nothing
    returning event_id into inserted_event_id;

    if inserted_event_id is null then
        select payload_sha256, processed_at
          into existing_hash, existing_processed_at
          from public.billing_event
         where event_id = p_event_id
         for update;

        if existing_hash <> p_payload_sha256 then
            raise exception 'billing event id reused with different payload';
        end if;

        -- Existing rows are never re-applied here. New processing is atomic below,
        -- so an interrupted new transaction cannot leave a permanently claimed row.
        return false;
    end if;

    effective_plan := case
        when normalized_status in ('active', 'trialing') then p_plan
        else 'free'
    end;

    case effective_plan
        when 'free' then
            max_datasets := 10;
            max_jobs_per_month := 100;
            max_storage_mb := 1024;
        when 'pro' then
            max_datasets := 1000;
            max_jobs_per_month := 1000;
            max_storage_mb := 10240;
        when 'team' then
            max_datasets := 1000;
            max_jobs_per_month := 1000;
            max_storage_mb := 10240;
        when 'enterprise' then
            max_datasets := 0;
            max_jobs_per_month := 0;
            max_storage_mb := 0;
    end case;

    insert into public.entitlement (
        tenant_id, plan, max_datasets, max_jobs_per_month, max_storage_mb, updated_at
    )
    values (
        p_workspace_id, effective_plan, max_datasets, max_jobs_per_month, max_storage_mb, pg_catalog.now()
    )
    on conflict (tenant_id) do update set
        plan = excluded.plan,
        max_datasets = excluded.max_datasets,
        max_jobs_per_month = excluded.max_jobs_per_month,
        max_storage_mb = excluded.max_storage_mb,
        updated_at = excluded.updated_at;

    insert into public.subscription (
        workspace_id, plan, status, provider,
        provider_customer_id, provider_subscription_id,
        current_period_end, updated_at
    )
    values (
        p_workspace_id, p_plan, normalized_status, p_provider,
        p_provider_customer_id, p_provider_subscription_id,
        p_current_period_end, pg_catalog.now()
    )
    on conflict (workspace_id) do update set
        plan = excluded.plan,
        status = excluded.status,
        provider = excluded.provider,
        provider_customer_id = coalesce(excluded.provider_customer_id, public.subscription.provider_customer_id),
        provider_subscription_id = coalesce(excluded.provider_subscription_id, public.subscription.provider_subscription_id),
        current_period_end = coalesce(excluded.current_period_end, public.subscription.current_period_end),
        updated_at = excluded.updated_at;

    update public.billing_event
       set processed_at = pg_catalog.now()
     where event_id = p_event_id;

    return true;
end;
$$;

revoke execute on function public.process_billing_event(
    text, uuid, text, text, text, text, timestamptz, text, text
) from public, anon, authenticated;
grant execute on function public.process_billing_event(
    text, uuid, text, text, text, text, timestamptz, text, text
) to service_role;

comment on function public.process_billing_event(
    text, uuid, text, text, text, text, timestamptz, text, text
) is 'Server-only atomic billing event deduplication, entitlement projection, and subscription lifecycle update.';
