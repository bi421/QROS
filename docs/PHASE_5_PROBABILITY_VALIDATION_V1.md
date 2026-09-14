# Phase 5 — Probability Validation Boundary v1

## Purpose

Phase 5 establishes an auditable validation boundary between probability production and downstream risk consumption.

The boundary measures probability quality against observed outcomes. It does **not** alter probabilities and does not fit an ML model.

## Architecture

```text
EvidenceCollection
      ↓
ProbabilityCalculator
      ↓
ProbabilityAssessment
      ↓
ProbabilityValidation
      ├── invariant validation
      ├── Brier score
      ├── multiclass log loss
      ├── ECE / MCE reliability diagnostics
      └── sample-size gate
      ↓
Risk boundary
```

## Contract

`ProbabilityValidationReport` is immutable and versioned as `probability-validation.v1`.

It records:

- number of assessment/outcome pairs;
- Brier score;
- log loss;
- expected calibration error (ECE);
- maximum calibration error (MCE);
- deterministic reliability bins;
- calibration status;
- limitations.

## Calibration rule

This phase intentionally does not claim that a probability is calibrated merely because it can be calculated.

If the validation sample is below the configured minimum, status is:

`INSUFFICIENT_SAMPLE`

Otherwise the report is:

`CALIBRATION_READY`

`CALIBRATION_READY` means that sufficient observations exist for calibration work; it does not mean that the probability model has been recalibrated or proven accurate.

## Safety / research invariants

1. No probability is silently changed.
2. No ML/LLM calibration model is introduced.
3. No broker or order execution is introduced.
4. Invalid assessment/outcome pairs fail explicitly.
5. Zero probability assigned to an observed outcome produces infinite log loss rather than being hidden by an arbitrary epsilon.
6. Results are deterministic for identical inputs.
7. Calibration diagnostics remain separate from risk calculation.
