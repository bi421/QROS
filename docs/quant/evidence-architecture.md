# QROS Quant Evidence Architecture

## Objective

Separate mathematical evidence generation from validation, integration, calibration, and final probability synthesis.

The system must never convert a collection of model outputs into a probability merely because the outputs are available.

## Layered execution graph

```text
RAW OHLCV
  |
  v
[1] Data Integrity
  |
  +-------------------- independent evidence branches --------------------+
  |       |          |          |          |          |          |         |
  v       v          v          v          v          v          v         v
Geometry  Geometric  First      Bayesian  Monte     Diffusion   OU      Dynamics
          Null       Passage             Carlo
  |       |          |          |          |          |          |         |
  +--------------------+------------------+------------------+-------------+
                       |
                       v
                 Mathematical Verification
                       |
                       v
                 Statistical Validation
                       |
                       v
                  Evidence Integration
                       |
                       v
                    Calibration
                       |
                       v
             Probability Synthesis (future)
```

## Independent evidence branches

Implemented native kernels:

- Candle geometry: range, body ratio, wick ratios, close position.
- Geometric null: interval occupancy baseline.
- First passage: driftless barrier baseline.
- Empirical edge: empirical minus geometric null plus diagnostic statistic.
- Bayesian signal filtering.
- GBM Monte Carlo.
- Heat/diffusion density and interval probability.
- GBM Fokker-Planck transition density.
- Ornstein-Uhlenbeck conditional moments and interval probability.
- Market velocity, momentum, and force.
- Shannon entropy.

Not yet implemented as production evidence kernels:

- Market structure.
- General statistical-model branch.
- Empirical-frequency branch as a first-class independent module.

These are explicitly tracked as missing rather than represented by placeholder probabilities.

## Semantic separation

Every evidence item carries:

- branch identity;
- quantity type: feature, probability, density, statistic, or score;
- validation status;
- sample size;
- uncertainty bounds;
- model version;
- data version;
- independence group.

A density is not a probability. A feature is not a probability. A null-model probability is not a calibrated forecast.

## Validation gates

The native state machine enforces:

1. Data integrity.
2. Independent evidence collection.
3. Mathematical verification.
4. Statistical validation.
5. Evidence integration.
6. Calibration.

Final probability synthesis is deliberately disabled until a dependency-aware, out-of-sample calibrated synthesizer exists.

## Probability synthesis requirements

Future synthesis must not use a naive arithmetic average.

It must account for:

- correlated evidence branches;
- out-of-sample predictions;
- calibration;
- sample size;
- uncertainty;
- model/data version;
- leakage;
- multiple testing;
- temporal dependence.

Candidate methods include dependency-aware stacking, logistic/meta-models, Bayesian model averaging, hierarchical weighting, and isotonic/Platt calibration. The method must be selected and tested before the synthesis gate is enabled.

## Performance structure

Native numerical kernels use caller-owned buffers and release the Python GIL at the nanobind boundary.

The next optimization layer is:

1. validate inputs before parallel execution;
2. parallelize independent rows with OpenMP where beneficial;
3. add runtime-safe AVX2/AVX-512 dispatch;
4. preserve a deterministic scalar reference path;
5. benchmark before changing data layout.

Performance claims require measured benchmark evidence, not compiler flags alone.

## Non-negotiable contract

```text
model output != calibrated probability
p-value != trading edge
statistical significance != economic significance
correlated evidence != independent evidence
OOS support != proof of future performance
```
