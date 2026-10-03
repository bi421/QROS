# ResearchOS — Canonical Architecture Specification

**File:** `architecture.md`
**Version:** 3.0
**Status:** Canonical Architecture Reference
**Date:** 2026-08-17
**Primary Research Asset:** XAUUSD
**Runtime:** Python 3.14.x
**Quantitative Backend:** Python + optional native C++ backend
**Execution Model:** Research-only; no broker execution

---

# 1. Purpose

ResearchOS is a deterministic, reproducible, research-first quantitative market research and intelligence platform.

The system is designed to study historical market behavior and determine whether measurable and statistically defensible relationships exist between:

* XAUUSD price behavior;
* market state;
* volatility;
* historical market patterns;
* DXY;
* cross-asset relationships;
* macroeconomic conditions;
* economic events;
* positioning;
* geopolitical context;
* other validated market variables.

The primary research question is:

> Under what historical conditions did XAUUSD move UP or DOWN, and how much predictive information was contained in the information available at that time?

ResearchOS must prioritize:

1. factual data;
2. deterministic computation;
3. explicit contracts;
4. provenance;
5. reproducibility;
6. empirical testing;
7. statistical validation;
8. calibrated uncertainty.

The system must never convert an unsupported hypothesis into a factual conclusion.

---

# 2. Architectural Philosophy

ResearchOS is not designed as a conventional trading bot.

It is designed as a layered research system.

The fundamental progression is:

```text
DATA
  ↓
VALIDATION
  ↓
STRUCTURED DATA
  ↓
MARKET MEMORY
  ↓
QUANTITATIVE ANALYSIS
  ↓
MARKET CONTEXT
  ↓
RESEARCH
  ↓
EXPERIMENT
  ↓
EVALUATION
  ↓
EVIDENCE
  ↓
INTELLIGENCE
  ↓
FUTURE LEARNING
```

The system must not bypass the research and validation layers merely to produce a prediction.

---

# 3. Core Architectural Principles

## 3.1 Evidence Before Prediction

A numerical output is not automatically evidence.

ResearchOS must distinguish between:

```text
Observed Data
Derived Measurement
Statistical Relationship
Hypothesis
Experiment Result
Validated Evidence
Interpretation
Prediction
```

These concepts must remain separate.

---

## 3.2 Determinism

ResearchOS must be deterministic by default.

Identical:

* input data;
* dataset identity;
* configuration;
* experiment definition;
* algorithm version;
* backend;
* parameters;
* random seed;

must produce equivalent research results.

Randomness must never be implicit.

---

## 3.3 Reproducibility

A research result must be reproducible.

The minimum reproducibility identity should include:

```text
Dataset Identity
Dataset Version
Experiment Definition
Configuration
Algorithm Version
Backend
Parameters
Random Seed
```

Runtime timestamps may be recorded for provenance but must not arbitrarily alter scientific result identity.

---

## 3.4 Provenance

Important objects must retain provenance.

ResearchOS must be able to answer:

```text
Where did this data come from?

When was it available?

What transformation was applied?

Which experiment used it?

Which algorithm calculated it?

Which backend produced it?

How was it validated?
```

---

## 3.5 Conservative Failure

ResearchOS must fail conservatively.

Examples:

```text
REAL DATA MISSING
    ↓
BLOCKED

PROVENANCE INVALID
    ↓
INVALID

DATA LEAKAGE DETECTED
    ↓
INVALID

SAMPLE TOO SMALL
    ↓
INSUFFICIENT_EVIDENCE

RESULT NOT CALIBRATED
    ↓
DO NOT PRESENT AS TRUSTWORTHY PROBABILITY
```

A blocked result is preferable to a false result.

---

# 4. Current Repository Architecture

The repository currently contains the following major top-level areas:

```text
ResearchOS/
│
├── cpp_quant_engine/
├── data/
├── docs/
├── macro_intelligence/
├── monitoring/
├── researchos/
├── scripts/
├── tests/
├── tools/
│
├── .github/
├── .gitignore
├── architecture.md
├── CONTRIBUTING.md
├── pyproject.toml
├── README.md
└── run_demo.py
```

As of the `chore: remove build artifacts and AI dumps from tracking`
cleanup (2026-08-18), the transient `ai_audit.ps1` / `AI_*.txt` /
`AI_CONTEXT.md` dump files previously listed here were removed from
version control and are now `.gitignore`d. They are regenerable
local artifacts, not part of the canonical architecture.

The repository also contains the C++ quantitative engine integration under:

```text
cpp_quant_engine/
```

with its Python binding/package surface and native compiled backend.

The architecture document must distinguish repository-level infrastructure from Python package-level architecture.

---

# 5. Current Python Architecture

The verified ResearchOS Python architecture contains the following major domains:

```text
researchos/
│
├── core/
├── objects/
├── repository/
├── data_engine/
├── market_memory/
├── memory/
├── decision_engine/
├── experiments/
├── quant_engine/
├── intelligence/
├── orchestration/
├── pipeline_repository/
├── evaluation/
└── validation/
```

