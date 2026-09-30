# QROS — CURRENT STATE, COMPLETION ROADMAP & PRODUCTION CHECKLIST

Last verified snapshot: 2026-09-30

IMPORTANT: This date is a historical verification timestamp, not a substitute for live-state verification.
Repository: bi421/QROS
Production branch: main
Production SHA: b584a10d7853f9d5d4297c5202ef130b19c3faa5

---

# 1. PURPOSE

This document is the persistent project-state and completion roadmap for QROS.

Its purpose is to prevent:

- losing the current project state,
- repeating already-completed work,
- reopening frozen evidence,
- confusing production-main evidence with open PRs,
- claiming deployment before real deployment exists,
- claiming customer readiness before a real customer journey succeeds,
- making unnecessary changes to the scientific core,
- manufacturing evidence through artificial database or authentication actions.

The governing principle is:

REAL IMPLEMENTATION
→ VERIFIED TESTS
→ PRODUCTION-MAIN EVIDENCE
→ REAL DEPLOYMENT
→ REAL CUSTOMER SMOKE TEST
→ CUSTOMER-READY PRODUCT

---


# 1A. AI EXECUTION CONTRACT

This roadmap is an AI-executable project-state contract, not merely a planning document.

Any future AI agent working on QROS MUST:

1. Read this document before making changes.
2. Verify the live repository state before trusting any statement in this document.
3. Verify the actual `origin/main` SHA before starting work.
4. Treat this document as guidance and state memory, NOT as evidence.
5. If the live repository contradicts this document, report:
   - DOCUMENTED STATE
   - ACTUAL STATE
   - EXACT CONTRADICTION
   - REQUIRED RESOLUTION
6. Never silently overwrite, reset, rebase, delete, or discard unrelated user work.
7. Never force-push without explicit human authorization.
8. Never merge a pull request automatically unless explicitly authorized.
9. Never fabricate deployment, authentication, customer, billing, scientific, or production evidence.
10. Before changing code, identify the concrete blocker and the evidence that the change is expected to produce.
11. After each completed task, report:
    FACT → COMMAND/TOOL → RESULT → EVIDENCE → NEXT ACTION
12. Continue autonomously through repository-accessible work.
13. Stop and request human action only when the remaining blocker genuinely requires external access, credentials, approval, payment, account configuration, or another action unavailable to the agent.

The agent must prefer verified repository facts over remembered conversation state.

# 2. CURRENT PRODUCTION TRUTH

## Production SHA

b584a10d7853f9d5d4297c5202ef130b19c3faa5

Commit:

evidence(phase52): record XAUUSD M1 permutation test

Parent:

5d6eea14c8cd8194252479a6ff8a5d97db97fea8

GitHub main currently points to:

b584a10d7853f9d5d4297c5202ef130b19c3faa5

This SHA is the frozen production baseline.

DO NOT replace this baseline with an older SHA.

---

# 3. PRODUCTION CI STATUS

Production-main evidence previously verified:

- CI #2870 — SUCCESS
- Release Readiness #887 — SUCCESS
- Supply Chain Security #40 — SUCCESS
- Supabase Database Security #1008 — SUCCESS

Relevant production jobs were verified successful, including:

- Python 3.11
- Python 3.12
- C++ / nanobind Quant Engine
- Static Type Check
- Property-Based Tests
- Health Evidence

Therefore:

PRODUCTION CI = PASS

---


# EVIDENCE HIERARCHY

Use the following evidence levels when describing QROS state:

- LEVEL 0 — CLAIM: stated intent, plan, or expectation only.
- LEVEL 1 — CODE: implementation exists in a repository revision.
- LEVEL 2 — LOCAL TEST: implementation passes a reproducible local test.
- LEVEL 3 — CI: implementation is verified by the relevant GitHub CI workflow.
- LEVEL 4 — PRODUCTION: the exact production SHA is verified running in the real production environment.
- LEVEL 5 — REAL EXTERNAL: a real external/customer-facing flow has been successfully exercised and independently evidenced.

Rules:

