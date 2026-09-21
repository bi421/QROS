# QROS Disaster Recovery Runbook V1

## Scope

This runbook covers the repository-controlled nightly PostgreSQL logical backup and a controlled restore drill. It does not claim that production backups are active until the GitHub Actions workflow has completed successfully against the configured production secrets.

## Required secrets

- `PROD_DATABASE_URL`
- `BACKUP_AWS_ACCESS_KEY_ID`
- `BACKUP_AWS_SECRET_ACCESS_KEY`
- `BACKUP_AWS_REGION`
- `BACKUP_S3_BUCKET`

The S3 bucket must have restricted write/read access, encryption at rest, and a lifecycle/retention policy appropriate to the production data classification.

## Backup verification

A successful run must show:
1. `pg_dump` completed.
2. SHA-256 manifest was generated.
3. Both objects were uploaded.
4. S3 `head-object` succeeded.
5. The workflow run is retained as operational evidence.

## Restore drill

Never restore over production. Use an isolated staging database.

1. Select a dated S3 backup.
2. Download the dump and SHA-256 manifest.
3. Verify the digest before restore.
4. Provision a clean staging database.
5. Run `pg_restore --clean --if-exists --no-owner`.
6. Apply the repository migration set to the restored database if the restore target requires migration reconciliation.
7. Run the full database/security test suite.
8. Verify tenant isolation, session revocation, claim/evidence persistence, and artifact integrity.
9. Record restore duration and data-loss point.
10. Destroy the temporary restore environment after evidence is captured.

## Release gate

The DR gate remains **unverified** until a real restore drill succeeds. A scheduled backup workflow and this document alone are not a zero-data-loss guarantee.

## Recovery targets

Set and record explicit RPO/RTO values for the production environment. Do not substitute the backup schedule for an RPO commitment.
