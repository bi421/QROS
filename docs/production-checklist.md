# QROS Production Readiness Checklist

## Infrastructure
- [ ] Exact release CI green
- [ ] Staging deployment verified
- [ ] Production deployment verified
- [ ] Secrets/config validated
- [ ] Monitoring/alerting live
- [ ] Backup and restore tested

## Tenant security
- [ ] Real Auth provider wired
- [ ] Workspace membership verified
- [ ] Cross-tenant attack suite passes
- [ ] Role matrix passes
- [ ] RLS and grants audited

## Research integrity
- [ ] Dataset versions immutable
- [ ] Content hashes verified
- [ ] Run provenance verified
- [ ] Result manifest verified
- [ ] Evidence lineage verified
- [ ] Claim/evidence governance verified

## Operations
- [ ] Queue recovery verified
- [ ] Worker lease/retry recovery verified
- [ ] Request correlation traceable
- [ ] p95 latency measured
- [ ] API error rate measured
- [ ] RPO/RTO restore-tested

## Product
- [ ] Golden Path staging
- [ ] Golden Path production
- [ ] Time -> First Valid Research Result measured
- [ ] Real user feedback collected
