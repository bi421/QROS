# Market Structure Data Adapter — Phase 4 Report

**Status:** `PASS — READ-ONLY M1 FRAME ADAPTER IMPLEMENTED`
**Base commit:** `4dc6e3331252dd04c8339529f5ffab11517a7ebd`
**Branch:** `feat/market-structure-variants`

## Goal

Provide a strict, read-only boundary between an already-loaded tabular M1 dataset and the Phase 3 detector. This phase implements an adapter only; it does not load, inspect, or execute the real FTMO dataset.

## Files

- `researchos/quant_engine/technical/market_structure_adapter.py`
- `tests/unit/test_market_structure_adapter.py`
- `researchos/quant_engine/technical/__init__.py` (public exports)
- `docs/research/market_structure/PHASE4_REPORT.md`

## Adapter contract

`market_structure_input_from_frame()` accepts a pandas DataFrame and explicit symbol metadata. Required columns are UTC datetime (`time` by default), `open`, `high`, `low`, and `close`. Optional MT5 fields `spread`, `tick_volume`, and `real_volume` are preserved separately; spread remains in source points, not silently converted to price units.

Validation is fail-closed:

- M1 only; no implicit timeframe conversion.
- No empty frames or duplicate column names.
- No timestamp parsing guesses, timezone localization, sorting, deduplication, resampling, or synthetic-bar insertion.
- Timestamps must already be timezone-aware UTC, whole-minute aligned, unique, and strictly increasing.
- OHLC values must be numeric, finite, and internally consistent.
- If `is_complete` exists, every row must explicitly be complete.
- Optional metadata preserves nulls but rejects nonnumeric, negative, or non-finite present values.
- Original row order and observed timestamp gaps are preserved.

The result is a frozen `MarketStructureInput` with tuple-backed fields. It does not call the detector; a synthetic integration test demonstrates that the adapter output can be passed to the detector explicitly.

## Verification evidence

```text
py -3 -m pytest -q tests/unit/test_market_structure_adapter.py
35 passed in 1.20s

py -3 -m pytest -q tests/unit/test_market_structure_adapter.py tests/unit/test_market_structure_detector.py tests/unit/test_market_structure_definition.py
75 passed in 5.06s

py -3 -m ruff check [all Phase 2–4 files]
All checks passed!

py -3 -m mypy --config-file pyproject.toml --follow-imports=skip researchos/quant_engine/technical/market_structure_adapter.py
Success: no issues found in 1 source file

py -3 scripts/check_text_integrity.py [adapter and test]
TEXT INTEGRITY: PASS (2 files checked)

git diff --check
DIFF_EXIT=0
```

## Explicit non-actions

- No raw dataset file was opened by this phase.
- No FTMO market-data row was adapted or passed to the detector.
- No grid/variant runner was invoked on market data.
- No changes to costs, fills, backtest engine, OOS, Supabase, Auth/RLS, MT5 connection, or execution.

## Gate decision

Phase 4 passes as a synthetic-only adapter. Phase 5 grid execution remains blocked by the registered SPEC: exact account-specific commission/volume-band and slippage evidence are not certified, and prospective OOS data is not yet available. The Phase 3 performance smoke test also remains a warning: 5,000 synthetic rows × 56 definitions took 18.002 seconds, so no full-scale run is authorized.

**Decision:** Commit the adapter and stop before any market-data execution. A later phase may address performance or non-executing infrastructure only if it does not violate the pre-registration gates.
