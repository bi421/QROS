# QROS Backup / Restore Drill V1

Status: **RUNBOOK ONLY — EXECUTION REQUIRED**

This runbook defines the evidence required to close the QROS disaster-recovery gate. It does not claim that a restore drill has been executed.

## Scope

The drill must validate four independent recovery surfaces:

1. Supabase Postgres database.
2. Supabase Storage objects used by QROS.
3. Durable research jobs and idempotency state.
4. Application deployment/configuration required to resume service.

Supabase database backups do **not** restore Storage API objects; storage recovery must therefore be tested separately.

## Preconditions

- Use a non-production restore target whenever possible.
- Record the exact source project ref, source release commit, migration version, and drill start timestamp.
- Do not copy production secrets into the restore target.
- Establish a unique drill dataset containing:
  - one workspace;
  - one dataset and immutable version;
  - one research run;
  - one research claim;
  - one evidence record;
  - one content-addressed artifact;
  - one queued/completed job state.
- Record hashes/IDs for every drill object before the failure simulation.

## Database recovery drill

1. Confirm the production backup/PITR capability and available recovery window.
2. Select a restore point immediately before the recorded drill dataset.
3. Restore to a new project or other isolated recovery target.
4. Verify:
   - migration/schema objects exist;
   - tenant RLS remains enabled;
   - server-only grants remain denied to client roles;
   - `qros_session_is_active(uuid,uuid)` exists with its service-role-only execution boundary;
   - the drill workspace and research records are internally consistent;
   - content hashes and immutable versions match the pre-drill evidence.
5. Record restore completion time and calculate observed RTO.
6. Compare the latest recoverable timestamp with the simulated failure timestamp and calculate observed RPO.

Supabase documents that database backups cover the database but not Storage API objects, and that PITR can provide finer-grained recovery points on eligible paid projects.

## Storage recovery drill

1. Create a drill artifact in the private QROS storage bucket.
2. Record object path, content hash, size, and metadata.
3. Simulate object loss only in the isolated recovery environment.
4. Restore the object from the chosen independent storage backup/export mechanism.
5. Recompute the content hash and compare with the recorded manifest.
6. Verify tenant authorization still prevents cross-workspace download.
7. Record observed recovery time and any data-loss interval.

## Queue / job recovery drill

1. Create a durable research job with a deterministic idempotency key.
2. Record job ID, input artifact hash, state, attempt count, and provenance.
3. Simulate worker loss after lease acquisition.
4. Restore the database/recovery target.
5. Verify the lease/heartbeat/retry state permits safe recovery.
6. Re-run the job using the same idempotency key.
7. Verify that the result is not duplicated and remains provenance-linked to the same input hash.

## Application recovery drill

1. Deploy the exact release commit associated with the recovery snapshot.
2. Inject only recovery-target credentials.
3. Verify `/healthz` and `/readyz`.
4. Verify authenticated tenant resolution.
5. Verify session revocation behavior.
6. Verify dataset, research-run, claim, evidence, and result reads/writes.
7. Verify structured errors and request correlation.
8. Verify metrics/alerts are available.

## Evidence package

The drill is complete only when the repository contains:

- source release commit;
- source migration version;
- backup/PITR restore point;
- restore target project reference;
- pre-drill object manifest;
- post-restore object manifest;
- database verification results;
- storage verification results;
- queue/job recovery results;
- observed RPO;
- observed RTO;
- incident/recovery notes;
- operator sign-off.

## Release rule

Do not mark the QROS backup/restore gate `[x]` from documentation alone. A real restore exercise with recorded RPO/RTO and verification evidence is required.

Supabase backup guidance: https://supabase.com/docs/guides/platform/backups