- Never describe LEVEL 0 as implementation.
- Never describe LEVEL 1 as tested.
- Never describe LEVEL 2 as production verified.
- Never describe LEVEL 3 as deployed.
- Never describe LEVEL 4 as a successful customer journey unless the customer journey itself was tested.
- Never describe LEVEL 5 evidence using weaker or ambiguous wording.
- Always identify the highest evidence level actually achieved.

# 4. PHASE 5.2 STATUS

## STATUS: FROZEN / CLOSED

Phase 5.2 permutation evidence is frozen at:

b584a10d7853f9d5d4297c5202ef130b19c3faa5

Artifact:

artifacts/xauusd_m1_permutation_test.json

The commit added one evidence artifact only.

No production Python implementation was changed.

No C++ implementation was changed.

No Quant Engine implementation was changed.

No worker/queue implementation was changed.

No Phase 5.2 rerun is required.

---

# 5. PHASE 5.2 RECORDED EVIDENCE

Permutation count:

1000

Permutation type:

label_shuffle

Seed base:

20260910

Complete events:

24850

OOS events:

22000

Folds:

44

Train:

2000

Validation:

500

Step:

500

Holdout:

500

Observed delta Brier:

-0.0010344996

Observed delta LogLoss:

-0.0020706827

Brier extreme permutations:

0 / 1000

Brier empirical p:

0.000999000999000999

LogLoss extreme permutations:

0 / 1000

LogLoss empirical p:

0.000999000999000999

Scientific classification:

OOS_STATISTICAL_SUPPORT_ONLY_NO_TRADING_EDGE_CLAIM

IMPORTANT:

This evidence does NOT establish:

- profitability,
- transaction-cost-adjusted profitability,
- live trading performance,
- future performance,
- universal XAUUSD predictability,
- a guaranteed trading edge.

It is statistical evidence against the tested label-shuffle null for the specified OOS probability comparison.

---

# 6. PHASE 5.2 SOURCE PROVENANCE

Event/outcome artifact:

artifacts/xauusd_m1_real_events_outcomes.json

SHA256:

8a2ba847da994dc0f570b7d63bdae3ff7d976d87260ff0f533a83b26079843e4

Walk-forward artifact:

artifacts/xauusd_m1_walkforward.json

SHA256:

e08786bfe8b944823b1f20087e58112fb8d920f394979ecf5fd79d6cc7a49cc2

Dataset SHA256:

632950ee767eb8968a00331e6f8da35d3bc73e937bc3ceb5c1b15f596939da

No synthetic repair, interpolation, FFILL, resampling, or fabricated observations were identified in the verified evidence chain.

This does NOT mean every possible raw-data property has been universally proven.

---

# 7. CUSTOMER-READY ARCHITECTURE ALREADY IMPLEMENTED

The main governed customer execution chain exists:

AUTHENTICATED USER
    ↓
WORKSPACE
    ↓
OWNER MEMBERSHIP
    ↓
FREE ENTITLEMENT
    ↓
DATASET
    ↓
IMMUTABLE DATASET VERSION
    ↓
RESEARCH RUN
    ↓
DURABLE QUEUE
    ↓
GOVERNED WORKER
    ↓
LEASE
    ↓
FROZEN SCIENTIFIC RUNNER
    ↓
RESULT
    ↓
EVIDENCE / PROVENANCE
    ↓
REPORT / API RETRIEVAL

This is the core QROS execution path.

---

# 8. AUTHENTICATION

Implemented:

- Supabase Auth
- JWT verification
- issuer validation
- audience validation
- bearer authentication
- authenticated user identity
- server-side service-role usage
- browser-safe publishable key

Critical security rule:

The browser MUST NEVER receive:

SUPABASE_SERVICE_ROLE_KEY

Only the publishable key may be exposed to browser-side code.

---

# 9. CUSTOMER SELF-SERVICE ONBOARDING

Implemented in:

8980a7fed5a0cef31843613e92d80da766fe25ba

Path:

NEW PERSON
→ /onboarding
→ Supabase Auth signup
→ authenticated session
→ POST /v1/workspaces
→ owner membership
→ FREE entitlement
→ GET /v1/me

The onboarding implementation supports:

- immediate-session signup
- confirmation-required signup
- authenticated bearer session
- workspace provisioning
- owner assignment
- FREE entitlement

However:

THE CODE EXISTS.

