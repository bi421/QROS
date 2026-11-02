# Supabase default privileges — QROS operating contract

## Scope

QROS application migrations execute as the Supabase `postgres` role. The migration `20261102000100_default_privileges_hardening.sql` removes default browser-role table and sequence grants for objects created by `postgres`, and removes the global default `PUBLIC EXECUTE` privilege for functions created by `postgres`. It then removes direct `anon` and `authenticated` function grants in `public`. The `service_role` defaults are deliberately retained for the server-only QROS API and worker.

## Platform-managed `supabase_admin` role

Do not issue `ALTER DEFAULT PRIVILEGES FOR ROLE supabase_admin` or `SET ROLE supabase_admin` from a QROS migration. Supabase reserves this internal role: the `postgres` migration role is not a member and cannot change its default privileges. Attempting to do so fails with SQLSTATE `42501` (`permission denied to change default privileges`). This is a platform boundary, not a transient CI failure.

Supabase uses `supabase_admin` for internal administration and extension installation. Its default grants apply to extension-owned objects, not ordinary QROS application tables created by migrations as `postgres`. Do not attempt to revoke those grants from objects that QROS does not own.

## Extension placement

For every new extension, specify a schema explicitly. Prefer the `extensions` schema when the extension supports it; otherwise use the extension's required dedicated schema. Do not install extensions into `public` by relying on the default search path. Existing extension migrations are append-only history and must not be rewritten as part of this change.

## Function EXECUTE detail

PostgreSQL grants `EXECUTE` on new functions to `PUBLIC` by default. A schema-scoped default-privilege `REVOKE` cannot remove a global default grant. Therefore QROS revokes `EXECUTE` from `PUBLIC` globally for functions created by `postgres`, then removes any direct `anon`/`authenticated` grants in `public`. Each function that needs to be callable by the API or worker must receive an explicit grant to the intended server role.

## Verification boundary

The pgTAP test creates rolled-back probe objects under the `postgres` migration role and verifies browser denial plus retained `service_role` access. It does not claim to alter or certify Supabase's platform-managed `supabase_admin` defaults. Production/staging project migration parity and tenant-isolation checks remain separate release gates.

## References

- Supabase KB: [Can't change the default privileges of supabase_admin in the public schema](https://supabase.com/kb/troubleshooting/cant-change-the-default-privileges-of-supabase_admin-in-the-public-schema)
- PostgreSQL 17: [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/17/sql-alterdefaultprivileges.html)
