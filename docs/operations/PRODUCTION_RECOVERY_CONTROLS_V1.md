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
