# Disaster Recovery

## Objectives

- **RPO:** less than 24 hours.
- **RTO:** less than 4 hours.
- Restore into a fresh, isolated database; never restore over production during a drill.
- A release is healthy only when its exact commit has matching health evidence.

## Database backup and restore

1. Capture the source PostgreSQL database with `pg_dump --format=custom`.
2. Create a fresh restore database with `createdb`.
3. Apply every repository migration with `supabase db push --db-url <target> --include-all`.
4. Run `scripts/verify_migrations.py` against the target.
5. Restore the public data dump with `pg_restore`.
6. Compare the SHA-256 digest of `public.dataset_version` before and after restore.
7. Run `supabase test db supabase/tests/tenant_isolation_test.sql --db-url <target>`.
8. Record the machine-readable report from `scripts/backup_verify.py`.
9. Destroy the temporary restore database unless explicitly retained.

Supabase documents `db push --db-url`/`--include-all` for applying local migrations and `test db --db-url` for pgTAP against a specified database. See the official CLI reference.

## Storage restore

Database backups do not contain the bytes of Storage objects. Storage recovery is a separate object-store backup/restore operation.

1. Export Storage objects from the production bucket to the approved backup destination.
2. Restore them into a fresh staging/restore bucket.
3. Compute a deterministic SHA-256 manifest of relative object paths and bytes before and after restore.
4. Require an exact manifest match before declaring storage restore successful.
5. Run tenant-scoped storage authorization tests against the restored environment.

## Release gate

A release tag must point at the same commit recorded in `health_evidence_<sha>.json`. Evidence must report:

- `tests_passed: true`
- `health_status: PASS`
- `rls_check: true`
- `authz_check: true`
- `tenant_isolation_check: true`

The release workflow uploads the evidence artifact and creates the release only after all checks pass.

## Incident procedure

- Declare the incident and record UTC start time.
- Freeze destructive maintenance.
- Select the newest verified backup satisfying the RPO.
- Restore to an isolated target.
- Apply migrations and verify migration parity.
- Verify dataset and storage hashes.
- Run tenant-isolation and authorization checks.
- Switch application configuration only after restore evidence is complete.
- Record actual RTO/RPO and attach the evidence report.
