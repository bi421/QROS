# QROS Disaster Recovery Runbook

## Recovery objectives

| Objective | Target | Verification |
|---|---:|---|
| RPO | **< 24 hours** (operational target: 12 hours) | Backup cadence/PITR monitoring plus `scripts/backup_verify.py` |
| RTO | **< 4 hours** | Quarterly restore drill measured from incident declaration to service readiness |
| Backup integrity | 100% of scheduled verification runs | `backup_verify.py` must exit 0 |
| Tenant isolation | Required before recovery is accepted | Restored database must pass `supabase/tests/tenant_isolation_test.sql` |
| Dataset object integrity | 100% hash match for restored objects | SHA-256 comparison in `backup_verify.py` |

The RPO/RTO values are QROS operational targets, not a guarantee of the underlying managed platform. Supabase daily backups can leave up to a day's worth of changes at risk; PITR provides finer-grained recovery points and should be enabled when the 12-hour target cannot be met by the selected backup schedule.

## What is backed up

QROS has two independent recovery domains:

1. **PostgreSQL** — tenant/workspace metadata, datasets, dataset versions, research jobs/runs, evidence and lineage metadata, claims/findings/validation records, retention/deletion audit state, and supported Supabase metadata.
2. **Object storage** — dataset files and other content addressed by `storage_path`.

The database backup does not contain Supabase Storage object bytes; object storage must therefore be replicated/backed up independently.

## Backup verification procedure

Run:

    python scripts/backup_verify.py \
      --source-url "$SOURCE_DATABASE_URL" \
      --target-admin-url "$TARGET_ADMIN_DATABASE_URL" \
      --object-root-before /path/to/source-object-mirror \
      --object-root-after /path/to/restored-object-mirror

The verifier:

1. creates a custom-format `pg_dump`;
2. creates a fresh PostgreSQL database;
3. applies every repository migration with `supabase migration up --include-all`;
4. runs `scripts/verify_migrations.py` against the restored target schema;
5. restores source public data with `pg_restore --data-only`;
6. compares every `dataset_version.content_sha256` before/after restore;
7. executes the tenant-isolation pgTAP suite against the restored database;
8. computes SHA-256 for every supplied object-storage file and requires exact before/after equality;
9. removes the temporary restore database unless `--keep-target` is supplied.

`pg_restore` is designed to restore PostgreSQL archives created by `pg_dump`, including custom-format archives.

## Required pass conditions

- `pg_dump` succeeds.
- A new database can be created.
- `pg_restore` completes without error.
- migration integrity verification passes.
- all tenant-isolation tests pass on the restored database.
- every replicated dataset object has the same SHA-256 hash before and after restore.
- no expected object is missing and no unexpected object appears in the verified object set.

## Restore procedure

### 1. Declare incident

Record incident start time, desired recovery point, last known good backup/PITR point, affected services, and database/object-storage replication status.

### 2. Recover PostgreSQL

Restore the selected backup/PITR point into a new database/project where practical. Do not overwrite production until verification succeeds.

Supabase supports restoring backups and PITR recovery points; actual restoration duration depends on database size and WAL activity, so the <4h RTO must be measured in QROS restore drills rather than assumed.

### 3. Recover object storage

Restore the independently replicated object set. For every dataset version/object, locate `storage_path`, calculate SHA-256 over the restored bytes, compare with the source/recorded `content_sha256`, and reject recovery if any hash differs.

Supabase documents that restoring a database backup does not restore Storage object bytes; those files must be restored separately.

### 4. Verify security and lineage

Run `python scripts/check_migrations.py` and `python scripts/backup_verify.py ...`.

Then verify tenant isolation, deleted/tombstoned evidence non-resurrection, historical evidence hashes, and application health/readiness.

### 5. Cut over

Only after all verification gates pass: switch application/database configuration, verify health/readiness, run a read-only tenant smoke test, monitor errors/database activity, and record recovery completion time.

## Backup schedule and monitoring

To maintain RPO <24h, production must have a successful backup point at least once per 24-hour interval, with operational margin. The recommended target is 12 hours or better.

If the required recovery point cannot be guaranteed by scheduled backups, enable PITR. Supabase documents PITR as providing much finer recovery granularity than daily backups.

A failed backup verification is a production reliability incident. The next scheduled run is not considered sufficient until the failed path is diagnosed and a successful restore verification completes.

## Restore-drill cadence

Run a full restore drill before production launch, after major schema/retention changes, at least quarterly thereafter, and after any backup-platform or object-storage migration.

Record backup identifier, database size, dump/restore durations, migration and tenant-test durations, object count, hash mismatches, total RTO, achieved RPO, and final PASS/FAIL.

The measured drill result is the authoritative evidence for whether QROS currently meets the stated RPO/RTO targets.