THE PUBLIC PRODUCTION SITE DOES NOT YET EXIST.

Therefore the complete real customer journey has NOT yet been proven.

---

# 10. WORKSPACE PROVISIONING

Implemented and production verified.

Provisioning guarantees:

- authenticated identity determines owner
- client cannot choose another user as owner
- workspace/member/subscription creation is atomic
- concurrent duplicate provisioning is protected
- existing workspace returns conflict
- existing tenant/RLS primitives are reused

Production migration and authorization were verified.

---

# 11. DATASET SYSTEM

Implemented:

- tenant-scoped dataset creation
- immutable dataset versions
- dataset identity
- SHA-256 content identity
- provenance
- tenant-scoped storage paths

Dataset registration is available through:

POST /v1/datasets

---

# 12. RESEARCH RUN SYSTEM

Implemented:

POST /v1/research-runs

Capabilities include:

- tenant authorization
- idempotency
- usage limits
- concurrency limits
- frozen workflow
- durable queue enqueue

---

# 13. QUEUE / WORKER

Implemented:

- durable qros-research-runs queue
- receive
- ACK
- visibility timeout
- governed Research Worker
- lease acquisition
- heartbeat
- lease fencing
- result persistence

ResearchWorker.run_once() is implemented.

---

# 14. SCIENTIFIC EXECUTION

Implemented:

GovernedResearchExecutor

It resolves:

immutable dataset
→ governed execution
→ FrozenXauusdM1Runner
→ result
→ evidence

The scientific execution boundary is already implemented.

DO NOT redesign this merely to solve deployment.

---

# 15. TENANT ISOLATION

Tenant isolation has been hardened and verified through:

- workspace membership
- tenant authorization
- tenant-scoped datasets
- tenant-scoped research runs
- tenant-scoped result access
- RLS
- authentication identity
- authorization checks

Do not weaken or bypass these controls for deployment testing.

---

# 16. BILLING STATUS

Billing foundation exists.

Implemented / present:

- FREE / PRO / TEAM / ENTERPRISE entitlement model
- usage limits
- concurrency policies
- quota enforcement
- subscription state
- signed billing webhook
- deduplication
- server-side feature enforcement

Not yet implemented as a complete commercial purchase experience:

- checkout
- customer billing portal
- payment lifecycle UI
- upgrade flow
- downgrade flow
- cancellation flow
- failed-payment customer workflow

Billing is NOT the current first blocker because a FREE customer can enter the research system without payment.

---

# 17. USER-VISIBLE PRODUCT STATUS

API-level customer functionality is substantially implemented.

But a complete public customer web experience is not yet deployed.

Missing production proof:

- public website
- public HTTPS endpoint
- deployed /onboarding
- real browser signup
- real session
- real workspace creation
- real /v1/me confirmation

Therefore:

API PRODUCT = SUBSTANTIALLY IMPLEMENTED

PUBLIC CUSTOMER PRODUCT = NOT YET DEPLOYED

---

# 18. PRODUCTION DOCKER ARTIFACT

Dockerfile is present and internally coherent.

Runtime image:

python:3.12.14-alpine3.24

Application:

researchos.saas.runtime:app

Start command:

uvicorn researchos.saas.runtime:app --host 0.0.0.0 --port 8000

Container port:

8000

Health endpoint:

/healthz

Required server secrets:

SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_PUBLISHABLE_KEY

Billing secret:

BILLING_WEBHOOK_SECRET

Container security:

- runs as nobody
- read-only root filesystem
- dropped capabilities

docker-compose.yml is a local/container wrapper.

It is NOT proof of production hosting.

IMPORTANT:

A successful Docker image build is NOT a production deployment.

---


# BLOCKER CLASSIFICATION

Every remaining blocker MUST be classified before deciding how to respond.

- CLASS A — REPOSITORY: code, tests, configuration, migrations, or documentation that the agent can modify.
- CLASS B — CI: workflow, runner, permissions, or CI-only failure that can be diagnosed through repository/GitHub evidence.
- CLASS C — GITHUB: repository settings, branch protection, PR state, Actions permissions, or other GitHub-side configuration.
- CLASS D — SUPABASE: database, Auth, Storage, RLS, project settings, or other Supabase-side configuration.
- CLASS E — DEPLOYMENT PROVIDER: VPS, Render, Railway, managed container host, DNS, HTTPS, runtime environment, or provider-side configuration.
- CLASS F — HUMAN-ONLY EXTERNAL ACTION: credential entry, account ownership, billing/payment approval, secret creation unavailable to the agent, or an action that explicitly requires the human.

