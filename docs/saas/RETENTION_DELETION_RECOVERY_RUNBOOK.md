# Retention Deletion Recovery Runbook

## Scope

This runbook covers the destructive retention boundary where a resource delete
and its completion audit are separate side effects.

## Safety rule

Production destructive deletion stays disabled until the target environment
has a durable, atomic implementation of the deletion operation store, plus
backup and restore verification.

## Normal operation

1. Resolve the tenant from authorized server context.
2. Evaluate retention eligibility.
3. Require explicit approval.
4. Resolve dependencies and verify zero active references.
5. Reserve a unique tenant-scoped deletion operation atomically.
6. Append the pre-delete deletion_approved audit event.
7. Perform the idempotent resource delete.
8. Append deletion_completed.
9. Persist terminal COMPLETED state.

## Reconciliation path

If step 7 succeeds but step 8 fails:

1. Do not retry the destructive delete blindly.
2. Persist RECONCILIATION_REQUIRED for the same tenant-scoped operation ID.
3. Reconcile the resource's actual storage/database state.
4. Reconcile the missing completion audit event.
5. Record the reconciliation result.
6. Only then transition the operation to its terminal state.

If the delete outcome is unknown, treat the operation as unsafe to retry until
the target resource state is verified.

## Idempotency requirements

A production operation store must make reservation atomic and preserve
terminal state across worker retries. A read-then-write sequence is not
sufficient because concurrent workers can both observe an absent operation.

## Current implementation boundary

The repository contains the provider-neutral operation-state contract and an
in-memory test implementation. No production destructive-deletion adapter is
enabled by this change.
