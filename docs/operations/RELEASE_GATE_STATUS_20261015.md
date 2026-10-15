# QROS Release Gate Status — 2026-10-15

## Evidence binding

- Repository: `bi421/QROS`
- Main SHA at audit: `c8cb1fce90293a861b09c88779a9d7cf125756ec`
- PR #787 merge commit: `c8cb1fce90293a861b09c88779a9d7cf125756ec`
- Exact-main CI run: [38661013344](https://github.com/bi421/QROS/actions/runs/38661013344) — success
- Supabase Database Security Tests: [38661013665](https://github.com/bi421/QROS/actions/runs/38661013665) — success
- Git Governance: [38661013371](https://github.com/bi421/QROS/actions/runs/38661013371) — success
- Repository Self-Audit: [38661013357](https://github.com/bi421/QROS/actions/runs/38661013357) — success
- Main branch protection: enabled; 13 required status checks.
- Latest production backup workflow: [38697191880](https://github.com/bi421/QROS/actions/runs/38697191880) — failed at configuration preflight.

## Status classification

### Implemented and repository-verified

- Deterministic research API foundation, workspace-scoped authorization and RLS contracts.
- Forward-only workspace RLS restoration migration merged in PR #787.
- CI, migration replay/security checks, and 23 pgTAP tenant-isolation assertions passed on the PR head before merge; main CI/security workflows passed on the exact merge SHA.
- Main branch is protected with required checks.

### Not yet proven in a deployed environment

- Staging app URL and exact deployed release SHA.
- Real signup/email confirmation and workspace provisioning.
- Complete staging Golden Path against a live app.
- Two controlled Auth identities and real API cross-workspace denial.
- Live Stripe checkout/webhook/entitlement lifecycle.
- Production observability acceptance.
- Database + object-storage + durable-job recovery drill and measured RPO/RTO.
- First external paying customer and measured delivery economics.
- Public HTTPS deployment for the QROS app.

### Release-blocking external dependencies / decisions

1. **Authoritative production target and migration provenance.** The two production ledger versions `20261008042804` and `20261008042823` still have unresolved local-source/provenance mismatch. Do not rewrite migration history or apply production migrations until target identity and provenance are reviewed.
2. **Staging identity and runtime access.** The recorded staging project ref is `yebwhcntiockckhdvawt`; its observed migration ledger has 46 rows and ends at version `20261005091724` (remote display name `20261005050000_dataset_version_feed_reconciliation`). This is historical/read-only evidence, not proof that a currently deployed app is using the current main SHA.
3. **Backup destination configuration.** Run `38697191880` failed because `BACKUP_AWS_ROLE_ARN` is missing; `BACKUP_AWS_REGION` and `BACKUP_S3_BUCKET` are also empty. Real, approved AWS OIDC role, region, and bucket values are required. Never fabricate values or weaken fail-closed checks.
4. **Recovery target.** A separate, isolated recovery database/project and independent storage destination are not yet proven provisioned. Do not use production as staging or as a recovery substitute.
5. **Local developer workstation.** The registered Windows Desktop Commander device was offline at audit time (last seen 42 hours earlier), so a fresh local clean-tree/test verification could not be performed during this audit.

## Verified configuration failure

The latest backup job log ends at preflight with:

```text
BACKUP_AWS_ROLE_ARN repository variable is not configured
```

This is a real missing external configuration, not a code/test failure. The workflow correctly stops before creating a backup.

## Safe next sequence

1. Restore access to the Windows dev workstation; verify root, branch, HEAD, clean tree, and sync with the merge SHA.
2. Identify the authoritative staging application URL and deployed SHA, and verify staging is non-production.
3. Obtain two controlled staging Auth identities in distinct workspaces.
4. Reconcile the migration ledger/source provenance using read-only evidence and clean replay. Keep historical migrations immutable; no database apply until reviewed.
5. Configure the approved AWS OIDC role, region, and bucket through repository settings; rerun the backup workflow and verify remote manifest/checksum.
6. Run the staging Golden Path and retain the run URL, exact SHA, and artifacts.
7. Provision/verify an isolated recovery target and independent storage, then run the restore drill and measure actual RPO/RTO.
8. Verify live billing, observability, and the full customer flow; only then consider production release and a paid pilot.

## Release decision

**NOT PRODUCTION-READY / RELEASE BLOCKED.**

A green CI run proves the tested repository revision passed those checks. It does not prove a live deployment, migration parity, backup/restore, billing, customer isolation through the real API, or revenue. QROS remains a research/evidence system and must not place or execute broker orders.
