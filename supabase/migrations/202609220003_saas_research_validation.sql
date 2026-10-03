-- Durable, tenant-scoped persistence for governed research validation records.
-- Validation is a projection over an already-persisted canonical research result.

create table if not exists public.research_validation (
    id uuid primary key,
    workspace_id uuid not null,
    research_run_id uuid not null,
    result_manifest_sha256 text not null,
    claim_id text,
    plan_hash text,
    validation_sha256 text not null,
    status text not null,
    metrics jsonb not null default '{}'::jsonb,
    contract_version text not null default '1.0.0',
    created_at timestamptz not null default timezone('utc', now()),
    constraint research_validation_result_manifest_sha256_format
        check (result_manifest_sha256 ~ '^[0-9a-f]{64}$'),
    constraint research_validation_sha256_format
        check (validation_sha256 ~ '^[0-9a-f]{64}$'),
    constraint research_validation_plan_hash_format
        check (plan_hash is null or plan_hash ~ '^[0-9a-f]{64}$'),
    constraint research_validation_claim_plan_pair
        check ((claim_id is null) = (plan_hash is null)),
    constraint research_validation_status_nonempty
        check (length(trim(status)) between 1 and 64),
    constraint research_validation_contract_version_nonempty
        check (length(trim(contract_version)) between 1 and 32),
    constraint research_validation_run_fk
        foreign key (research_run_id)
        references public.research_run(id)
        on delete restrict,
    constraint research_validation_workspace_unique
        unique (workspace_id, research_run_id)
);

create index if not exists idx_research_validation_claim
    on public.research_validation(workspace_id, claim_id)
    where claim_id is not null;

alter table public.research_validation enable row level security;
alter table public.research_validation force row level security;

revoke all on table public.research_validation from public, anon, authenticated;

create or replace function public.create_research_validation(
    p_id uuid,
    p_workspace_id uuid,
    p_research_run_id uuid,
    p_result_manifest_sha256 text,
    p_claim_id text,
    p_plan_hash text,
    p_validation_sha256 text,
    p_status text,
    p_metrics jsonb,
    p_contract_version text
)
returns table (record jsonb, replayed boolean)
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_run public.research_run%rowtype;
    v_result public.research_run_result%rowtype;
    v_existing public.research_validation%rowtype;
begin
    if p_id is null
       or p_workspace_id is null
       or p_research_run_id is null
       or p_result_manifest_sha256 !~ '^[0-9a-f]{64}$'
       or p_validation_sha256 !~ '^[0-9a-f]{64}$'
       or p_plan_hash is not null and p_plan_hash !~ '^[0-9a-f]{64}$'
       or (p_claim_id is null) <> (p_plan_hash is null)
       or p_status is null
       or length(trim(p_status)) < 1
       or length(p_status) > 64
       or p_metrics is null
       or jsonb_typeof(p_metrics) <> 'object'
       or p_contract_version is null
       or length(trim(p_contract_version)) < 1
       or length(p_contract_version) > 32 then
        raise exception 'invalid research validation arguments';
    end if;

    select *
      into v_run
      from public.research_run
     where workspace_id = p_workspace_id
       and id = p_research_run_id
     for share;

    if not found then
        raise exception 'research run not found for workspace';
    end if;

    select *
      into v_result
      from public.research_run_result
     where workspace_id = p_workspace_id
       and research_run_id = p_research_run_id
     for share;

    if not found then
        raise exception 'research result not found for workspace';
    end if;

    if v_result.manifest_sha256 <> p_result_manifest_sha256 then
        raise exception 'result manifest does not match canonical research result';
    end if;

    if v_run.claim_id is distinct from p_claim_id
       or v_run.plan_hash is distinct from p_plan_hash then
        raise exception 'validation claim lineage does not match research run';
    end if;

    select *
      into v_existing
      from public.research_validation
     where workspace_id = p_workspace_id
       and research_run_id = p_research_run_id
     for update;

    if found then
        if v_existing.validation_sha256 <> p_validation_sha256 then
            raise exception 'research validation already exists with a different digest'
                using errcode = '23505';
        end if;
        return query select to_jsonb(v_existing), true;
        return;
    end if;

    insert into public.research_validation(
        id, workspace_id, research_run_id, result_manifest_sha256,
        claim_id, plan_hash, validation_sha256, status, metrics, contract_version
    )
    values (
        p_id, p_workspace_id, p_research_run_id, p_result_manifest_sha256,
        p_claim_id, p_plan_hash, p_validation_sha256, trim(p_status),
        p_metrics, trim(p_contract_version)
    )
    returning * into v_existing;

    return query select to_jsonb(v_existing), false;
end;
$$;

revoke all on function public.create_research_validation(
    uuid, uuid, uuid, text, text, text, text, text, jsonb, text
) from public, anon, authenticated;

grant execute on function public.create_research_validation(
    uuid, uuid, uuid, text, text, text, text, text, jsonb, text
) to service_role;

comment on table public.research_validation is
    'Immutable tenant-scoped validation projection bound to a canonical research result.';
