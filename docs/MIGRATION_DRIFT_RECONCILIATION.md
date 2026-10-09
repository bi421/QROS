# Production migration drift reconciliation

**Audit baseline:** repository commit `d213c37231e2a7ecad751cc6ffaff369a9f31673`  
**Environment:** production project `pvhdsngxyoiqhqwujfjt` (read-only audit)  
**Repository files:** 66 SQL migrations  
**Database ledger:** 57 rows  
**Write actions performed:** none

## Why this is not a blind “20 migrations” repair

A filename/version comparison identifies drift, not whether the SQL effects exist. Historical migration rows in this project have been registered under execution timestamps different from the filename timestamp; some rows also use a shortened name. Conversely, some SQL files may have had their effects applied by a later reconciliation migration. Therefore, do not run every apparently missing migration, rename historical files, or rewrite `supabase_migrations.schema_migrations` based on names alone.

## Inventory findings from the read-only comparison

### Repository files whose logical names were absent from the DB ledger (12)

These require a schema/effect check before classifying as unapplied:

- `202609230000_saas_tenant_retention_controls.sql`
- `202609230003_add_billing_workspace_role.sql`
- `202609230005_tenant_scoped_storage_authorization.sql`
- `202609230006_observability_queue_correlation.sql`
- `202609230009_dataset_registry_hardening.sql`
- `202609230010_workspace_billing_admin_role.sql`
- `202609240001_saas_research_server_only_policies.sql`
- `202609240002_enable_pgtap.sql`
- `20260928120000_storage_authorization_workspace_membership_reconciliation.sql`
- `20260928123000_dataset_version_storage_path_reconciliation.sql`
- `202610050001_align_team_entitlements.sql`
- `20261005050000_dataset_version_feed_reconciliation.sql`

### DB history rows without a matching repository logical name (2)

- `20261008042804:20261008050100_saas_rls_restore_and_optimize`
- `20261008042823:20261008050200_saas_qros_fk_indexes_v2`

Preserve these as historical evidence until the SQL source and resulting schema effects are recovered. Do not delete the rows.

### Version/name mismatches

Multiple ledger versions differ from the leading timestamp in the corresponding repository filename. Examples include research claim/validation/finding migrations, workspace provisioning, billing migrations, worker queue consumer, and RLS hardening. Use the complete CSV export with `scripts/check_migration_drift.py` to enumerate all cases. Do not normalize these by editing DB history.

## Additional read-only schema probes

At the audit time, these were observed:

- Present: workspace retention columns/tables, tenant deletion tombstones, dataset-version feed, `enqueue_research_run(uuid,uuid,text)`, team entitlement constraint, private `qros-datasets` bucket.
- Absent: `pgtap` extension; a policy named `research validation client deny` on `public.research_validation`; `public.validate_dataset_version_storage_path()`.
- The live `qros-datasets` select/insert/update/delete policies authorize via `auth.jwt() ->> 'tenant_id'`, not `private.is_workspace_member(uuid)`. The earlier membership reconciliation file is absent from the DB migration ledger.
- The live `dataset_version_storage_path_contract` constraint does not require the canonical trailing slash. The table had 0 rows at audit time, so the proposed path reconciliation has no existing rows to normalize; its precondition still must be tested in staging.
- Both `research_validation` and `research_finding` have RLS enabled and forced, but their live policies are `tenant_select/insert/update/delete`; the named client-deny policies are absent. The current repository migration `20261008050300_saas_rls_performance_hardening.sql` recreates those tenant policies on these server-only projections, conflicting with the earlier server-only contract. Direct table SELECT grants for `anon`, `authenticated`, and `service_role` were not present in the read-only privilege probe; governed server-side RPC behavior must be regression-tested before changing policies.

Three forward-only candidate migrations have been added to the PR for review:
- `202610100001_storage_authorization_workspace_membership_reconciliation.sql`
- `202610100002_dataset_version_storage_path_reconciliation.sql`
- `202610100003_restore_server_only_research_projections.sql`

These files are proposed changes only; they have **not** been applied to staging or production. The production workflow allowlist has intentionally not been expanded pending staging validation. Do not run them against production until exact-SHA staging tests and independent recovery evidence pass.

The absence of a particular policy name is not proof by itself that a table is unprotected. Inspect all policies, grants, RLS flags, and server-side RPC behavior. Do not enable RLS without the intended policies and tested service-role/RPC behavior.

## Required reconciliation protocol

1. Export the full ledger as UTF-8 CSV with columns `version,name`. Preserve the original values exactly.
2. Run:
   ```powershell
   python scripts/check_migration_drift.py --ledger .\artifacts\production-migration-ledger.csv
   ```
3. For each finding, record: file hash, DB version/name, expected objects, observed objects, equivalent later migration if any, test evidence, disposition, reviewer, and timestamp.
4. Apply SQL migrations to a disposable local database first. Then run tenant RLS, storage authorization, billing/entitlement, queue, retention, and rollback/recovery tests.
5. Reconcile missing effects using a new forward-only migration. If effects already exist, document the provenance and avoid reapplying destructive SQL.
6. Run the staging schema parity and Golden Path gates against the exact candidate SHA. Capture job URLs and artifacts.
7. Only after staging recovery is proven, prepare a separately approved production migration. Do not edit production migration history to make the count look clean.

## Release gate

**BLOCKED** until each finding has a reviewed disposition and staging schema parity, cross-tenant denial, Golden Path, and independent restore evidence pass on the same candidate SHA.