Additional research and integration modules may exist as specialized or transitional components.

These packages are not interchangeable.

Each package has a defined architectural responsibility.

---

# 6. Core Layer

## Location

```text
researchos/core/
```

## Responsibility

The Core layer provides foundational primitives used by the rest of ResearchOS.

It includes concepts such as:

* base objects;
* identity;
* deterministic hashing;
* lifecycle;
* versioning;
* timestamp handling;
* shared errors;
* foundational types.

The Core layer must remain independent of:

* XAUUSD-specific logic;
* broker execution;
* high-level prediction;
* external intelligence;
* future learning algorithms.

---

# 7. Objects Layer

## Location

```text
researchos/objects/
```

The Objects layer represents domain-level research objects.

Verified examples include objects related to:

* observations;
* evidence;
* hypotheses;
* scenarios;
* confidence;
* contradiction;
* knowledge;
* research;
* macro context;
* market memory.

The Objects layer defines domain semantics.

It should not become the location for computational algorithms that belong to the quantitative engine.

---

# 8. Repository Layer

## Location

```text
researchos/repository/
```

The Repository layer provides persistence-oriented abstractions.

Its responsibility is to store and retrieve domain objects while preserving:

* identity;
* determinism;
* provenance;
* auditability.

Persistence must not silently mutate historical research objects.

---

# 9. Data Engine

## Location

```text
researchos/data_engine/
```

The Data Engine is one of the foundational layers of ResearchOS.

Verified concepts include:

* `Candle`;
* `Trade`;
* `Dataset`;
* `Query`;
* `Repository`;
* `Validator`;
* hashing;
* timezone helpers;
* dataset statistics.

The Data Engine is responsible for structured market data representation and data-level operations.

---

## Data Engine Boundary

The Data Engine answers:

> What data exists, and what is its validated structure?

It must not answer:

> What should XAUUSD do next?

---

# 10. Market Memory

## Location

```text
researchos/market_memory/
```

Market Memory is the historical-pattern representation layer.

Verified components include concepts such as:

* market snapshots;
* historical scenarios;
* features;
* similarity;
* matching;
* outcome analysis;
* market events;
* repositories;
* reports.

The purpose of Market Memory is to preserve and retrieve historical market configurations and outcomes.

Conceptually:

```text
Historical Market State
        ↓
Feature Representation
        ↓
Historical Matching
        ↓
Comparable Situations
        ↓
Historical Outcomes
```

Market Memory is not itself the Learning Layer.

It provides historical evidence that a future learning system may consume.

---

# 11. Quant Engine

## Location

```text
researchos/quant_engine/
```

The Quant Engine is the quantitative computation boundary.

It contains the Python-side quantitative backend abstraction and the C++ integration.

The verified architecture includes:

```text
PythonQuantBackend
        │
        ├── reference computation
        │
        ▼
Quantitative Contract
        ▲
        │
CppQuantAdapter
        │
        ▼
Native C++ Quant Engine
```

---

# 12. Python Quant Backend

The Python backend serves as:

* reference implementation;
* correctness baseline;
* deterministic fallback;
* research development backend.

It is important because the C++ backend must be evaluated against a known reference implementation.

---

# 13. C++ Quant Engine

The repository contains a native C++ quantitative engine.

The verified integration path is:

```text
ResearchOS
    ↓
researchos.quant_engine.cpp_backend
    ↓
CppQuantAdapter
    ↓
native C++ module
```

The native module has been verified at:

```text
Cpp Quant Backend Version: 1.0.0
```

and the adapter reports:

```text
IS_CPP: True
ADAPTER_VERSION: 1.0.0
```

when the appropriate Python path is configured.

The native module is compiled for the active Python runtime and is loaded through the C++ backend integration.

---

# 14. C++ Quant Engine Responsibility

The C++ engine is responsible for quantitative computation.

Examples include:

* rolling statistics;
* descriptive statistics;
* correlations;
* regression;
* risk metrics;
* volatility;
* numerical calculations;
* simulation;
* future performance-sensitive calculations.

The C++ engine must not become a decision engine.

It must not contain hidden:

```text
BUY
SELL
BROKER ORDER
POSITION MANAGEMENT
```

logic.

The quantitative engine calculates.

Higher layers interpret.

---

# 15. Backend Routing

ResearchOS must preserve the ability to select between:

```text
Python Backend
      │
      │
      └──────────► C++ Backend
```

through an explicit backend boundary.

The backend identity must be recorded in research provenance.

Changing the backend must not silently change research semantics.

Backend equivalence must be tested.

---

# 16. Experiments Layer

## Location

```text
researchos/experiments/
```

Experiments represent controlled empirical research.

An experiment must define:

```text
Experiment Identity
Dataset
Dataset Identity
Hypothesis
Inputs
Parameters
Target
Method
Baseline
Evaluation Metrics
Configuration
Random Seed
```

An experiment result is not automatically a validated scientific conclusion.

---

# 17. Experiment Immutability

A completed experiment must preserve the configuration used to produce its result.

The recorded experiment configuration must not remain a live mutable reference to an external configuration object.

This is necessary for historical reproducibility.

---

# 18. Phase 5.1 — XAUUSD Predictive-Value Research

The repository contains a dedicated Phase 5.1 experiment area:

```text
researchos/experiments/phase51/
```

with its own tests.

The current architecture therefore recognizes Phase 5.1 as the empirical XAUUSD research surface.

The intended flow is:

```text
Real XAUUSD Historical Data
        ↓
Dataset Validation
        ↓
Experiment Definition
        ↓
Baseline
        ↓
Predictive-Value Measurement
        ↓
Evaluation
        ↓
Evidence
```

The existence of the experiment implementation does not imply that predictive value has been proven.

---

# 19. Intelligence Layer

## Location

```text
researchos/intelligence/
```

The Intelligence layer organizes and retrieves research evidence.

Its responsibility includes concepts such as:

* evidence graphs;
* deterministic retrieval;
* lineage-aware retrieval;
* evidence context;
* research knowledge access.

The verified architecture contains an `EvidenceGraph` and `LineageQueryEngine` research surface.

The Intelligence layer must operate on available evidence.

It must not manufacture evidence.

---

# 20. Evidence Graph

ResearchOS should conceptually preserve:

```text
Observation
    ↓
Hypothesis
    ↓
Evidence
    ↓
Experiment
    ↓
Result
    ↓
Validation
    ↓
Conclusion
```

The Evidence Graph provides the structural representation of these relationships.

This enables research questions such as:

> What evidence supports this conclusion?

and:

> Which dataset and experiment produced this evidence?

---

# 21. Lineage

ResearchOS has an explicit lineage-oriented architecture.

Lineage should connect:

```text
Dataset
    ↓
Version
    ↓
Transformation
    ↓
Feature
    ↓
Experiment
    ↓
Result
    ↓
Evidence
```

Lineage is part of the research integrity architecture.

---

# 22. Orchestration Layer

## Location

```text
researchos/orchestration/
```

The Orchestration layer coordinates research workflows.

It is responsible for sequencing operations across established contracts.

Conceptually:

```text
Load
 ↓
Validate
 ↓
Transform
 ↓
Compute
 ↓
Evaluate
 ↓
Record
```

Orchestration must not reimplement lower-level quantitative algorithms.

---

# 23. Pipeline Repository

## Location

```text
researchos/pipeline_repository/
```

The Pipeline Repository stores and retrieves pipeline-level research records.

Its purpose is to preserve reproducible pipeline definitions and results.

It must preserve:

* identity;
* version;
* configuration;
* provenance.

---

# 24. Evaluation Layer

## Location

```text
researchos/evaluation/
```

The Evaluation layer evaluates research outputs.

The verified architecture includes:

```text
ResearchEvaluator
EvaluationReport
EvaluationScore
```

and related validation/error contracts.

The Evaluation layer must remain separate from the model or hypothesis generation layer.

Its purpose is to answer:

> How well did this research method perform under the defined evaluation protocol?

---

# 25. Validation Layer

## Location

```text
researchos/validation/
```

The Validation layer validates domain objects and research structures.

Examples include validation of:

* observations;
* evidence;
* hypotheses;
* scenarios;
* research objects.

Validation must not silently modify invalid objects into valid ones unless the transformation is explicitly part of a defined contract.

---

# 26. Decision Engine

## Location

```text
researchos/decision_engine/
```

The Decision Engine exists as a domain-level decision/evidence component in the current codebase.

Its architectural role must remain constrained.

It may reason over validated evidence and defined decision contracts.

It must not become:

* broker execution;
* autonomous trading;
* an unvalidated prediction black box.

Any future probabilistic decision surface must remain downstream of validated research evidence.

---

# 27. Memory Layer

## Location

```text
researchos/memory/
```

The Memory layer represents broader historical/contextual memory functionality distinct from the lower-level `market_memory` subsystem.

The architecture must preserve the distinction between:

```text
market_memory
```

as market-specific historical representation and:

```text
memory
```

as broader memory infrastructure.

These should not be collapsed without an explicit architectural change.

---

# 28. Macro Intelligence

## Location

```text
macro_intelligence/
│
├── audit/
├── contracts/
├── econometrics/
├── exceptions.py      (module, not a package)
├── features/
├── interfaces/
├── knowledge/
├── provenance/
├── regime/
├── relationships/
├── revision/
├── revision_provenance/
├── statistics/
├── storage/
└── time/
```

The exact directory set may evolve, but these domains represent the current architectural direction.

---

# 30. Macro Contracts

The Macro Intelligence subsystem defines structured contracts for macro data and contextual objects.

Examples include:

* normalized series;
* evidence;
* macro events;
* contextual data.

The macro contract layer must preserve:

* timestamps;
* source information;
* deterministic identity;
* provenance.

---

# 31. Macro Feature Layer

The Macro Feature layer converts normalized macro information into structured analytical variables.

Its architecture includes:

