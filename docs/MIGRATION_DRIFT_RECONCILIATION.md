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

- Present: workspace retention columns/tables, tenant deletion tombstones, dataset-version feed, `enqueue_research_run(uuid,uuid,text)`, team entitlement constraint, private `qros-datasets` bucket, tenant select policy.
- Absent: `pgtap` extension; a policy named `research validation client deny` on `public.research_validation`.

The absence of a particular policy name is not proof that the table is unprotected. Inspect every applicable policy, grants, and RLS flags before deciding whether to add or replace policies. Do not enable RLS without the intended policies and tested service-role behavior.

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
