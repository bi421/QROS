# Automated repository self-audit

QROS runs the repository self-audit on every pull request targeting `main`,
every push to `main`, daily at 03:17 UTC, and on manual dispatch.

## Current invariant

Database migration files are append-only. The audit compares the current Git
tree against reviewed policy baseline
`c7976fa555ce5721f112bb0fb03e5b8b2e078c73` and fails if a migration that
existed at that baseline is modified, renamed, or deleted. Adding a new
forward migration is allowed. The audit does not apply SQL or connect to a
database.

A missing Git baseline, shallow checkout, or history not descended from the
baseline fails closed rather than reporting a false pass.

## Response to a failure

1. Open the failed Actions run and record the exact HEAD SHA and changed path.
2. Do not rewrite or amend an existing migration.
3. Create a new timestamped forward migration and add a regression/governance test.
4. If the policy baseline itself needs to change, require explicit human review
   of the baseline change; never update it merely to silence a failing audit.

## Limits

This audit currently covers append-only migration history. It is not a general
proof that every dataset, report, or runtime artifact is immutable, and it does
not verify deployed database parity, backup recoverability, calibration, or
trading performance. Those require separate evidence-producing checks.
