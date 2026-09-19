# Retention and deletion policy

QROS separates retention **eligibility** from destructive deletion.

## Safety contract

A resource can be considered deletion-eligible only when all of these are true:

1. Its resource type is explicitly allowed by the retention policy.
2. The minimum retention window has elapsed.
3. The resource has zero active references.
4. No legal hold is present.

Any failed or unknown safety condition must resolve to **RETAIN**. The policy is
deterministic and side-effect free; it does not delete database rows or storage
objects.

## Dependency rule

Historical research data must not be deleted while referenced by a durable
research run, result, evidence record, claim, or artifact manifest. The future
retention executor must resolve those references before calling a destructive
adapter.

## Production boundary

This contract does not authorize or execute destructive production operations.
Operational deletion requires a separately reviewed executor, audit event,
tenant authorization, dependency check, and recovery/runbook coverage.