Do not write repository code to compensate for a CLASS C/D/E/F blocker unless new evidence proves that repository code is the actual root cause.

When a blocker is found, record:

BLOCKER CLASS
→ EXACT BLOCKER
→ EVIDENCE
→ WHAT THE AGENT CAN DO NOW
→ WHAT REQUIRES HUMAN ACTION

# 19. CURRENT DEPLOYMENT STATUS

DEPLOYMENT ACCESS:

NOT AVAILABLE

Docker build:

NOT EXECUTED in the connected environment

Production deployment:

NOT EXECUTED

Public HTTPS:

NONE

/onboarding:

NOT DEPLOYED

Supabase Auth redirect:

NOT VERIFIED

Real signup:

NOT EXECUTED

Real session:

NOT EXECUTED

Real workspace:

NOT EXECUTED

Owner + FREE:

NOT EXECUTED

/v1/me:

NOT EXECUTED

Therefore:

CUSTOMER JOURNEY = BLOCKED

---


# 19A. LIVE EXTERNAL VALIDATION SNAPSHOT — 2026-10-01

This section records evidence obtained from the currently connected GitHub and Supabase environments during autonomous execution.

## GitHub

Verified:

- Repository: `bi421/QROS`
- Default branch: `main`
- Current `main` SHA: `b584a10d7853f9d5d4297c5202ef130b19c3faa5`
- Roadmap branch: `docs/current-state-completion-roadmap`
- Roadmap branch HEAD: `a9d269dbb0d8613db568b83bf935ddf82dbe2d79`
- Roadmap PR: `#417`
- PR #417 base: `main`
- PR #417 head: `a9d269dbb0d8613db568b83bf935ddf82dbe2d79`
- PR #417: OPEN / NOT MERGED

The PR-triggered Release Readiness Static Gate for the roadmap commit completed successfully as run #888. CI #2871, Supply Chain Security #41, and Supabase Database Security Tests #1009 were still running at the time of this snapshot.

## Production Supabase

Read-only verification was performed against the connected Supabase project:

- Project ref: `pvhdsngxyoiqhqwujfjt`
- Project status: `ACTIVE_HEALTHY`
- PostgreSQL: 17.6.1.084
- Project API URL is configured and reachable through the connected Supabase integration.
- Production migration rows: **45**
- First recorded migration: `202609170001`
- Latest recorded production migration:
  `20260930013114` — `saas_workspace_provisioning`

The live production migration history therefore contains a workspace-provisioning migration version that was not located as a matching migration filename/name in the current `main` repository search.

This creates a real **CLASS D — SUPABASE / RELEASE REPRODUCIBILITY** gap:

LIVE PRODUCTION SCHEMA HISTORY
≠
PROVEN REPOSITORY MIGRATION HISTORY

Do NOT silently repair this by editing or applying SQL.

Before declaring an exact-release production deployment safe, the migration provenance must be reconciled and the governed forward-only migration rules must be followed.

## Current Supabase security evidence

The current Supabase Security Advisor reports:

- `auth_leaked_password_protection` — WARN

The remediation is external Auth configuration, not application-code evidence.

The current database also reports 9 legacy public tables with RLS disabled. A direct read-only privilege query independently verified that `anon`, `authenticated`, and `service_role` do not have SELECT privilege on those 9 tables.

Therefore:

- do NOT automatically enable RLS on those legacy tables;
- the advisor warning must not be treated as proof of Data API exposure;
- any future remediation requires an identified legitimate application access path and explicit policy design.

This is a security-hardening item, but it is not currently proven to block the QROS customer path.

## Deployment remains independently blocked

No QROS production container host or public QROS HTTPS endpoint was discovered through the connected GitHub/Supabase state.

Therefore the deployment-provider blocker remains:

**CLASS E — DEPLOYMENT PROVIDER**

