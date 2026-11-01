# Market Structure Variant Study — Phase 2 Report

**Phase / Status:** `PASS — IMMUTABLE STRUCTURE DEFINITION IMPLEMENTED`
**Base commit:** `1d9b8184343ee41cd925838d0e63e9ec247fbac6`
**Branch:** `feat/market-structure-variants`

## Goal

Create an immutable, deterministic, content-addressed definition for every registered Market Structure variant, with exact correspondence to the pre-registered `grid.json`.

## Files created

- `researchos/quant_engine/technical/market_structure_definition.py`
- `tests/unit/test_market_structure_definition.py`
- `docs/research/market_structure/PHASE2_REPORT.md`

## Implementation

`StructureDefinition` is a frozen, slotted dataclass containing:

- swing window;
- break basis (`wick` / `close`);
- consecutive confirmation bars;
- ATR buffer and ATR period;
- fixed V1 CHOCH rule (`opposite_confirmed_swing_break`);
- fixed V1 trend filter (`off`);
- definition schema version.

It derives the same `variant_key` format as the grid and calculates `definition_id` as SHA-256 of canonical, sorted JSON containing the schema version and every behavior-defining field. `to_dict()` returns a fresh JSON-compatible mapping. `from_mapping()` rejects missing/unknown fields and declared-key drift.

`definitions_from_grid_payload()` validates the declared count, all 56 unique keys and IDs, every declared axis, and the complete Cartesian product. It rejects axis metadata drift, missing combinations, duplicate values, and unsupported V1 rules.

No market data is read by this module. It does not detect swings, create signals, calculate P&L, or execute orders.

## Verification

```text
py -3 -m pytest -q tests/unit/test_market_structure_definition.py
9 passed in 0.71s

py -3 -m ruff check researchos/quant_engine/technical/market_structure_definition.py tests/unit/test_market_structure_definition.py
All checks passed!

grid materialization
 definitions=56
 first_key=sw02_wick_c1_atr0000
 first_definition_id=b95cd2fc4b1cc262d4705e4453a5b0ef3d335f6d260a1399dd4b9930142e5619
 last_key=sw10_close_c2_atr0500
 unique_ids=56

git diff --check
DIFF_CHECK_EXIT=0
```

## Scope and limitations

- The definition schema is implemented in its own module and is not yet re-exported from `researchos.quant_engine.technical`; public integration will be done with the detector in Phase 3.
- The current uncommitted detector implementation was not modified by Phase 2.
- No market-data variant was run. The dataset and cost/OOS blockers in Phase 1 remain in force.
- No backtest engine, execution layer, cost configuration, or live-trading component was changed.

**Decision:** Phase 2 passes. Phase 3 may proceed using synthetic OHLC fixtures only; timestamps/gap handling and ambiguous-bar semantics must be made consistent with the frozen SPEC before any future market-data use.