```text
Feature Definitions
        ↓
Feature Registry
        ↓
Feature Pipeline
        ↓
Feature Vector
```

Macro features must remain historically time-valid.

Future information must not be inserted into historical feature vectors.

---

# 32. Macro Relationship Engine

The Macro Intelligence subsystem contains an explicit relationship architecture.

Verified relationship functionality includes concepts such as:

* correlation;
* rolling relationships;
* lag analysis;
* regime relationships;
* structural break detection;
* relationship models.

Conceptually:

```text
Series A
   │
   ├── Correlation
   ├── Rolling Relationship
   ├── Lag Analysis
   ├── Regime Relationship
   └── Structural Break Analysis
   │
   ▼
Relationship Evidence
```

This is directly relevant to the future XAUUSD ↔ DXY / cross-asset architecture.

---

# 33. Macro Econometrics

The Macro Intelligence subsystem also contains econometric functionality.

Examples include:

* stationarity;
* VIF;
* matrix operations;
* statistical tests.

These capabilities are research infrastructure.

They must not be interpreted as proof of causal relationships by themselves.

---

# 34. Macro Knowledge

The Macro Knowledge layer provides structured contextual knowledge derived from validated macro information.

It must preserve the distinction between:

```text
Macro Observation
      ↓
Statistical Result
      ↓
Relationship
      ↓
Knowledge
```

Knowledge must remain traceable to its evidence.

---

# 35. Macro Revision and Provenance

Macro data may be revised after initial publication.

Therefore the Macro Intelligence architecture must preserve:

```text
Original Observation
Revision
Revision Time
Effective Historical Value
Source
Provenance
```

Historical research must not silently replace what was historically known at time `t` with a later revised value unless the experiment explicitly specifies a revised-data methodology.

---

# 36. Time Architecture

Time is a first-class architectural concern.

ResearchOS must use explicit timezone-aware timestamps.

The historical information boundary must distinguish:

```text
Event Time
Publication Time
Availability Time
Observation Time
```

This is especially important for:

* macro events;
* news;
* economic releases;
* revisions;
* cross-asset data.

---

# 37. Market Context Architecture

The future Market Context layer should connect existing subsystems rather than create another parallel architecture.

The intended relationship is:

```text
XAUUSD Market Data
        │
        ▼
Data Engine
        │
        ▼
Market Memory
        │
        ├───────────────┐
        │               │
        ▼               ▼
Quant Engine      Macro Intelligence
        │               │
        │               ├── Macro
        │               ├── Relationships
        │               ├── Econometrics
        │               └── Events
        │
        └───────────────┬───────────────
                        ▼
                 Research Layer
```

This is preferable to creating a new duplicate `context/` hierarchy.

---

# 38. DXY Integration

DXY should become the first major external relationship for XAUUSD research.

The intended architecture is:

```text
XAUUSD
   ↕
DXY
```

followed by:

```text
XAUUSD
   ↕
Rates / Yields
```

and later:

```text
XAUUSD
   ↕
EURUSD
   ↕
Other FX
```

The Relationship Engine should own relationship measurement.

The XAUUSD module should consume the relationship results rather than reimplement relationship mathematics.

---

# 39. Cross-Asset Relationship Architecture

Cross-asset relationships should support:

* correlation;
* rolling correlation;
* lag analysis;
* reaction delay;
* regime-conditioned relationship;
* structural breaks;
* stability;
* statistical significance.

A relationship record should conceptually preserve:

```text
Series A
Series B
Timeframe
Window
Lag
Method
Statistic
Sample Size
Regime
Algorithm Version
Provenance
```

---

# 40. Correlation Is Not Causation

ResearchOS must never make the following transformation without additional evidence:

```text
A correlates with B
        ↓
A causes B
```

The correct representation is:

```text
Observed Relationship
        ↓
Statistical Evidence
        ↓
Hypothesis
        ↓
Further Testing
```

---

# 41. Historical Market Memory

Market Memory is expected to become an important bridge between historical data and future Learning.

The intended future flow is:

```text
Current Market State
        ↓
Historical Similarity Search
        ↓
Comparable Historical States
        ↓
Observed Historical Outcomes
        ↓
Evidence
```

This should remain deterministic and auditable.

---

# 42. Research Evidence Pipeline

The complete research pipeline should conceptually be:

```text
External Data
      ↓
Data Engine
      ↓
Validated Dataset
      ↓
Market State
      ↓
Market Memory
      ↓
Quant Engine
      ↓
Macro / Cross-Asset Context
      ↓
Experiment
      ↓
Evaluation
      ↓
Validation
      ↓
Evidence Graph
      ↓
Research Conclusion
```

---

# 43. Self-Audit Architecture

ResearchOS must contain self-auditing behavior across the research pipeline.

The audit layer should evaluate:

### Data

* schema;
* completeness;
* timestamps;
* duplicates;
* source identity.

### Provenance

* source;
* dataset identity;
* version;
* transformations.

### Experiment

* target;
* feature boundary;
* configuration;
* baseline.

### Temporal Integrity

