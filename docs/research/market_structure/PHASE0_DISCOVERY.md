# Market Structure Variant Study — Phase 0 Discovery

**Phase status:** BLOCKED (repository discovery and Python test baseline recorded; external release gates are not green)

**Discovery timestamp:** 2026-11-01T16:23:27.552883+00:00 (from `.health/health_evidence.json`)

## 1. Git baseline

- Repository: `C:\Users\User\Desktop\QROS`
- Remote: `origin https://github.com/bi421/QROS.git`
- `origin/main` at discovery: `9e73a7e0db33b3240e089d34c16334e41ad40acc`
- Local `main` at discovery: `9e73a7e0db33b3240e089d34c16334e41ad40acc`
- Feature branch created from that same commit: `feat/market-structure-variants`
- Phase 0 HEAD before the documentation commit: `9e73a7e0db33b3240e089d34c16334e41ad40acc`
- Python: `3.12.10`

The worktree already contained these uncommitted changes before Phase 0 discovery. They were preserved and not edited during Phase 0:

- Modified: `researchos/quant_engine/technical/__init__.py`
- Untracked: `researchos/quant_engine/technical/market_structure.py`
- Untracked: `tests/unit/test_market_structure_detector.py`
- Untracked: `docs/architecture/market-structure-variation-engine.md`

The earlier Market Structure detector work is therefore not part of a clean committed baseline. It must not be treated as a completed integration or as a market-data backtest result.

## 2. Literal baseline checks

Commands run:

```powershell
py -3 --version
py -3 -m ruff check .
py -3 scripts/final_health_check.py
```

Observed output:

```text
Python 3.12.10
All checks passed!
RUFF_EXIT=0
```

Full health-check pytest result:

```text
4554 passed, 41 skipped, 3 warnings in 688.82s (0:11:28)
Coverage: 77.6257765035156%
HEALTH: FAIL
```

Additional health gates:

- `red_team_tenant_isolation`: PASS — 2 passed, 40 deselected.
- `authz_matrix`: PASS — 14 passed.
- `real_tenant_isolation`: FAIL/BLOCKED — required environment was absent: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
- `rls_tenant_isolation`: FAIL/BLOCKED — local PostgreSQL refused connection at `127.0.0.1:54322`; Supabase local DB was not running.
- `backup_verify_contract`: FAIL — required workflow text `sha256sum --check` was missing.

Overall health is FAIL because of these additional release gates, not because the full pytest suite failed. The health evidence file is `.health/health_evidence.json`; coverage output is `.health/coverage.json`.

## 3. Canonical engine ownership and existing backtest paths

`docs/CANONICAL_ENGINE.md` declares:

- Public/domain quant API: `researchos/quant_engine/`.
- Native C++ implementation: `cpp_quant_engine/`.
- `cpp_quant/` is legacy/forbidden for new implementation.
- New engine/module additions must first be checked against existing implementations.

Relevant implementations found:

- `researchos/quant_engine/simulation.py:35` — `HistoricalSimulationEngine`; delegates numerical simulation to a `QuantComputationInterface` backend. Its default backend is `PythonQuantBackend`.
- `researchos/quant_engine/execution.py:62` — `ExecutionSimulationLayer`; deterministic signal/order/fill/position/trade simulation with commission and slippage specifications.
- `researchos/quant_engine/backtest.py:21` — a separate simple `BacktestEngine` using a price list and strategy-generated signals; defaults to percentage commission/slippage.
- `researchos/quant_engine/advanced_backtest.py:26` — `AdvancedBacktestEngine` also exists.
- `researchos/orchestration/vectorized_backtest.py:367` — `run_grid`, an existing specialized XAUUSD vectorized event-study/backtest path. It is not a generic Market Structure strategy adapter.

The repository therefore has multiple historical/backtest-related classes. The canonical ownership document, not a new package or duplicate engine, is the governing boundary. The exact adapter target for a Market Structure trade simulation must be decided from the existing execution contracts before implementation.

## 4. Vectorized XAUUSD engine facts

File: `researchos/orchestration/vectorized_backtest.py`

- `EngineConfig` begins at line 15.
- `_apply_barrier_step` begins at line 259. It checks stop before target and models a stop gap at the worse bar open.
- `_causal_signal_score` begins at line 324. Its docstring says a signal at bar `t` is eligible for entry at the next bar open and invalidates lookback windows crossing a 15-minute gap.
- `run_grid` begins at line 367.
- Entry index is `sig + 1`; entry price is the next bar open.
- The current grid is based on close movement normalized by ATR and includes FOLLOW_SIGNAL / REVERSE_SIGNAL directions, lookbacks, z thresholds, TP/SL ATR multiples, horizons, and optional news buffers. It is not a Market Structure grid.
- The current code marks a candidate insufficient when `len(sig) < 20`; this is not the 1,245-observation gate specified for the planned Market Structure study.
- The final chronological 20% is used as a holdout in this engine.
- Benjamini–Hochberg FDR and block-bootstrap statistics are present in this path.
- Costs are considered verified only when cost values are configured, `cost_model_verified` is true, and a valid evidence SHA-256 is supplied. Otherwise the engine returns `NO_TRADE_COST_AUDIT_UNVERIFIED` and does not certify net expectancy.

## 5. Dataset and frozen XAUUSD research paths

