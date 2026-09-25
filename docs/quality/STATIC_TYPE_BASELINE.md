# Governed Static Type Check Baseline

## Baseline

Measured on commit `ad5465cb3060fd5aa2a4c09c3d53e84571956a94` with mypy 2.3.1 and Python 3.12:

- 213 mypy errors across 40 files in `researchos/saas`.
- 28 errors were in production modules.
- 185 errors were in test modules.
- The remaining errors are pre-existing typing debt; they are not suppressed.

The first attempted whole-SaaS gate also exposed a dependency-stub incompatibility when the checker target was Python 3.10: NumPy 2.5.3 stubs use a Python 3.12-only `type` statement. The governed checker therefore targets Python 3.12, matching the CI execution environment; this does not change QROS runtime support.

## Governed boundary

The enforced CI boundary is intentionally limited to the following production-critical SaaS contracts that are currently type-clean:

- `researchos/saas/api.py`
- `researchos/saas/contracts.py`
- `researchos/saas/claim_api.py`
- `researchos/saas/evidence_api.py`

CI runs `mypy` against exactly this configured file set.

This is an explicit incremental boundary, not a claim that the repository is fully typed. No `ignore_errors`, blanket `type: ignore`, or production-code exclusion was added to make the governed files pass.

## Incremental policy

1. The governed boundary must remain error-free.
2. New production modules should enter the governed boundary only after their baseline is measured and repaired.
3. The 28 existing production errors outside the boundary remain tracked technical debt.
4. Broadening the boundary must not be accompanied by suppression of newly discovered errors.
