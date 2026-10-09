# Minimal customer pilot before Product UI

## Objective

Validate that one invited customer can complete the existing governed research workflow and receive reproducible evidence before investing in a self-service UI. This is a technical/product validation pilot, not a claim of production readiness or trading performance.

## Scope

- Duration: 7 calendar days after all entry gates pass.
- Participants: one design-partner customer and at most one analyst under the same customer workspace.
- Product surface: existing API plus documented operator-assisted onboarding. No public signup, public UI, live-trading integration, or automated billing.
- Data: synthetic XAUUSD M1 fixture first; then customer-provided data only if the customer is authorized to share it and staging isolation has passed.
- Environment: isolated staging only until all release gates and data handling terms are approved.

## Entry gates — all required

- [ ] Exact candidate commit SHA and successful required CI checks recorded.
- [ ] Migration drift ledger has a reviewed disposition for every finding in `docs/MIGRATION_DRIFT_RECONCILIATION.md`.
- [ ] Staging project and URL are accessible; two separately authenticated identities in separate workspaces are available.
- [ ] Staging schema parity passes for the exact candidate SHA.
- [ ] Cross-tenant API, database RLS, and private Storage access-denial tests pass.
- [ ] Golden Path passes: dataset upload → immutable version/content hash → research run → worker completion → result/evidence/report retrieval.
- [ ] Independent backup/restore drill succeeds and restored content hashes match.
- [ ] Customer consent, data ownership/retention terms, support contact, and pilot stop procedure are recorded.
- [ ] No production credentials, service-role keys, or real customer data are placed in logs or repository artifacts.

If any entry gate fails, do not onboard the customer or upload their data. Continue with synthetic fixtures and resolve the blocker.

## Customer workflow

1. Operator creates/invites the customer identity and workspace using the existing supported path; no direct production database writes.
2. Customer signs in and confirms access to only their own workspace.
3. Customer uploads the agreed CSV dataset or sends it through the approved secure intake route.
4. API returns dataset/version identifiers and a content hash.
5. Customer submits one governed research run; operator records the request ID and run ID.
6. Customer retrieves status and the final report/evidence through the API.
7. Customer repeats the same run request once to verify idempotency and checks that provenance remains tied to the immutable dataset version.
8. Operator performs a negative test with the second tenant identity and records denial evidence; never use another customer's real data.

## Seven-day schedule

| Day | Work | Exit evidence |
|---|---|---|
| 1 | Reconfirm SHA, migration dispositions, staging access, and recovery | Gate checklist and links |
| 2 | Tenant identity/workspace setup and permission checks | Redacted access log; cross-tenant denial |
| 3 | Dataset intake and immutable versioning | Dataset ID, version ID, SHA-256 |
| 4 | Submit and complete governed research run | Request ID, run ID, worker status |
| 5 | Retrieve report/evidence; repeat request | Report/evidence hashes and idempotency result |
| 6 | Customer walkthrough and usability interview | Recorded answers, defects, support time |
| 7 | Review success metrics and make go/no-go decision | Signed pilot summary and prioritized backlog |

## Success criteria

Pilot succeeds only if all are true:

- One customer independently completes the agreed workflow with no data-isolation incident.
- 100% of submitted runs have traceable request/run IDs, immutable dataset-version linkage, and retrievable evidence/report.
- Duplicate submission behavior matches the documented idempotency contract.
- Cross-tenant negative tests deny access to API results and private Storage objects.
- No unresolved severity-1 security, data-loss, or reproducibility defect.
- Customer confirms the output is useful for a real research task and agrees to a specific next step.
- Operator time and support incidents are measured rather than guessed.

Do not use profitable trading, predictive accuracy, or investment returns as pilot success claims unless separately measured with a pre-registered out-of-sample evaluation.

## Stop conditions

Stop the pilot immediately on any cross-tenant data exposure, unexpected production write, unexplained evidence/provenance mismatch, data loss, or inability to restore. Preserve redacted logs and hashes; revoke pilot access if needed; do not silently repair evidence.

## Product UI decision

Do not build the full Product UI before the pilot. If the pilot passes, the smallest UI scope is:

1. Invite/login and workspace context.
2. Dataset upload with validation and immutable-version confirmation.
3. Research run submission and visible queued/running/failed/completed status.
4. Result/report/evidence view with IDs, hashes, timestamps, and failure details.

Defer billing dashboard, self-service team administration, complex visualization, and live trading until the pilot demonstrates demand and the core safety gates remain green.

## Pilot report template

- Candidate SHA:
- Staging environment / run URLs:
- Customer participant count:
- Dataset ID / version ID / content hash:
- Request ID / research run ID:
- Evidence/report hash:
- Cross-tenant denial test result:
- Restore drill artifact:
- Workflow completion rate:
- Operator minutes per workflow:
- Customer feedback / next-step commitment:
- Open defects and severity:
- Decision: GO / EXTEND / STOP:
