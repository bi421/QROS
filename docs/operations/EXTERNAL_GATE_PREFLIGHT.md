# External Gate Preflight

Status: **repository-side deterministic preflight only**.

This document separates configuration prerequisites from environment execution.
The preflight never prints secret values and never claims that a remote target is
reachable.

## Staging application / Golden Path

Run:

```bash
python scripts/verify_environment_prerequisites.py --profile staging
```

Required:
- `QROS_STAGING_BASE_URL`
- `QROS_STAGING_JWT`
- `QROS_STAGING_ISOLATION_JWT`

The check requires HTTPS and requires the two JWT values to be distinct. It does
not verify that the identities exist, belong to distinct workspaces, or that the
application endpoint is reachable.

## Disaster recovery infrastructure

Run:

```bash
python scripts/verify_environment_prerequisites.py --profile dr
```

Required:
- staging source environment/project identity;
- staging Supabase URL and service-role credential;
- isolated recovery target environment and identity;
- independent S3 bucket, region, and scoped AWS credentials.

The check rejects staging/production recovery targets and rejects a recovery
target identity equal to the staging project identity. It does not provision or
execute recovery infrastructure.

## Governed production forward migration

Run:

```bash
python scripts/verify_environment_prerequisites.py --profile production-migration
```

Required:
- `SUPABASE_ACCESS_TOKEN`
- `PRODUCTION_DB_PASSWORD`
- `PRODUCTION_PROJECT_ID`

The project reference must equal the governed QROS production project
`pvhdsngxyoiqhqwujfjt`. This check does not authorize or execute a migration.

## Evidence boundary

PASS from this utility means **configuration prerequisites are present and
internally consistent**. It does not mean:
- authentication succeeded;
- the application is deployed;
- staging tenant isolation passed;
- recovery infrastructure exists;
- a backup/restore drill ran;
- production was mutated;
- production migration parity is closed.
