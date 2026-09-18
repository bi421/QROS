# QROS SaaS Launch Checklist — 2026

## Implemented in repository
- [x] Versioned API boundary
- [x] Fail-closed authentication abstraction
- [x] Supabase JWT + server-side membership/plan resolution
- [x] Tenant-scoped dataset/version model
- [x] Content-addressed immutable dataset objects
- [x] Durable Supabase queue with identifier-only messages
- [x] Tenant-scoped persistent research-run store
- [x] RLS read isolation and server-only writes
- [x] Idempotency key primitive
- [x] Request correlation IDs
- [x] Bounded API rate limiter for single-instance deployments
- [x] Worker state machine
- [x] Billing webhook signature/idempotency boundary
- [x] Private dataset storage bucket
- [x] Operational lease columns for recoverable workers
- [x] Governance + health evidence CI gate

## Environment/deployment dependent
- [ ] Create/configure production Supabase project
- [ ] Apply migrations in order
- [ ] Configure production secrets
- [ ] Configure a shared rate limiter for multi-instance deployment
- [ ] Deploy API and worker separately
- [ ] Configure billing provider and verified webhook endpoint
- [ ] Configure domain/TLS/WAF
- [ ] Configure backups and perform a restore drill
- [ ] Run staging end-to-end research execution
- [ ] Run production security review and dependency scanning
- [ ] Define SLOs, alerting and on-call procedure

These items require target production accounts and deployment infrastructure;
they cannot truthfully be marked complete from repository-only access.
