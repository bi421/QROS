# ResearchOS Technology Ecosystem & Admission Matrix 2026

**Status:** Controlled technology baseline 1.0  
**Date:** 2026-09-17

This document prevents ResearchOS from becoming a random collection of popular libraries. A technology enters the system only when its responsibility, boundary, contract, tests, and operational cost are understood.

| Area | Baseline | Role | Admission rule |
|---|---|---|---|
| Python numerics | NumPy | deterministic numerical primitives | core |
| Tabular research | pandas / Polars | data manipulation | use per workload; avoid duplicate logic |
| Columnar data | PyArrow | Parquet/schema/interop | core data contract |
| Analytical SQL | DuckDB | local/embedded analytical research | preferred for file analytics |
| Statistics | SciPy | distributions/tests/optimization | core |
| Econometrics | statsmodels | time-series/econometric diagnostics | governed model adapters |
| ML | scikit-learn | baseline ML/evaluation | core research option |
| Gradient boosting | XGBoost / LightGBM | tabular ML candidates | experiment dependency, not core truth |
| Deep learning | PyTorch | advanced ML | add only when a research hypothesis requires it |
| Visualization | Matplotlib / Plotly | research inspection | presentation only; never source of truth |
| Notebook | Jupyter | exploratory research | non-canonical execution surface |
| C++ algebra | Eigen | high-performance linear algebra | preferred C++ primitive |
| Python/C++ binding | nanobind or pybind11 | explicit bridge | one canonical binding strategy per engine |
| Networking | Boost.Asio | future low-latency I/O | execution-plane only unless justified |
| Database | PostgreSQL / Supabase | application/evidence system of record | SaaS baseline |
| Time-series DB | TimescaleDB | high-volume time-series workloads | introduce when workload requires it |
| Cache | Redis | transient state/cache/queue support | never source of research truth |
| Object storage | S3-compatible | large immutable artifacts | required for production artifact scale |
| Messaging | NATS / Kafka | distributed event transport | scale-triggered, not default |
| Containers | Docker | reproducible runtime | baseline |
| CI/CD | GitHub Actions | quality gates | mandatory |
| Observability | OpenTelemetry | telemetry standard | production baseline |
| Metrics | Prometheus/Grafana | operational visibility | production scale |
| Error tracking | Sentry or equivalent | failure visibility | production scale |

## Quantitative method registry

The following are ResearchOS-governed methods, regardless of which third-party implementation provides numerical primitives:

```text
Probability
  conditional probability
  Bayes
  binomial / Beta-Binomial

Payoff
  expected value
  Kelly mathematics

Uncertainty
  bootstrap
  block bootstrap
  effective sample size

Risk
  VaR
  Expected Shortfall
  drawdown

Econometrics
  stationarity
  autocorrelation
  ARIMA family
  GARCH / EGARCH / GJR-GARCH

Stochastic
  GBM
  Ornstein-Uhlenbeck
  jump/stochastic-volatility extensions when justified

Distribution / Tail
  Student-t
  EVT / GPD

Dependence
  copulas
  tail dependence

Information
  Shannon entropy
  conditional entropy
  mutual information

Inference
  Sharpe inference
  PSR
  DSR

Selection
  multiple-testing controls
  White Reality Check
  Hansen SPA
  PBO
  CPCV
  purging / embargo

Calibration
  reliability
  Brier
  log loss
  calibration slope/intercept
```

## Dependency rules

### Rule A — No duplicate responsibility

Two packages should not independently implement the same canonical research calculation unless one is an independently validated reference implementation used for differential testing.

### Rule B — Reference vs production implementation

For critical numerical methods, ResearchOS may maintain:

`reference implementation → optimized implementation → differential tests`

This is preferred to trusting a fast implementation without an oracle.

### Rule C — Version pinning

Production research environments must be lockable. A result must identify the dependency environment sufficiently to reproduce it.

### Rule D — Numerical tolerance

Floating-point comparisons must use method-appropriate tolerances. Exact equality is reserved for exact/deterministic representations.

### Rule E — No AI as numerical oracle

An LLM may generate analysis plans or explanations but cannot be the authoritative calculator for probability, risk, statistical inference, or validation.

## Technology lifecycle

```text
PROPOSED
  ↓
RATIONALE
  ↓
PROTOTYPE
  ↓
BENCHMARK / NUMERICAL CHECK
  ↓
INTEGRATION TEST
  ↓
ADMITTED
  ↓
MONITORED
  ↓
DEPRECATED / REPLACED
```
