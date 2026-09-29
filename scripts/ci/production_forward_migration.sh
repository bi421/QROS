#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_PROJECT_ID:?SUPABASE_PROJECT_ID is required}"
: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD is required}"
: "${MIGRATION_FILE:?MIGRATION_FILE is required}"

case "${MIGRATION_FILE}" in
  20260928123000_dataset_version_storage_path_reconciliation.sql|20260928124500_workspace_billing_admin_role_reconciliation.sql|20260928120000_storage_authorization_workspace_membership_reconciliation.sql)
    ;;
  *)
    echo "::error::migration is not in the governed M1 forward-migration allowlist: ${MIGRATION_FILE}"
    exit 1
    ;;
esac

migration_path="supabase/migrations/${MIGRATION_FILE}"
test -f "${migration_path}" || {
  echo "::error::migration file not found: ${migration_path}"
  exit 1
}

version="${MIGRATION_FILE:0:14}"
migration_sha="$(sha256sum "${migration_path}" | awk '{print $1}')"

echo "migration=${MIGRATION_FILE}"
echo "version=${version}"
echo "sha256=${migration_sha}"

bundle="$(mktemp -d)"
trap 'rm -rf "${bundle}"' EXIT

mkdir -p "${bundle}/supabase/migrations"
cp "${migration_path}" "${bundle}/supabase/migrations/${MIGRATION_FILE}"

echo "== isolated migration bundle =="
find "${bundle}/supabase/migrations" -maxdepth 1 -type f -printf '%f\n' | sort

echo "== link target =="
supabase --workdir "${bundle}" link \
  --project-ref "${SUPABASE_PROJECT_ID}"

echo "== preflight: remote history =="
supabase --workdir "${bundle}" migration list --linked

echo "== preflight: controlled dry-run =="
dry_run="$(
  supabase --workdir "${bundle}" db push \
    --linked \
    --include-all \
    --dry-run \
    2>&1
)"
printf '%s\n' "${dry_run}"

count="$(printf '%s\n' "${dry_run}" | grep -F -c "${MIGRATION_FILE}" || true)"
test "${count}" -eq 1 || {
  echo "::error::controlled dry-run did not identify exactly one approved migration; count=${count}"
  exit 1
}

unexpected="$(printf '%s\n' "${dry_run}" | grep -E 'Would push migration [0-9]{14}_[^ ]+\.sql' | grep -F -v "${MIGRATION_FILE}" || true)"
test -z "${unexpected}" || {
  echo "::error::controlled bundle would apply an unexpected migration:"
  printf '%s\n' "${unexpected}"
  exit 1
}

if [[ "${APPLY_MIGRATION:-false}" != "true" ]]; then
  echo "forward_migration_mode=DRY_RUN"
  echo "forward_migration_apply=NOT_EXECUTED"
  exit 0
fi

test "${CONFIRM_APPLY:-}" = "APPLY" || {
  echo "::error::production mutation requires CONFIRM_APPLY=APPLY"
  exit 1
}

echo "== apply exactly one allowlisted migration =="
supabase --workdir "${bundle}" db push \
  --linked \
  --include-all \
  --yes

echo "== postflight: exact migration version =="
history="$(
  supabase --workdir "${bundle}" migration list --linked 2>&1
)"
printf '%s\n' "${history}"

remote_count="$(printf '%s\n' "${history}" | awk -v v="${version}" '
  $0 ~ v { count++ }
  END { print count + 0 }
')"

test "${remote_count}" -eq 1 || {
  echo "::error::postflight could not verify exactly one remote history entry for version ${version}"
  exit 1
}

echo "forward_migration_mode=APPLY"
echo "forward_migration_apply=SUCCESS"
echo "migration_version_verified=${version}"
echo "migration_sha256=${migration_sha}"

echo "== postflight: schema contract =="
case "$MIGRATION_FILE" in
  20260928123000_dataset_version_storage_path_reconciliation.sql)
    supabase --workdir "$bundle" db query --linked "
select 1 / case when
  (select count(*) from public.dataset_version) = 0
  and exists (select 1 from pg_constraint where conrelid = 'public.dataset_version'::regclass and conname = 'dataset_version_storage_path_contract')
  and to_regprocedure('public.validate_dataset_version_storage_path()') is not null
  and exists (select 1 from pg_trigger where tgrelid = 'public.dataset_version'::regclass and tgname = 'dataset_version_storage_path_contract' and not tgisinternal)
then 1 else 0 end as postcondition_ok;
"
    ;;
  20260928124500_workspace_billing_admin_role_reconciliation.sql)
    supabase --workdir "$bundle" db query --linked "
select 1 / case when
  (select count(*) from public.workspace_member) = 0
  and exists (select 1 from pg_constraint where conrelid = 'public.workspace_member'::regclass and conname = 'workspace_member_role_check' and position('billing_admin' in pg_get_constraintdef(oid)) > 0)
then 1 else 0 end as postcondition_ok;
"
    ;;
  20260928120000_storage_authorization_workspace_membership_reconciliation.sql)
    supabase --workdir "$bundle" db query --linked "
select 1 / case when
  exists (select 1 from storage.buckets where id = 'qros-datasets' and public = false)
  and (select count(*) from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname in ('qros_datasets_tenant_select','qros_datasets_tenant_insert','qros_datasets_tenant_update','qros_datasets_tenant_delete')) = 4
  and (select count(*) from pg_policies where schemaname = 'storage' and tablename = 'objects' and policyname in ('qros_datasets_tenant_select','qros_datasets_tenant_insert','qros_datasets_tenant_update','qros_datasets_tenant_delete') and (roles::text <> '{authenticated}' or permissive <> 'PERMISSIVE' or coalesce(qual, '') like '%auth.jwt()%' or coalesce(with_check, '') like '%auth.jwt()%' or coalesce(qual, '') like '%tenant_id%' or coalesce(with_check, '') like '%tenant_id%' or (coalesce(qual, '') not like '%private.is_workspace_member%' and coalesce(with_check, '') not like '%private.is_workspace_member%'))) = 0
then 1 else 0 end as postcondition_ok;
"
    ;;
esac
