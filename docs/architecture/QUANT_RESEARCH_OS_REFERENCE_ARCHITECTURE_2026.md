# Quant Research Operating System — Reference Architecture 2026

**Status:** Proposed architecture standard 1.0  
**Date:** 2026-09-17

## 1. Architectural thesis

ResearchOS is a **research operating system**, not a generic backtester. The architecture is organized around durable research objects and evidence lineage rather than around a collection of indicators.

```text
                         ┌──────────────────────────────┐
                         │        RESEARCHOS SaaS        │
                         │ Claim / Evidence / Knowledge │
                         └──────────────┬───────────────┘
                                        │
              ┌─────────────────────────┼────────────────────────┐
              │                         │                        │
              ▼                         ▼                        ▼
        Research API              Evidence Graph           SaaS Control
              │                         │                        │
              ▼                         ▼                        ▼
       Research Orchestrator      Claims / Runs / Results   Auth / RLS / Audit
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
   Python    C++    Data Engine
   Research  Kernels  Integrity
      │       │        │
      └───────┼────────┘
              ▼
     Probability & Edge Engine
              │
              ▼
   Validation / OOS / Replication
              │
              ▼
        Knowledge Status
```

## 2. Trust domains

### Domain A — Research Core

No live-market side effects. Deterministic, provenance-first, evidence-producing.

### Domain B — SaaS Control Plane

Identity, tenant boundaries, authorization, billing, jobs, audit, API access.

### Domain C — Future Execution Plane

Optional and isolated. Consumes explicitly approved research artifacts. It is not allowed to mutate research truth.

## 3. Python/C++ division of responsibility

### Python

Use for:

- research orchestration;
- exploratory analysis;
- statistical/econometric models;
- probability analysis;
- feature research;
- ML experimentation;
- notebooks;
- report generation;
- high-level APIs.

### C++

Use when profiling justifies it for:

- high-throughput numerical kernels;
- market-data transformations;
- vectorized/parallel backtest kernels;
- deterministic simulation;
- latency-sensitive future execution components;
- memory-sensitive operations.

The Python/C++ boundary must be explicit and versioned. Binding code is an adapter, not a second source of truth.

## 4. Data architecture

```text
Raw Source
   ↓
Ingestion Adapter
   ↓
Raw Immutable Artifact
   ↓
Schema / Timestamp / Duplicate / Gap / Missingness Checks
   ↓
Data Integrity Envelope
   ↓
Canonical Dataset Version
   ↓
Parquet / Analytical Store
   ↓
DuckDB / Research Query
   ↓
Experiment Input
```

PostgreSQL/Supabase is the system of record for application metadata and evidence relationships. Parquet is the preferred durable analytical file format. DuckDB is the preferred local/embedded analytical engine for columnar research workloads. A time-series extension/store is introduced only where workload evidence justifies it.

## 5. Artifact architecture

Every material research artifact must have:

```text
artifact_id
artifact_type
content_hash
schema_version
producer_version
created_at
source_dataset_version
access_policy
```

Examples:

- dataset;
- feature table;
- label table;
- model;
- simulation output;
- probability analysis;
- validation report;
- replication report;
- benchmark.

## 6. Probability & Edge Engine

The engine is a graph of specialized analysis services, not one monolithic "edge score".

```text
Observations
   ↓
Distribution
   ↓
Probability ──────┐
   ↓              │
Payoff             │
   ↓              │
Risk               │
   ↓              │
Time Series        │
   ↓              │
Dependence         │
   ↓              │
Tail               │
   ↓              │
Inference          │
   ↓              │
Selection Bias     │
   ↓              │
Calibration        │
   ↓              │
OOS                │
   ↓              │
Replication ◄──────┘
   ↓
Economic Validation
```

Each service emits an inspectable AnalysisResult. Downstream services consume declared contracts rather than reaching into undocumented internal state.

## 7. Research execution lifecycle

```text
CREATE CLAIM
  ↓
LOCK PLAN
  ↓
FREEZE DATA/FEATURE/LABEL VERSIONS
  ↓
RUN BASELINE
  ↓
RUN PRE-DECLARED ANALYSES
  ↓
RECORD ALL RESULTS
  ↓
VALIDATE STATISTICAL INTEGRITY
  ↓
ADJUST FOR SEARCH / SELECTION
  ↓
RUN OOS
  ↓
REPLICATE
  ↓
ECONOMIC COST TEST
  ↓
PROMOTE / CONTRADICT / REMAIN INCONCLUSIVE / REJECT
```

## 8. Failure isolation

A failed component must fail closed where evidence integrity is affected.

Examples:

- missing data provenance → analysis blocked;
- invalid timestamps → temporal gate blocked;
- non-convergent GARCH → model result invalid, not silently replaced;
- missing OOS split → edge promotion blocked;
- missing cost model → economic validation incomplete;
- artifact hash mismatch → artifact rejected;
- unauthorized tenant access → request denied and audited.

## 9. Performance architecture

Use a benchmark-driven rule:

`Measure → identify hotspot → define numerical contract → optimize → benchmark → regression-test`

Do not optimize by intuition alone. Do not trade numerical correctness for speed without an explicit approximation contract.

## 10. Future execution architecture

Execution is a separate service boundary:

```text
Validated Research Artifact
          ↓
Execution Eligibility Gate
          ↓
Risk Engine
          ↓
Order Manager
          ↓
Exchange Adapter
          ↓
Venue
```

The execution plane must never write back an unverified "successful trade" as research evidence without an explicit observation ingestion path.

## 11. SaaS scale path

### Stage 1

Single deployment, PostgreSQL/Supabase, object storage, worker jobs, Python/C++ research engines.

### Stage 2

Tenant-isolated workloads, background jobs, caching, artifact lifecycle, usage metering.

### Stage 3

Distributed research workers, queue/event infrastructure, dedicated compute pools, workload quotas.

### Stage 4

Optional execution plane, market-data streaming, low-latency components.

Scaling must follow measured bottlenecks, not technology fashion.