* future leakage;
* publication-time violations;
* revised-data contamination.

### Statistical Integrity

* sample size;
* significance;
* effect size;
* robustness.

### Reproducibility

* deterministic rerun;
* result identity;
* backend consistency.

---

# 44. Architecture Guards

Architecture must be enforced by tests where practical.

The repository already contains architecture-oriented tests, including:

```text
test_architecture_boundary_experiment_quant.py
test_architecture_immutability.py
```

and macro architecture guard tests.

Architecture is therefore not documentation-only.

It should be partially executable as a set of enforceable boundaries.

---

# 45. Locked Core Modules

The architecture audit identified the following major modules as controlled/locked architectural areas:

```text
researchos/core/
researchos/data_engine/
researchos/market_memory/
researchos/experiments/
researchos/intelligence/
researchos/orchestration/
researchos/pipeline_repository/
researchos/quant_engine/
```

Changes to these areas should be treated as architectural changes when they modify contracts or boundaries.

---

# 46. Contract Architecture

ResearchOS contains a substantial contract surface.

The architecture audit identified approximately:

```text
20 contract-related files
```

Contracts must be treated as first-class architectural interfaces.

A contract should define:

* input;
* output;
* identity;
* invariants;
* serialization;
* determinism;
* error behavior.

Implementation must not silently redefine an established contract.

---

# 47. Immutability

ResearchOS uses immutability as a major architectural principle.

Where an object represents:

* historical evidence;
* dataset identity;
* experiment configuration;
* evaluation result;
* provenance;

mutation after creation should be prohibited or tightly controlled.

The goal is to prevent historical research records from changing after they have been used.

---

# 48. Learning Layer

## Status

```text
FUTURE — NOT IMPLEMENTED AS A CANONICAL SUBSYSTEM
```

A future Learning Layer is explicitly reserved.

The intended entry point is:

```text
researchos/learning.py
```

However, the existing:

```text
researchos/quant_engine/machine_learning/
researchos/quant_engine/models/
researchos/quant_engine/training/
researchos/quant_engine/validation/
```

must **not automatically be interpreted as the final Learning Layer architecture**.

Those existing code areas may represent earlier or experimental implementation work.

They do not define the final Learning Layer contract.

---

# 49. Learning Layer Objective

The future Learning Layer is intended to learn empirically from multi-source, multi-angle market context.

Its long-term objective is to investigate individual XAUUSD candle outcomes.

Potential inputs may include:

```text
XAUUSD Market State
DXY
Cross-Asset Relationships
Macro Conditions
Economic Events
Geopolitical Context
Positioning
Volatility
Spread
Liquidity
Historical Market Memory
```

The intended research question is:

> Given the information available around an individual XAUUSD candle, what historical evidence exists for an UP or DOWN outcome?

---

# 50. Future Learning Outputs

Possible future outputs may include:

```text
P(UP)
P(DOWN)
Calibration
Uncertainty
Historical Support
Relevant Context
Supporting Factors
```

These are architectural objectives only.

They are not yet implementation contracts.

---

# 51. Learning Contract Gate

The Learning Layer must not be implemented as a finalized subsystem until the following are explicitly defined:

```text
Learning Objective
Input Schema
Output Schema
Feature Contract
Target Definition
Training Data Model
Temporal Split Policy
Leakage Policy
Evaluation Protocol
Calibration Protocol
Uncertainty Model
Versioning
Provenance
Reproducibility
Validation Contract
```

No developer should invent these interfaces simply to make the Learning Layer operational.

---

# 52. Learning Data Model

The future Learning dataset should conceptually preserve:

```text
Observation Time
Asset
Market State
Context State
Feature Values
Information Availability Time
Target Definition
Historical Outcome
Dataset Identity
Provenance
```

The critical requirement is:

```text
Features(t)
=
Information available at or before t
```

Never:

```text
Features(t)
=
Information discovered after t
```

---

# 53. Learning Evaluation

A future Learning system must not be evaluated only by prediction accuracy.

Evaluation should eventually include:

* out-of-sample performance;
* calibration;
* Brier score or equivalent probabilistic metrics;
* class balance;
* baseline comparison;
* stability;
* regime robustness;
* temporal robustness;
* leakage resistance;
* reproducibility.

A probability estimate is not trustworthy merely because it looks numerically plausible.

---

# 54. Intelligence vs Learning

The Intelligence Layer and Learning Layer must remain distinct.

## Intelligence

Retrieves and organizes existing evidence.

```text
Evidence
    ↓
Retrieve
    ↓
Context
```

## Learning

Attempts to learn statistical relationships from historical evidence.

```text
Historical Data
    ↓
Learning Dataset
    ↓
Model
    ↓
Probability
```

Intelligence must not pretend that retrieved evidence is a learned prediction.

Learning must not invent evidence that does not exist.

---

# 55. Decision Boundary

ResearchOS may eventually produce research-level probability or decision-support information.

However:

```text
Research Result
    ≠
Broker Order
```

The architecture explicitly excludes autonomous execution.

No layer may silently connect:

