# QROS SaaS execution plan

1. Scientific core — frozen and independent from HTTP, billing and tenancy.
2. Identity — verified token -> server-side workspace membership -> plan.
3. Data — immutable content-addressed dataset versions in private storage.
4. Execution — database-backed research runs + durable identifier-only queue.
5. Reliability — explicit state machine, leases, retries, idempotency.
6. API — versioned contract, request IDs, rate limits, stable errors.
7. Billing — server-authoritative entitlements and verified idempotent events.
8. Security — RLS read isolation, server-only writes, secret isolation.
9. Operations — CI evidence, migrations, backups, observability and SLOs.
10. Release — staging E2E, reproducibility manifest, rollback and incident runbook.

A feature is complete only when implementation, tests, migration compatibility,
deployment verification and operational evidence exist.
