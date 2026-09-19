# QROS

**Quant Research Operating System — Evidence-Governed Research Infrastructure**

QROS is a research-first quantitative research system being developed toward a **multi-tenant SaaS platform** for reproducible, auditable, evidence-backed research.

> **Core rule:** a formula is not a claim, a model fit is not a validated edge, and statistical significance is not automatically economic significance.

QROS is **research infrastructure, not a broker/execution system**. It does not place trades or send orders.

## Research Pipeline

```
REAL DATA
    ↓
MARKET MEMORY
    ↓
RESEARCH PLAN
    ↓
EXPERIMENT
    ↓
EVIDENCE
    ↓
VALIDATION
    ↓
CALIBRATED PROBABILITY
    ↓
AUDITABLE RESULT
```

The system is designed so that conclusions remain traceable to the data, plan, experiments, validation state, costs, and artifacts that produced them.

## Current Research Governance

The current implementation includes the following research-grade foundations:

### Evidence integrity

- Immutable evidence envelopes
- Deterministic canonical JSON representation
- SHA-256 artifact hashing
- Versioned hash scheme
- Typed research artifacts and lineage relations
- Artifact integrity verification

### Claim → Plan → Evidence

- Durable research claims
- Immutable/content-hashed research plans
- Plan locking before evidence attachment
- Claim-to-evidence graph projection
- Rejection of missing evidence
- Deterministic evidence tracing
- Graph verification and regression tests

### Statistical governance

- Probability analysis contracts
- Uncertainty intervals and effective sample size fields
- Calibration state
- Multiple-testing context
- Bonferroni correction
- Benjamini–Hochberg false-discovery-rate correction
- Deterministic adjusted p-values and rejection decisions

### Validation governance

- Explicit OOS state machine
- Explicit replication state machine
- `NOT_APPLICABLE → PENDING → PASS/FAIL` governance
- Terminal validation states cannot be silently reversed

### Economic realism

Research results can carry an explicit cost model covering:

- Commission
- Spread
- Slippage
- Market impact
- Fixed per-trade costs

Gross returns can therefore be evaluated against explicit transaction costs instead of treating statistical results as automatically tradable.

### Reproducible artifacts

- Dataset SHA-256 binding
- Research-plan SHA-256 binding
- Deterministic artifact manifests
- Manifest schema versioning
- Duplicate artifact detection
- Manifest SHA-256 verification

### Research execution / SaaS foundations

- Durable research-run/job records
- Idempotent mutation handling
- Bounded retry and terminal-state governance
- Worker heartbeat/lease concepts
- Provenance-linked results
- Server-side result persistence foundations
- Tenant-aware SaaS architecture under active hardening

## SaaS Direction

QROS is being evolved from a research codebase into a **research product**, with the following target architecture:

```
User / Client
     ↓
Versioned API
     ↓
Authentication + Authorization
     ↓
Workspace / Tenant Boundary
     ↓
Research Planner
     ↓
Governed Research Execution
     ↓
Evidence / Lineage / Validation
     ↓
Content-Addressed Artifacts
     ↓
Auditable Research Result
```

The SaaS design is intended to provide:

- Workspace/tenant isolation
- Versioned API contracts
- Authenticated research access
- Authorization by workspace and resource
- Idempotent research-run requests
- Durable asynchronous jobs
- Provenance-linked outputs
- Tenant-scoped artifact storage
- Dataset versioning
- Auditability
- Observability
- Backup and recovery
- Reproducible releases

These SaaS capabilities are **not all complete yet**. QROS is being implemented and verified incrementally; documentation does not treat planned functionality as production-ready functionality.

## Project Status

QROS is currently in an **active research-core → SaaS hardening phase**.

### Implemented foundations

- Research claim model
- Research-plan hashing and locking
- Evidence envelope governance
- Claim/evidence graph foundation
- Research planner v1
- Governed `AnalysisResult`
- Probability/edge registry foundations
- Calibration and uncertainty contracts
- Multiple-testing correction
- OOS/replication state transitions
- Economic cost/slippage model
- Deterministic artifact manifests
- Durable job/execution governance
- Provenance-linked result records