```text
Probability
    ↓
Order
```

inside the ResearchOS core.

---

# 56. Monitoring

## Location

```text
monitoring/
```

Monitoring is an operational/supporting layer.

It should observe:

* system health;
* research execution;
* failures;
* performance;
* data pipeline status.

Monitoring must not become a hidden decision engine.

---

# 57. Scripts and Tools

## Locations

```text
scripts/
tools/
```

These are supporting development and operational utilities.

They may provide:

* audits;
* repository checks;
* data utilities;
* build helpers;
* diagnostics;
* migration utilities.

They are not part of the core research domain model.

---

# 58. Tests

The repository has multiple test domains.

Verified test surfaces include:

```text
researchos/tests/
tests/unit/
researchos/data_engine/tests/
researchos/market_memory/tests/
researchos/experiments/phase51/tests/
```

Macro Intelligence also has dedicated tests for:

```text
macro_intelligence/
```

including:

* determinism;
* architecture guards;
* features;
* relationships;
* revision provenance;
* time/calendar.

Testing is part of the architecture.

---

# 59. Current Verification Baseline

The current verification record (2026-08-18 re-check) includes:

```text
Pytest:
3500 passed
60 skipped
```

The C++ backend integration path exists in the repository
(`researchos/quant_engine/research_cpp_backend.py`,
`CppQuantAdapter`) and native module. Whether `IS_CPP: True` at
runtime depends on the native module being built for the active
platform/Python version — this must be re-verified per environment
rather than treated as a fixed global fact. A clean checkout without
a prebuilt native module falls back to `PythonQuantBackend`
(functionally correct, reference implementation) with a warning,
rather than failing.

Ruff's pass/fail status likewise depends on which rule set is
selected at invocation time; `pyproject.toml` currently pins only
`line-length` and `target-version` under `[tool.ruff]` with no
explicit `select`, so "all checks passed" should be re-verified
against the exact ruff invocation used in CI
(`.github/workflows/`) rather than assumed from a bare `ruff check .`.

---

# 60. Real Data Requirement

Predictive-value research requires real historical XAUUSD data.

Synthetic datasets may be used for:

* engineering tests;
* deterministic tests;
* integration tests;
* benchmark tests.

Synthetic data must never be treated as evidence for real-market predictive value.

The system must explicitly block predictive research when the required real dataset is unavailable.

---

# 61. Preferred XAUUSD Dataset

The preferred XAUUSD historical dataset should preserve, where available:

```text
Timestamp
Open
High
Low
Close
Tick Volume
Spread
```

Additional fields may be included if they have reliable provenance.

The dataset must preserve the original source identity.

---

# 62. Data Availability Boundary

For any historical timestamp `t`, ResearchOS must distinguish:

```text
What happened at t
```

from:

```text
What was known at t
```

This distinction is mandatory for:

* macro events;
* news;
* revisions;
* positioning;
* cross-asset information;
* learning.

---

# 63. Research Status Model

ResearchOS should distinguish:

```text
EXECUTED
VALIDATED
EVIDENCE_SUFFICIENT
```

from:

```text
BLOCKED
INVALID
INSUFFICIENT_EVIDENCE
```

An experiment that executes successfully is not necessarily a valid research result.

---

# 64. Architectural Non-Goals

ResearchOS is not:

* a broker;
* an autonomous trading system;
* a guaranteed prediction engine;
* a black-box AI trader;
* an execution bot;
* a signal-selling platform;
* a replacement for empirical validation.

---

# 65. Architectural Anti-Patterns

The following are prohibited unless explicitly approved through an architecture revision.

## 65.1 Hidden Trading Logic

No hidden BUY/SELL logic in infrastructure.

## 65.2 Fake Evidence

No synthetic evidence represented as real-market evidence.

## 65.3 Look-Ahead Leakage

No future information in historical features.

## 65.4 Untracked Provenance

No result without dataset and experiment identity.

## 65.5 Mutable Historical Results

No modification of completed research records.

## 65.6 Unvalidated Probability

No probability presented as trustworthy without evaluation and calibration.

## 65.7 Premature Learning

No finalized Learning Layer contract before its specification exists.

## 65.8 Duplicate Architecture

Do not create a second parallel subsystem for functionality already owned by an existing module.

For example, do not create a new:

```text
researchos/context/
```

merely to duplicate the existing:

```text
macro_intelligence/
```

relationship architecture.

---

# 66. Target Architecture

The target architecture should evolve from the current codebase rather than replacing it with an invented directory structure.

```text
                         RESEARCHOS
                              │
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
       ▼                      ▼                      ▼
  DATA FOUNDATION       QUANTITATIVE CORE      CONTEXT FOUNDATION
       │                      │                      │
       ▼                      ▼                      ▼
 data_engine            quant_engine         macro_intelligence
       │                      │                      │
       ▼                      │                      ├── features
 market_memory                │                      ├── relationships
       │                      │                      ├── econometrics
       │                      │                      ├── regime
       │                      │                      ├── knowledge
       │                      │                      └── revision
       │                      │
       └──────────────┬───────┘
                      │
                      ▼
                EXPERIMENTS
                      │
                      ▼
                  EVALUATION
                      │
                      ▼
                 VALIDATION
                      │
                      ▼
               EVIDENCE GRAPH
                      │
                      ▼
                INTELLIGENCE
                      │
                      ▼
              RESEARCH OUTPUT
                      │
                      ▼
             FUTURE LEARNING
```

