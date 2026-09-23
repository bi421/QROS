# QROS SaaS Disaster Recovery

## Targets
- RPO: <24 hours for the PostgreSQL system of record.
- RTO: <4 hours for a validated restore path.

## Recovery sequence
1. Freeze writes and record the incident/change identifier.
2. Select the most recent verified PostgreSQL backup.
3. Verify its SHA-256 and size before restore.
4. Restore into a fresh PostgreSQL/Supabase environment.
5. Apply migrations newer than the backup and run migration/security verification.
6. Restore or rehydrate private Storage objects from the independent object backup.
7. Verify dataset SHA-256 identities and tenant isolation.
8. Run the exact-release health and integration gates.
9. Re-enable traffic only after the restored environment is independently verified.

backup_verify.py deliberately fails when the backup source or restore tooling is unavailable; a missing backup is never treated as a successful drill.
