# QROS Production Recovery Controls V1

Status: **IMPLEMENTED — EXECUTION REQUIRED**

## Recovery boundary

QROS treats PostgreSQL, Supabase Storage, durable jobs/idempotency, and application release/configuration as independent recovery surfaces.

## Object-storage recovery

The manual staging drill creates a deterministic artifact, stores it in the private `qros-datasets` bucket, exports an independent S3 recovery copy, verifies SHA-256, restores from that copy, re-uploads it, downloads it, and performs byte-for-byte verification.

Required staging environment secrets:
- `QROS_STAGING_SUPABASE_URL`
- `QROS_STAGING_SUPABASE_SERVICE_ROLE_KEY`
- `QROS_RECOVERY_S3_BUCKET`
- `QROS_RECOVERY_AWS_REGION`
- `QROS_RECOVERY_AWS_ACCESS_KEY_ID`
- `QROS_RECOVERY_AWS_SECRET_ACCESS_KEY`

The workflow maps the two AWS credential secrets explicitly to the AWS SDK/CLI environment variables `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. The region is mapped to `AWS_DEFAULT_REGION`.

This proves a controlled recovery path only; it does not prove that every production object is independently backed up.

## Migration rollback strategy

QROS migrations remain forward-only and are the canonical schema history. We do not invent destructive reverse migrations.

For a failed release:
1. stop promotion;
2. preserve migration history;
3. redeploy the previous release when schema compatibility permits;
4. otherwise apply a pre-reviewed forward repair migration;
5. use an isolated database restore only for actual corruption/loss;
6. re-run schema parity, RLS, security, and exact-release smoke gates.

Each production migration must document backward compatibility, reconciliation requirements, forward repair path, recovery point, and operator approval.

## RPO/RTO

RPO/RTO remain **unverified until an actual drill records them**. Documentation alone cannot close the gate.

## Release blockers

Before production launch, the exact target environment must demonstrate schema parity, authenticated Golden Path, storage upload/download, job execution/recovery, database restore, independent storage restore, exact-release smoke, and measured RPO/RTO.

## Production database backup prerequisites

The scheduled production backup fails closed unless the GitHub Actions `production` environment and repository configuration are provisioned. Configure and verify these values through the repository/environment settings; do not commit credentials or print secret values in workflow logs.

Required GitHub Actions values:

- Repository variable `BACKUP_AWS_ROLE_ARN`: IAM role trusted for this repository's GitHub Actions OIDC identity.
- Repository variable `BACKUP_AWS_REGION`: AWS region for the destination bucket.
- Repository/environment secret `PROD_DATABASE_URL`: connection URL for the governed production database.
- Repository/environment secret `PRODUCTION_PROJECT_ID`: expected project identifier checked against the connection URL.
- Repository/environment secret `BACKUP_S3_BUCKET`: destination bucket name.
- Optional secret `BACKUP_S3_PREFIX`: object-key prefix; defaults to `qros/production`.
- Optional secret `BACKUP_AWS_ENDPOINT_URL`: endpoint override for an S3-compatible service.

The role trust policy must allow the GitHub OIDC provider and restrict the subject to the intended repository and production environment. Grant only the permissions needed to upload, inspect, and download the backup objects in the configured bucket. Enable S3 bucket versioning before running the workflow; the workflow now checks this before connecting to the production database.

After configuration, dispatch the workflow manually and inspect the exact run. A successful code CI run is not a successful production backup. Production backup readiness remains unverified until an actual run confirms OIDC assumption, database dump, remote object/version checks, downloaded checksum equality, and final manifest equality. A separate isolated restore drill is required to prove recoverability.