---

# 67. Target Market Context Flow

The intended future XAUUSD context architecture is:

```text
XAUUSD
  │
  ├──────────────► Market State
  │
  ├──────────────► Market Memory
  │
  ├──────────────► Quantitative Measurements
  │
  ├──────────────► DXY Relationship
  │
  ├──────────────► Rates / Yields
  │
  ├──────────────► FX Relationships
  │
  ├──────────────► Macro Events
  │
  ├──────────────► Positioning
  │
  └──────────────► Geopolitical Context
                         │
                         ▼
                   Context State
                         │
                         ▼
                    Experiment
                         │
                         ▼
                      Evidence
```

---

# 68. Asset Expansion

XAUUSD remains the primary research asset.

The future sequence is:

```text
XAUUSD
   ↓
DXY / USD Context
   ↓
Cross-Asset Relationships
   ↓
EURUSD
   ↓
Other FX
   ↓
Other Assets
```

The architecture must avoid duplicating the core infrastructure for each asset.

Shared infrastructure should include:

* Data Engine;
* Quant Engine;
* Experiment Engine;
* Evaluation;
* Validation;
* Provenance;
* Evidence.

---

# 69. Development Sequence

## Phase 1 — Foundation

Maintain and harden:

* Core;
* Data Engine;
* Repository;
* provenance;
* deterministic identity;
* validation.

---

## Phase 2 — Quantitative Infrastructure

Maintain and expand:

* Python backend;
* C++ backend;
* backend routing;
* numerical parity;
* benchmarks.

---

## Phase 3 — XAUUSD Research

Focus on:

* real historical XAUUSD data;
* market state;
* market memory;
* candle outcomes;
* predictive-value experiments;
* baselines.

---

## Phase 4 — Market Context

Expand:

```text
DXY
↓
Rates / Yields
↓
FX Relationships
↓
Macro
↓
Positioning
↓
Geopolitical / Event Context
```

---

## Phase 5 — Research Validation

Strengthen:

* leakage detection;
* statistical significance;
* robustness;
* calibration;
* reproducibility;
* evidence lineage.

---

## Phase 6 — Learning Specification

Before implementation:

```text
Define
   ↓
Review
   ↓
Test Conceptually
   ↓
Freeze Contract
```

---

## Phase 7 — Learning Implementation

Only after Phase 6:

```text
Learning Dataset
      ↓
Learning Engine
      ↓
Probability
      ↓
Calibration
      ↓
Validation
      ↓
Evidence
```

---

## Phase 8 — Multi-Asset Expansion

After sufficient XAUUSD research maturity:

```text
EURUSD
GBPUSD
USDJPY
Other Assets
```

---

# 70. Architectural Change Control

Any change to the following must be considered an architectural change:

* package responsibility;
* contract;
* dependency direction;
* data model;
* provenance model;
* experiment identity;
* backend boundary;
* validation boundary;
* Learning Layer contract.

Architectural changes must be documented before implementation becomes dependent on them.

---

# 71. Current vs Future Classification

Every architectural component must be classified as one of:

```text
CURRENT
```

meaning implemented and part of the current architecture;

```text
TRANSITIONAL
```

meaning present in the repository but not necessarily part of the final architecture;

or:

```text
FUTURE
```

meaning intentionally reserved but not implemented.

This prevents historical/experimental code from being mistaken for the canonical future design.

---

# 72. Current/Future Learning Distinction

The following distinction is mandatory:

```text
Existing machine-learning-related code
        ≠
Canonical Learning Layer
```

The canonical Learning Layer begins only when:

```text
Specification
+
Data Contract
+
Evaluation Contract
+
Validation Contract
```

have been explicitly defined.

Until then, `learning.py` remains a reserved architectural boundary.

---

# 73. Architectural Maturity

ResearchOS should be evaluated according to actual evidence.

```text
Level 0
Engineering Foundation

Level 1
Deterministic Research Infrastructure

Level 2
Validated XAUUSD Historical Research

Level 3
Multi-Context Market Research

Level 4
Validated Probabilistic Learning

Level 5
Multi-Asset Research Platform
```

The project must never claim a higher level than the evidence supports.

---

# 74. Definition of Done — Core

The architecture is structurally mature when:

* data identity is reliable;
* provenance is preserved;
* experiments are reproducible;
* configuration snapshots are stable;
* quantitative backend contracts are explicit;
* Python/C++ parity is tested;
* market memory is auditable;
* macro context is traceable;
* experiments have explicit targets;
* validation can reject invalid research;
* evidence has lineage.

---

# 75. Definition of Done — Predictive Research

Predictive research requires:

