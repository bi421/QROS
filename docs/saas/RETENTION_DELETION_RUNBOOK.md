# Retention deletion operational runbook

This runbook defines the operational boundary for the fail-closed retention executor.

## Preconditions

A deletion request must have all of the following:

1. Retention policy eligibility.
2. Explicit approval.
3. Tenant authorization for the resource.
4. A successful dependency check against durable references.
5. An available audit sink.
6. A concrete delete operation.

If any precondition is missing, deletion must not occur.

## Execution sequence

1. Evaluate the immutable retention candidate.
2. Authorize the tenant/resource boundary.
3. Resolve durable dependencies.
4. Record the approval audit event.
5. Execute the destructive adapter.
6. Record completion.

The pre-delete audit event is a safety boundary: if it fails, the delete operation is not called.

## Recovery

The current executor does not automatically retry or roll back a destructive operation. A failed post-delete audit therefore requires operational reconciliation between the delete adapter and the audit sink.

Before production destructive deletion is enabled, the deployment must provide:

- durable audit-event persistence;
- an idempotent delete operation;
- a reconciliation procedure for delete-success/audit-failure;
- backup/restore verification for affected durable stores;
- operator evidence that tenant authorization and dependency checks query the target environment.

## Production boundary

The executor contract is implemented and tested, but production deletion remains disabled until the target-environment authorization, dependency, audit, recovery, and backup/restore gates are observed.
