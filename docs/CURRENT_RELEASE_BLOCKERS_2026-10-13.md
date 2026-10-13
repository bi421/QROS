# Current release blockers — 2026-10-13

**Candidate main SHA audited:** `2c79418c5445e9b36004c53978993ae54d37a76f`  
**Status:** RELEASE BLOCKED. This document is a read-only evidence snapshot, not an approval to mutate either database.

## Exact-SHA CI

- GitHub check-runs for the candidate SHA: **13 success, 1 failure, 0 pending** at audit time.
- The failed check is **Supabase Preview**: `Remote migration versions not found in local migrations directory.`
- The configured test suite and coverage job passed on workflow run [38360231198](https://github.com/bi421/QROS/actions/runs/38360231198).
- The failed Supabase Preview check is not a GitHub Actions workflow in `.github/workflows`; repository-side changes alone cannot establish or change the integration's linked project/branch configuration.

## Current repository and remote ledgers

- Current repository contains **69** `supabase/migrations/*.sql` files.
- Read-only production ledger for `pvhdsngxyoiqhqwujfjt`: **57** rows at audit time.
- Read-only staging ledger for `yebwhcntiockckhdvawt`: **46** rows at audit time; latest row `20261005091724` / `20261005050000_dataset_version_feed_reconciliation`.
- Production ledger rows:
  - `20261008042804:20261008050100_saas_rls_restore_and_optimize`
  - `20261008042823:20261008050200_saas_qros_fk_indexes_v2`
  have no corresponding SQL files in the current 69-file repository migration directory. The only local migration beginning `2026100805` is `20261008050300_saas_rls_performance_hardening.sql`.
- GitHub commit-path queries for the missing source filenames returned no commits in this repository. Global code search found only references in the drift-reconciliation document, not the SQL source. This does not rule out an external backup or a separate private/local source.

## Important correction: do not infer a clean-replay failure from current staging columns alone

The current staging schema does not have `tenant_id` on most inspected workspace-scoped tables. However, migration `202609230004_tenant_rls_contract.sql` adds `tenant_id` to the relevant tenant-owned tables earlier in the repository migration order. Therefore, the current staging schema alone does **not** prove that a fresh replay fails at `20261008050300_saas_rls_performance_hardening.sql`. A clean replay remains unverified and must be tested in an isolated disposable database.

## Safe completion path

1. Identify the Supabase GitHub integration's linked project and branch; capture its configuration and exact failing check output.
2. Recover the exact SQL, checksum, and provenance for both orphaned production ledger entries from an authoritative backup or another verified source. Do not synthesize replacements based on migration names.
3. Export the full `version,name` ledgers from both projects and run `scripts/check_migration_drift.py` against each export. Record every repo-only, DB-only, and version/name mismatch with expected objects, observed objects, and evidence.
4. Create a disposable replay database from the approved migration source; run all migrations in order and capture the first failure, if any. Keep the test database isolated from staging and production.
5. Make a reviewed forward-only remediation only after the missing SQL provenance and clean-replay evidence are understood. Verify staging schema parity, two-identity tenant isolation, storage denial, billing/entitlement, worker queue, and full Golden Path on the exact candidate SHA.
6. Re-run exact-SHA CI and independent backup/restore verification. Only then consider a separately approved production migration.

## Explicitly not done

- No production or staging database writes, migration applications, resets, or history rewrites.
- No fabricated SQL files added for the two orphaned ledger entries.
- No claim that a paying customer, public HTTPS deployment, Stripe lifecycle, DR restore, or end-to-end staging Golden Path is proven.

**Release decision:** remain blocked until the above evidence gates pass.

## Post-merge re-audit — 2026-10-13 08:49 UTC

The documentation snapshot above was merged as commit `5ab7f9d5ff44d0ab699ecb3be2fbc66010711d2e`. A subsequent comparison of the exact remote migration `version` values against the filename prefixes on current `main` found a broader mismatch than the two rows whose SQL source names are absent:

- Repository: **69** migration files.
- Production project `pvhdsngxyoiqhqwujfjt`: **57** remote ledger rows; **19** remote version values do not exactly match any local migration filename prefix.
- Staging project `yebwhcntiockckhdvawt`: **46** remote ledger rows; **46** remote version values do not exactly match any local migration filename prefix.
- In staging, many ledger `name` values correspond to local migration filenames but the recorded remote `version` is a different timestamp. This is a version-ledger mismatch, not evidence that all 46 SQL sources are absent.
- Production also has the two previously identified entries whose `name` has no matching local SQL source: `20261008050100_saas_rls_restore_and_optimize` and `20261008050200_saas_qros_fk_indexes_v2`.
- This exact-prefix comparison is a diagnostic signal, not a complete semantic migration diff. A verified export plus name/version/object-level comparison is still required.

On merged `main` SHA `5ab7f9d5ff44d0ab699ecb3be2fbc66010711d2e`, GitHub check-runs were observed at **4 success, 1 failure, 8 in progress**. The failed check remains Supabase Preview with `Remote migration versions not found in local migrations directory.`; the other eight checks were still running at capture time. Do not report this SHA as fully green.

The GitHub API also reports `main` branch protection disabled (`protected=false`, `protection.enabled=false`). This is a separate release-governance gap; no branch protection settings were changed during this audit.

No staging or production database writes, migration applications, resets, history rewrites, or paid Supabase branch creation were performed.
