# QROS SaaS Disaster Recovery

## Verification state

| Surface | Repository implementation | Executable prerequisites | Verified |
|---|---|---|---|
| PostgreSQL logical backup | `scripts/backup_verify.py` + production backup workflow | DB URL + PostgreSQL clients | **Not executed** |
| PostgreSQL restore | Disposable matching-major PostgreSQL container | Docker + source DB + clients | **Not executed** |
| Migration/security verification | `scripts/verify_migrations.py` + migration history | Restored DB + `psql` | **Not executed against a restored DB** |
| Tenant isolation | pgTAP + real Supabase integration tests | Real Supabase target + credentials | **Not executed as a recovery drill** |
| Dataset integrity | `dataset_version.content_sha256` source/restore comparison | Source + restored DB | **Not executed** |
| Storage recovery | `storage-recovery-drill.yml` + `storage_recovery_verify.py` | Staging Supabase + independent S3 | **Not executed** |
| Queue/job recovery | Durable leases, heartbeat, bounded retry, idempotency | Real worker-loss drill | **Not executed** |
| Application recovery | Health/readiness and governed API gates | Recovered environment | **Not executed** |
| RPO/RTO | Measurement procedure is documented | Real recovery drill | **Not verified** |

## Boundary

Documentation is not execution. CI is not production recovery.

A successful `pg_dump` proves only that a logical backup was produced. A successful `pg_restore` proves only that the dump can be loaded into the selected PostgreSQL target. The recovery gate additionally requires schema/security checks, immutable dataset identity checks, governed-record integrity checks, and an environment-backed application/security drill.

Supabase database backups do not include objects stored through the Storage API, so Storage recovery is a separate recovery surface.

## Database recovery procedure

### Prerequisites

- `QROS_BACKUP_DATABASE_URL` or `--database-url`
- explicit source authorization via `QROS_BACKUP_SOURCE_ENVIRONMENT` or `--source-environment local|staging|recovery`
- `pg_dump`, `pg_restore`, and `psql`

The database URL alone is insufficient: the source environment must be explicitly authorized before any `pg_dump` runs. Production source targeting is not authorized by this verifier. `--skip-restore` is backup-only; it is not a dry-run and does not bypass source authorization.
- Docker with access to the source PostgreSQL major image
- network access from the runner to the source database
- sufficient disk for the dump and disposable restore

### Deterministic verifier

```bash
python scripts/backup_verify.py --database-url "$QROS_BACKUP_DATABASE_URL" --source-environment staging
```

The verifier fails closed when prerequisites are missing and emits `backup/qros_restore_report.json`. It verifies:

1. non-empty custom-format `pg_dump`;
2. source immutable dataset-version IDs, version numbers, and SHA-256 identities;
3. restore into a fresh PostgreSQL container using the source PostgreSQL major version;
4. required QROS tables;
5. RLS enabled on required tenant/governed tables;
6. critical governed-record counts;
7. restored dataset-version identities;
8. repository migration/security invariants against the restored database.

`--skip-restore` is explicitly **BACKUP_ONLY** and never reports restore verification.

### Not proven by this script

Supabase Auth/Data API behavior, Storage objects, worker-loss recovery, and RPO/RTO still require their environment-backed drills.

## Full recovery drill

1. Freeze writes and record the incident/change identifier.
2. Record source release commit, migration version, and recovery point.
3. Restore the database into an isolated recovery target.
4. Run the database verifier.
5. Run real tenant-isolation/security tests against the recovery target.
6. Restore independent Storage objects and verify byte-for-byte SHA-256 identity.
7. Verify durable job leases, idempotency, retry state, and provenance after simulated worker loss.
8. Deploy the exact release commit and run health/readiness and governed Golden Path checks.
9. Record restore completion time and calculate observed RTO.
10. Compare the recoverable timestamp with the simulated failure timestamp and calculate observed RPO.
11. Preserve the evidence package and operator sign-off before traffic is re-enabled.

Do not assign an RPO/RTO target from documentation before a drill measures it.