The correct sequence is now:

1. reconcile/verify production migration provenance;
2. verify the exact-release schema gate;
3. obtain a real production container host;
4. deploy the exact verified release SHA;
5. verify HTTPS and `/healthz` / `/readyz`;
6. configure Auth redirect;
7. execute the real customer journey.

# 20. CURRENT FIRST BLOCKER

The first remaining blocker is:

ACTUAL PRODUCTION HOSTING / DEPLOYMENT ACCESS

At the time this roadmap was last verified, the connected environment had:

- GitHub access
- Supabase access

It does NOT currently have:

- VPS/container host
- Render deployment connection
- Railway deployment connection
- equivalent managed container hosting access

Therefore no deployment evidence may be manufactured.

---

# 21. EXACT DEPLOYMENT TARGET

When hosting access becomes available, deploy EXACTLY:

b584a10d7853f9d5d4297c5202ef130b19c3faa5

Do NOT deploy:

5d6eea14...

Do NOT use:

an old local branch

Do NOT use:

an unverified working tree

The deployment must be traceable to the frozen production SHA.

---

# 22. DEPLOYMENT SEQUENCE

STEP 1 — CONNECT HOSTING

Choose a real container host.

Examples:

- Render
- Railway
- VPS
- another managed Docker host

The provider must be capable of:

- building the existing Dockerfile
- running the container
- exposing port 8000
- providing public HTTPS
- storing server-side environment secrets

---

# 23. STEP 2 — DEPLOY CURRENT PRODUCTION SHA

Deploy:

b584a10d7853f9d5d4297c5202ef130b19c3faa5

Do not modify application code merely to deploy it.

Use the existing Dockerfile.

---

# 24. STEP 3 — CONFIGURE SERVER SECRETS

Configure securely through the hosting provider:

SUPABASE_URL

SUPABASE_SERVICE_ROLE_KEY

SUPABASE_PUBLISHABLE_KEY

BILLING_WEBHOOK_SECRET

Never put:

SUPABASE_SERVICE_ROLE_KEY

into browser code.

Never commit production secrets into Git.

---

# 25. STEP 4 — VERIFY CONTAINER

Verify:

- image builds
- container starts
- application imports
- Uvicorn starts
- port 8000 is reachable internally
- /healthz succeeds
- container remains running

Evidence should identify the deployed SHA.

---

# 26. STEP 5 — OBTAIN PUBLIC HTTPS

Required:

https://<REAL-QROS-HOST>

Example only:

https://qros.example.com

Do not record an invented URL.

The URL must be the actual provider-issued or configured production endpoint.

---

# 27. STEP 6 — CONFIGURE SUPABASE AUTH

Once the REAL HTTPS URL exists:

Configure Supabase Auth:

Site URL:

https://<REAL-QROS-HOST>

Redirect URL:

https://<REAL-QROS-HOST>/onboarding

Verify the configuration against the actual deployed URL.

---

# 28. STEP 7 — REAL CUSTOMER SMOKE TEST

Use a legitimate test/customer identity.

Do NOT manufacture evidence using:

- service_role
- direct SQL Auth user insertion
- direct workspace insertion
- bypassed JWT
- manually fabricated database rows

Test:

1. Open:
   https://<REAL-QROS-HOST>/onboarding

2. Signup.

3. Complete email confirmation if required.

4. Sign in.

5. Obtain authenticated session.

6. Call:

POST /v1/workspaces

7. Verify:

workspace exists

8. Verify:

owner membership exists

9. Verify:

FREE entitlement exists

10. Call:

GET /v1/me

11. Verify returned customer/account state.

---

# 29. CUSTOMER JOURNEY SUCCESS CONDITION

The milestone is COMPLETE only when this real path succeeds:

NEW CUSTOMER
→ SIGNUP
→ AUTHENTICATION
→ SESSION
→ WORKSPACE
→ OWNER
→ FREE ENTITLEMENT
→ /v1/me

No operator database intervention.

No service-role impersonation.

No manually inserted customer state.

---

# 30. AFTER CUSTOMER ONBOARDING

Once onboarding succeeds, the next real product test is:

CUSTOMER
→ DATASET
→ DATASET VERSION
→ RESEARCH RUN
→ QUEUE
→ WORKER
→ LEASE
→ SCIENTIFIC EXECUTION
→ RESULT
→ EVIDENCE
→ REPORT

This should be tested through the supported customer boundary.

---

# 31. PRODUCTION OPERABILITY

Already implemented:

- structured API errors
- correlation/request IDs
- run status
- lease state
- attempt count
- provenance
- result manifest hash
- tenant-safe logs

Partially implemented:

- automatic retry/backoff
- richer worker status
- customer-facing operational UI

These are NOT the current deployment blocker.

---

# 32. PR #416 STATUS

PR:

#416

Title:

fix(ci): use sudo for production backup package install

HEAD:

d7100126eb5cc6dc257591e0d1f1982744f79bfb

Base:

5d6eea14c8cd8194252479a6ff8a5d97db97fea8

Status:

OPEN

Merged:

NO

Important:

PR #416 is NOT part of the b584a10 production baseline.

Do not merge it merely because deployment is blocked.

Only address it if there is a concrete production backup requirement.

---


# FROZEN WORK RULE

A frozen or closed item may be reopened only when ALL of the following are true:

1. New evidence contradicts the recorded state.
2. The contradiction is reproducible or independently verifiable.
3. The exact affected production SHA or artifact is identified.
4. Reopening the item is necessary for the current customer-ready milestone or a concrete production requirement.

If these conditions are not met:

- do not reopen the item,
- do not rerun it merely for another green result,
- do not alter its frozen evidence,
- do not create replacement evidence just to improve presentation.

A new question, curiosity, code preference, or desire for additional confidence is not by itself sufficient reason to reopen frozen work.

# 33. DO NOT REOPEN

The following are CLOSED and should not be reopened without new evidence:

- Phase 5.2 permutation evidence
- C++ canonical backend migration
- Quant Engine architecture
- worker architecture
- queue architecture
- lease fencing
- workspace provisioning
- owner membership
- FREE entitlement
- tenant isolation
- provenance architecture
- PR #412 forensic/security work

---

# 34. CURRENT PROJECT COMPLETION ESTIMATE

There is no mathematically defined total roadmap, so a universal percentage would be misleading.

For the currently defined customer-ready milestone:

Estimated engineering implementation:

~90–95%

Estimated production-proven customer product:

~80–85%

The gap is primarily real external deployment and real customer verification.

The project is NOT 50–60% complete.

The core engineering system is substantially built.

The remaining gap is concentrated in the final production/customer boundary.

---

# 35. VISUAL STATE

ENGINEERING CORE

██████████████████████████████████████████████████ ~95%


CUSTOMER PRODUCT IMPLEMENTATION

████████████████████████████████████████████████░░ ~90–92%


PRODUCTION PROOF

████████████████████████████████████████░░░░░░░░░░ ~80–85%


REAL CUSTOMER

████████████████████████████████████░░░░░░░░░░░░░░ BLOCKED

---

# 36. SINGLE NEXT ACTION

DO NOT WRITE MORE QROS CODE.

DO NOT RERUN PHASE 5.2.

DO NOT MODIFY THE SCIENTIFIC CORE.

DO NOT MERGE PR #416.

DO NOT FABRICATE CUSTOMER EVIDENCE.

NEXT ACTION:

RECONCILE / VERIFY PRODUCTION MIGRATION PROVENANCE AGAINST THE EXACT RELEASE.

Then:

CONNECT A REAL PRODUCTION CONTAINER HOST.

Then:

HOST
→ DEPLOY b584a10
→ HTTPS
→ /healthz
→ SUPABASE AUTH REDIRECT
→ /onboarding
→ REAL SIGNUP
→ REAL SESSION
→ WORKSPACE
→ OWNER + FREE
→ /v1/me

---

# 37. FINAL CURRENT STATE

PRODUCTION SHA:
b584a10d7853f9d5d4297c5202ef130b19c3faa5

PHASE 5.2:
FROZEN

PRODUCTION CI:
PASS

SCIENTIFIC CORE:
IMPLEMENTED

CUSTOMER BACKEND:
SUBSTANTIALLY IMPLEMENTED

SELF-SERVICE ONBOARDING:
IMPLEMENTED