### Still under implementation / verification

- Complete Experiment → Run → Result → Validation → Finding graph traversal
- Contradiction and replication graph edges
- Graph orphan/integrity detection
- Full tenant-isolation integration testing
- Complete versioned public API
- Authentication and authorization matrix
- Request limits and abuse controls
- Structured API errors
- Tenant-scoped object storage
- Dataset version registry
- Security/audit hardening
- Production UI
- Billing/subscription
- Full observability
- Backup/restore and disaster recovery
- Final integration and release gates

**Important:** a feature is not considered production-ready merely because its contract or unit tests exist. Integration, tenant isolation, exact-release CI, operational behavior, and reproducibility must also be verified.

## Design Principles

1. **Evidence before intelligence**  
   Predictive or strategic conclusions must be grounded in validated historical evidence.

2. **Research before execution**  
   QROS produces research and evidence. It is not a broker or order-execution engine.

3. **Immutable provenance**  
   Data, plans, artifacts, and results must be traceable through stable hashes and manifests.

4. **Determinism**  
   The same versioned inputs and configuration should produce reproducible research outputs.

5. **Explicit uncertainty**  
   Probability is a governed research object, not an unexplained confidence number.

6. **Statistical ≠ economic**  
   Statistical evidence must be evaluated together with costs, slippage, sample size, and validation status.

7. **Out-of-sample discipline**  
   In-sample performance is not treated as equivalent to OOS validation.

8. **Replication matters**  
   A single experiment is not automatically a durable research finding.

9. **Tenant isolation is a correctness property**  
   In a SaaS deployment, workspace boundaries are part of the research integrity model.

10. **No silent repair**  
    Missing, corrupted, or ambiguous source data must not be silently interpolated, fabricated, or repaired without an explicit governed rule.

## Repository Structure

```
QROS/
├── researchos/
│   ├── claims/              # Research claims and evidence graph
│   ├── evidence/            # Evidence envelopes and lineage
│   ├── research_core/       # Core research contracts and governance
│   ├── probability/         # Probability-analysis contracts
│   ├── saas/                # SaaS execution, provenance, persistence
│   └── tests/               # Core regression/integration tests
├── docs/
│   └── saas/                # SaaS API and database design
├── todo/
│   └── saas.md              # Canonical SaaS implementation roadmap
├── scripts/                 # Reproducible operational tooling
├── examples/                # Research examples
└── README.md
```

## Installation

```bash
pip install -e .
```

## Running Tests

Run the relevant research-core tests during development:

```bash
pytest researchos/tests/ -v
```

For a full repository verification, use the repository's CI workflow and release/health gates. Do not treat a local partial test run as proof that the complete system is healthy.

## Documentation

The canonical SaaS roadmap is:

```
todo/saas.md
```

SaaS architecture and contracts are documented under:

```
docs/saas/
```

Research governance is distributed across the relevant modules under:

```
researchos/
```

## Repository Hygiene

- Canonical runtime code belongs under `researchos/`.
- Reproducible operational entry points belong under `scripts/`.
- Tests belong under the relevant package/test hierarchy.
- Historical reports belong under `docs/archive/` where applicable.
- One-off repair, exploratory, scratch, and manual-test scripts must not be added to the repository root.
- Credentials, API keys, tokens, and other secrets must never be committed.
- Changes to research contracts should include deterministic regression coverage.
- Documentation must distinguish implemented, verified, and planned functionality.

## Non-Goals

QROS is not intended to:

- Execute broker orders
- Provide autonomous trading decisions
- Hide model assumptions behind opaque scores
- Manufacture evidence when data is missing
- Treat backtest profitability as proof of a durable edge
- Claim production readiness without integration and operational verification

## License

QROS is research infrastructure. Research outputs are for research purposes and do not constitute financial advice or an instruction to execute trades.