- `researchos/data_engine/dataset.py:54` — `HistoricalDataset`; records are content-hashed and become immutable after `mark_ready()`.
- `researchos/data_engine/xauusd_dataset.py:8` — `XAUUSD_M1_Dataset`; default Parquet path is `data/curated/xauusd/xauusd_m1_2023_2025.parquet`; loads and sorts by `ts_utc`, optionally resampling with Polars dynamic windows (first open, max high, min low, last close).
- `scripts/confirm_xauusd_m1_frozen_candidate.py` — public frozen confirmation boundary.
- `scripts/_confirm_xauusd_m1_frozen_candidate_impl.py:272` — confirmation implementation; candidate selection is frozen before confirmation labels are evaluated; confirmation rows are partitioned into folds.
- `docs/research/xauusd_m1_frozen_confirmation.md` documents a development/untouched-confirmation split and B-level gates.

The presence of a default data path in code does not by itself prove that the file exists, is the approved frozen version, or has the required dataset hash. Those must be verified before any variant result is computed.

## 6. Experiment and evidence contracts

- `researchos/experiments/experiment.py:33` — `Experiment`.
- `researchos/experiments/contracts.py:63` — `DatasetConfig`; line 132 — `SimulationConfig`; line 196 — `MetricDefinition`.
- `researchos/experiments/result.py:40` — `ExperimentRun`; captures dataset/simulation config snapshots and a deterministic `run_hash`.
- `researchos/experiments/result.py:224` — `ExperimentResult`; read-only mapping views and deterministic `result_hash`.
- No `ExperimentSnapshot` class was found in the `researchos` Python source search. Existing snapshot behavior is implemented through config snapshot methods and `ExperimentRun` fields.
- `researchos/evidence/repository.py:21` — append-only `EvidenceRepository` with immutable artifact and parent-lineage checks.
- `researchos/evidence/envelope.py:93` — frozen `EvidenceEnvelope`; artifact and lineage hashes use canonical SHA-256 serialization.

## 7. Cost and execution facts

`config/costs.yaml` currently has:

- overall `status: UNVERIFIED`;
- spread base and session multipliers unset;
- round-trip commission and contract size unset;
- slippage base and volatility multiplier unset;
- swap values and triple-swap day unset;
- no verification identity, timestamp, or evidence hash.

Observed SHA-256 for `config/costs.yaml` at discovery:

`C487EE9F71E68A80925D63C15AA58164EF78666D25B46B8FA95533DA0DE8BD83`

`researchos/quant_engine/execution.py` documents deterministic commission and slippage specifications. Integration of this layer with the specialized vectorized XAUUSD grid has not been established by this discovery and must not be assumed.

## 8. Look-ahead and execution-timing tests

- `docs/validation/NO_LOOKAHEAD.md:1` states signals execute only on the following bar open and walk-forward test intervals are disjoint.
- `tests/unit/test_quant_replay_execution_timing.py:35` tests next-bar-open fill timing.
- `tests/unit/test_xauusd_ohlc_outcome_labels.py:86` tests entry at next-bar open rather than decision-bar close.
- `researchos/orchestration/vectorized_backtest.py:324` and `:259` contain causal signal and conservative stop/target handling.

These are existing contracts/tests; Phase 0 did not independently prove every engine path satisfies them.

## 9. Backend selection facts

Observed runtime checks:

```text
Python 3.12.10
has_cpp_research_engine= True
ResearchCppBackend.is_cpp= True
```

`researchos/quant_engine/research_registry.py:67` defines `create_research_engine(..., use_cpp=False)`; the default selects `PythonResearchBackend`. Passing `use_cpp=True` selects `ResearchCppBackend`. `ResearchCppBackend` delegates certified base quant operations to `CppQuantAdapter` when available and keeps analytical surfaces on the Python reference where not yet C++ certified. Therefore C++ availability does not mean every QROS backtest is executing in C++.

## 10. Phase 0 findings and open risks

1. Reuse is mandatory: do not create another backtest engine or duplicate the canonical quant package.
2. The specialized vectorized engine is currently an ATR-normalized momentum/event-study grid, not a Market Structure strategy engine.
3. Existing vectorized grid has a 20-signal minimum, whereas the Market Structure specification requires a 1,245-observation minimum. This must be handled explicitly in the preregistered contract, not silently conflated.
4. XAUUSD cost parameters are unverified and null; no candidate may be promoted while cost evidence is missing.
5. The exact execution adapter target remains to be selected after inspecting the existing engine contracts.
6. `ExperimentSnapshot` was not found as a named class; use existing `ExperimentRun`/`ExperimentResult` and snapshot contracts unless a verified alternative is found.
7. Real Supabase and local RLS release checks remain blocked by unavailable environment/database prerequisites.
8. The worktree has prior uncommitted Market Structure files; preserve them and do not treat them as Phase 0 baseline source.

## 11. Phase 0 scope statement

Phase 0 performed repository discovery and verification only. No Python source, tests, cost configuration, dataset, or trading logic was edited during this phase. The only intended repository artifact from Phase 0 is this discovery document; `.health/` files are generated health-check evidence.

**Phase 0 decision:** discovery facts are recorded; overall phase remains BLOCKED until the external health prerequisites are available and the existing worktree changes are reconciled. No market data was run through the Market Structure variants in this phase.