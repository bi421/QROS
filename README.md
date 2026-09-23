# QROS

**Quant Research Operating System — Evidence-Governed Research Infrastructure**

QROS is a research-first quantitative research system being evolved into a **multi-tenant SaaS platform** for reproducible, auditable, evidence-backed research.

> **Core rule:** a formula is not a claim, a model fit is not a validated edge, and statistical significance is not automatically economic significance.

QROS is **research infrastructure, not a broker/execution system**. It does not place trades or send orders.

## Research Pipeline

```
REAL DATA
   ↓
MARKET MEMORY
   ↓
RESEARCH CLAIM
   ↓
RESEARCH PLAN
   ↓
EXPERIMENT
   ↓
RUN
   ↓
RESULT
   ↓
VALIDATION
   ↓
FINDING
   ↓
REPLICATION / CONTRADICTION
```

Every governed conclusion is intended to remain traceable to its source data, immutable plan, execution, evidence, validation state, and research artifacts.

## What Is Implemented

### Research governance

- Research Claim as the durable unit of research intent
- Immutable/content-hashed Research Plan with one-time lock
- Governed planner v1
- Immutable governed `AnalysisResult`
- Probability / edge registry
- Evidence-backed edge eligibility gates
- OOS and replication evidence contracts
- Deterministic evidence hashing

### Evidence and lineage

- Immutable `EvidenceEnvelope`
- SHA-256 content and lineage hashes
- Typed artifacts: Dataset, Feature, Experiment, Run, Result, Validation, Finding, Model
- Lineage relations including `feeds`, `executes`, `produces`, `validates`, `derives`, `trains`, `contradicts`, and `replicates`
- Claim → Plan → Evidence graph projection
- Deterministic Experiment/Run/Result/Validation/Finding traversal
- Broken-edge and orphan-evidence integrity checks
- Historical evidence is referenced rather than silently rewritten

### SaaS execution foundation

- Explicit authenticated `TenantContext`
- Tenant-scoped dataset and research-job operations
- Content-addressed dataset storage paths
- Immutable dataset versions
- Atomic research-run idempotency
- Durable job state transitions
- Worker lease and heartbeat semantics
- Bounded retry controls
- Provenance-linked research results
- Tenant-scoped Supabase persistence adapters
- RLS and tenant-boundary database hardening migrations
- Workspace-scoped rate limiting
- Billing webhook signature verification and event deduplication
- Versioned `/v1` HTTP API
- Fail-closed authentication boundary
- Structured API error metadata with request correlation IDs

## Research Integrity Rules

1. **Evidence before intelligence.** Predictive conclusions require validated evidence.
2. **Research before execution.** QROS does not place live orders.
3. **Immutable provenance.** Data, plans, results, and artifacts retain stable identifiers and hashes.
4. **Deterministic computation.** Versioned inputs and configuration should produce reproducible outputs.
5. **Explicit uncertainty.** Probability must have a defined meaning and provenance.
6. **Statistical ≠ economic.** Costs and execution assumptions remain explicit.
7. **OOS discipline.** In-sample results are not treated as out-of-sample validation.
8. **Replication matters.** A single experiment does not automatically become durable knowledge.
9. **Tenant isolation is correctness.** Cross-workspace access is a data-integrity defect, not merely a UI problem.
10. **No silent repair.** Missing or ambiguous evidence must not be fabricated or silently repaired.

## SaaS Architecture

```
Client
  ↓
/v1 API
  ↓
Authentication
  ↓
Tenant / Workspace Context
  ↓
Research Planner
  ↓
Durable Research Job
  ↓
Governed Execution
  ↓
Evidence / Lineage / Validation
  ↓
Provenance + Content-Addressed Artifacts
  ↓
Auditable Research Result
```

The production target includes tenant isolation, authenticated access, authorization, durable jobs, object storage, dataset versioning, auditability, observability, billing controls, backup/recovery, and reproducible releases.

Not every production capability is complete. The repository roadmap is deliberately conservative: **implemented code, verified integration, and production readiness are separate states.**

## Current Development Status

The project is in the **research-core → SaaS hardening** stage.

### Remaining production gates

1. [ ] Tenant isolation and real-persistence integration
2. [ ] Migration/version compatibility
3. [ ] Public API contract coverage
4. [ ] Authorization policy matrix
5. [ ] Pagination/filter/sort contracts
6. [ ] Tenant-scoped object storage, retention, and dataset registry
7. [x] Security/threat-model and red-team review
8. [ ] Observability, billing, UI, and operational controls
9. [ ] Exact-release CI, backup/restore, and final production verification

Only gates directly verified by implementation/tests are checked. No release-readiness claim is made from unobserved CI or local execution.

See `todo/saas.md` for the canonical execution checklist.

## Repository Structure

```
QROS/
├── researchos/
│   ├── claims/              # Claims and evidence graph
│   ├── evidence/            # Evidence envelopes and lineage
│   ├── probability/         # Probability contracts
│   ├── research_core/       # Governed research contracts
│   └── saas/                # API, jobs, datasets, billing, persistence
├── examples/
│   └── research_lab/        # Standalone research example
├── supabase/
│   └── migrations/          # Database/RLS/tenant-boundary migrations
├── docs/
│   ├── architecture/
│   ├── governance/
│   ├── product/
│   └── saas/
├── todo/
│   └── saas.md              # Canonical SaaS roadmap
├── scripts/
└── README.md
```

## Installation

```bash
pip install -e .
```

## Verification

Run targeted tests during development:

```bash
pytest researchos/tests/ -v
pytest researchos/saas/tests/ -v
```

For release decisions, use the repository's complete CI and health-evidence gates. A partial local test run is not evidence that the whole repository is production-ready.

Health evidence can be generated with:

```bash
python scripts/final_health_check.py
```

A health claim is considered **verified only when the resulting artifact or the corresponding CI evidence is observed for the exact commit under review**.

## Documentation

Key contracts and architecture:

- `docs/governance/`
- `docs/architecture/`
- `docs/product/`
- `docs/saas/API_CONTRACT_V1.md`
- `docs/saas/DATABASE_SCHEMA.md`
- `todo/saas.md`

## Non-Goals

QROS does not:

- Execute broker orders
- Claim that backtest profitability proves a durable edge
- Hide assumptions behind unexplained scores
- Manufacture evidence when data is missing
- Treat statistical significance as economic significance
- Declare production readiness without integration and operational verification

## License

QROS is research infrastructure. Research outputs are for research purposes and do not constitute financial advice or instructions to execute trades.
