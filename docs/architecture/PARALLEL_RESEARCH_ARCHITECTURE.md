# QROS Parallel Research Architecture

Status: TRANSITIONAL -> CURRENT execution primitive
Base: 1008602be7e966b741b69eda2e75f0e77fc2d10c
Branch: feat/parallel-research-architecture-20261004

## Purpose

QROS must not model research as one long serial chain when independent evidence
families can be computed concurrently.

This change adds parallel execution inside the existing orchestration layer.
It does not create a second quant core, second runner, second evidence model, or
second repository.

## Canonical structure

    INPUT SNAPSHOT
           |
      +----+----+----+
      |         |   |
      v         v   v
    DATA      QUANT CONTEXT
    QUALITY   EVIDENCE
      |         |   |
      +----+----+---+
           |
         BARRIER
           |
      +----+----+----+
      |         |   |
      v         v   v
    VALIDATION SIMULATION ROBUSTNESS
      |         |   |
      +----+----+---+
           |
         BARRIER
           |
    EVIDENCE INTEGRATION
           |
       CALIBRATION
           |
      VALIDATION GATE
        /        \
      PASS       BLOCK
       |           |
       v           v
    OUTPUT      NO PROMOTION

The diagram describes dependency groups, not a claim that every named branch is
already implemented. Only the execution primitive and the first real parallel
slice are implemented by this change.

## First real parallel slice

The existing ResearchOrchestrator.run_pipeline() already builds one immutable
dataset before analysis. After that point:

    DATASET
       |
       +------ VALIDATION
       |
       +------ TRAINING

are independent in the current implementation and are now dispatched in the
same parallel wave.

The result is still deterministic:

- branch identifiers are explicit;
- output order follows the plan, not completion timing;
- the dataset is created before either branch starts;
- a failed branch fails the wave;
- later waves cannot start after failure;
- no partial wave is promoted;
- persistence remains outside orchestration.

## Future waves

The same primitive can host additional independent evidence bundles without
creating duplicate scientific modules:

    Wave 0: immutable input/data snapshot
    Wave 1: technical | probabilistic | market-context | data-quality
    Wave 2: statistical validation | simulation | robustness
    Wave 3: integration
    Wave 4: calibration
    Wave 5: final evidence gate

A branch must use an existing canonical module. The orchestration layer only
schedules it.

## CPU and GIL rule

The default scheduler uses a thread pool. This is intentional for an
orchestration boundary because native numerical kernels can release the GIL and
because some branches may be I/O-bound.

Pure-Python CPU-heavy work must not be described as CPU-parallel merely because
it is submitted to threads. A process-backed executor can be supplied through
the executor factory when a branch genuinely requires process-level CPU
parallelism.

## Failure rule

Parallelism never weakens governance.

    branch failure
         |
         v
      wave FAILED
         |
         +--> cancel not-started work
         |
         +--> do not start next wave
         |
         +--> no partial-success promotion

This preserves QROS's fail-closed research contract.

## Architecture boundary

    EXISTING SCIENTIFIC MODULES
        data_engine
        quant_engine
        macro_intelligence
        validation
        experiments
              |
              v
    EXISTING ORCHESTRATION
        ParallelResearchExecutor
              |
              v
    EXISTING PIPELINE / EVIDENCE / REPOSITORY

The scheduler owns when/how independent work is run. Scientific modules
continue to own what is computed.

## Not implemented by this change

This change does not claim that all evidence families are now parallelized.
It does not implement:

- market-structure computation;
- macro-data ingestion;
- calibration;
- final probability synthesis;
- new customer onboarding;
- billing;
- production hosting.

Those remain separate work items and require their own verification.