```text
Real Data
+
Explicit Target
+
Historical Information Boundary
+
Leakage-Free Features
+
Baseline
+
Out-of-Sample Evaluation
+
Statistical Evaluation
+
Calibration
+
Robustness
+
Reproducibility
+
Provenance
```

A model output alone is insufficient.

---

# 76. Definition of Done — Future Learning

The future Learning Layer is complete only when:

* objective is defined;
* input contract is frozen;
* output contract is frozen;
* target definition is frozen;
* training dataset construction is defined;
* temporal leakage controls are defined;
* evaluation methodology is defined;
* calibration is defined;
* uncertainty is represented;
* model versioning is defined;
* provenance is preserved;
* deterministic/reproducible behavior is demonstrated;
* self-validation is integrated.

---

# 77. Final Architecture Invariant

The central invariant of ResearchOS is:

> **No predictive intelligence without validated historical evidence.**

The canonical hierarchy is:

```text
DATA
  ↓
DATA VALIDATION
  ↓
STRUCTURED STATE
  ↓
QUANTITATIVE MEASUREMENT
  ↓
MARKET MEMORY / RELATIONSHIPS
  ↓
EXPERIMENT
  ↓
EVALUATION
  ↓
VALIDATION
  ↓
EVIDENCE
  ↓
INTELLIGENCE
  ↓
FUTURE LEARNING
  ↓
PROBABILITY
```

Never:

```text
LLM / INTUITION
       ↓
PREDICTION
       ↓
FALSE CONFIDENCE
```

---

# 78. Canonical System Map

```text
┌────────────────────────────────────────────────────────────┐
│                         RESEARCHOS                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  CORE                                                      │
│  ├── core                                                  │
│  ├── objects                                               │
│  └── repository                                            │
│                                                            │
│  DATA                                                       │
│  ├── data_engine                                           │
│  └── market_memory                                         │
│                                                            │
│  QUANTITATIVE                                               │
│  ├── quant_engine                                          │
│  ├── Python backend                                        │
│  ├── CppQuantAdapter                                       │
│  └── native C++ engine                                     │
│                                                            │
│  MARKET / DECISION                                         │
│  ├── memory                                                │
│  └── decision_engine                                       │
│                                                            │
│  RESEARCH                                                   │
│  ├── experiments                                           │
│  ├── orchestration                                         │
│  ├── pipeline_repository                                   │
│  └── evaluation                                            │
│                                                            │
│  VALIDATION                                                 │
│  └── validation                                            │
│                                                            │
│  INTELLIGENCE                                               │
│  └── intelligence                                          │
│                                                            │
│  MACRO / CONTEXT                                            │
│  └── macro_intelligence                                    │
│      ├── contracts                                         │
│      ├── features                                          │
│      ├── relationships                                     │
│      ├── econometrics                                      │
│      ├── statistics                                        │
│      ├── regime                                             │
│      ├── revision                                          │
│      ├── knowledge                                         │
│      ├── storage                                           │
│      └── time                                              │
│                                                            │
│  OPERATIONAL                                               │
│  ├── monitoring                                            │
│  ├── scripts                                               │
│  └── tools                                                 │
│                                                            │
│  FUTURE                                                     │
│  └── Learning Layer                                        │
│      └── researchos/learning.py                            │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Canonical Research Output Flow

The canonical research output flow is:

``text
INTELLIGENCE
     ↓
PROBABILITY
     ↓
RESEARCH OUTPUT
```

The Future Learning Layer remains a future, specification-gated subsystem and is not a mandatory stage of the current canonical execution flow.

---

# 79. Final Status

This document is the canonical architecture reference for ResearchOS.

The architecture is intentionally divided into:

```text
CURRENT
TRANSITIONAL
FUTURE
```

Existing repository code must not be retroactively reclassified as a future subsystem without explicit architectural review.

The current quantitative foundation, market memory, macro intelligence, experimentation, evaluation, validation, intelligence, provenance, and C++ backend integration form the present research infrastructure.

The future Learning Layer remains intentionally undefined at the contract level.

Its specification must be created before implementation.

The ultimate purpose of ResearchOS remains:

> **To discover, measure, validate, and preserve real historical market knowledge — especially for XAUUSD — before attempting to turn that knowledge into probabilistic intelligence.**

---

**End of Canonical Architecture Specification**


# QROS SaaS Architecture Freeze — Golden Path V1

QROS is now treated as a product workflow around the governed research core.

L0 Infrastructure -> L1 Identity/Tenant -> L2 Research Objects -> L3 Research Pipeline -> L4 API -> L5 UI -> L6 Monetization.

Golden Path: Register -> Workspace -> Dataset -> DatasetVersion -> ResearchRun -> Analysis -> Evidence -> Claim -> Result.

Until this Golden Path is production-validated, new research features and new top-level architecture layers are out of scope except security, reliability, correctness, and production-blocking fixes.

No TenantContext means no business operation. Tenant identity is server-derived. Scientific inputs and outputs retain immutable/content-addressed provenance. Production schema changes are migration-based.