BILLING FOUNDATION:
IMPLEMENTED

CHECKOUT:
NOT IMPLEMENTED

PUBLIC PRODUCTION HOST:
NOT AVAILABLE

DOCKER BUILD:
NOT EXECUTED IN CONNECTED ENVIRONMENT

DEPLOYMENT:
NOT EXECUTED

PUBLIC HTTPS:
NONE

AUTH REDIRECT:
NOT VERIFIED

REAL CUSTOMER SIGNUP:
NOT EXECUTED

REAL CUSTOMER JOURNEY:
BLOCKED

CODE CHANGES REQUIRED NOW:
NONE

FIRST REMAINING BLOCKER:
REAL PRODUCTION HOSTING ACCESS

---


# CHANGE AUTHORIZATION MATRIX

The AI agent may autonomously:

- inspect the repository and Git history,
- run local tests and audits,
- inspect GitHub state and CI evidence,
- create isolated feature branches,
- modify repository files required by the roadmap,
- commit changes,
- push feature branches,
- create pull requests when the workflow permits.

Human authorization is required for:

- merging a pull request unless explicitly authorized,
- force-pushing or destructive Git operations,
- entering or exposing production secrets,
- changing external account ownership/security settings when unavailable to the agent,
- spending money or activating paid infrastructure,
- production actions that require credentials or account approval unavailable to the agent,
- real customer actions that the agent cannot legitimately perform.

The agent must never treat the existence of a tool connection as proof that an external production action has succeeded.

# 38. OPERATING RULE FOR FUTURE WORK

Every future QROS session should begin by verifying:

1. current main SHA
2. current production SHA
3. Git status
4. whether production SHA changed
5. whether Phase 5.2 is still frozen
6. open PRs that could affect production
7. deployment status
8. public HTTPS availability
9. customer journey status

Never assume previous state.

Never claim completion without exact evidence.

Prefer:

FACT
→ EVIDENCE
→ GAP
→ SINGLE NEXT ACTION

over:

ASSUMPTION
→ SPECULATION
→ MORE CODE

---


# ROADMAP SELF-VALIDATION

The roadmap contains a dated snapshot, but the live repository and connected systems are authoritative for current state.

At the beginning of each execution session, verify at minimum:

1. `origin/main` exact SHA
2. current HEAD and branch
3. clean/dirty working tree
4. ahead/behind relationship
5. open PRs affecting the production baseline
6. relevant production CI status
7. frozen Phase 5.2 artifact hashes
8. deployment availability/status
9. public HTTPS availability
10. Supabase Auth configuration relevant to the deployed URL
11. real customer journey status
12. whether any external blocker has changed.

If this document conflicts with live state:

- do NOT silently rewrite the roadmap first;
- record the documented state;
- record the actual state;
- identify the contradiction;
- determine whether the contradiction is stale documentation or an actual project regression;
- resolve the underlying state before updating the roadmap.

The latest verified live state always takes precedence over an older timestamp in this document.

# 39. DEFINITION OF "CUSTOMER-READY"

QROS may be called customer-ready for the current milestone only after:

[ ] Production SHA is verified
[ ] Production CI is green
[ ] Phase 5.2 remains frozen
[ ] Real Docker deployment exists
[ ] Public HTTPS exists
[ ] /healthz passes
[ ] Supabase Auth Site URL configured
[ ] /onboarding redirect configured
[ ] New customer signup succeeds
[ ] Authentication succeeds
[ ] Real session exists
[ ] Workspace creation succeeds
[ ] Owner membership exists
[ ] FREE entitlement exists
[ ] /v1/me succeeds
[ ] No operator database intervention was required
[ ] Evidence is recorded against the real production deployment

---

# 40. FINAL PRINCIPLE

QROS is now at the boundary between:

ENGINEERING COMPLETION

and

REAL CUSTOMER DEPLOYMENT.

The remaining work should therefore become increasingly operational and customer-facing, not another cycle of speculative backend engineering.

The frozen production baseline is:

b584a10d7853f9d5d4297c5202ef130b19c3faa5

Protect it.

Deploy it.

Expose it through HTTPS.

Run the real customer journey.

Then move from engineering validation to actual customer usage and monetization.
