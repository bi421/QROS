# XAUUSD additive research integration — Phase 0 audit

## Non-negotiable compatibility boundary

This work adds a new orchestration contract under
`researchos/orchestration/xauusd_research.py`. It does not edit, replace, or
change the behavior of existing technical, macro, market-memory, quant,
decision, labeling, API, queue, worker, or execution modules.

The orchestrator receives existing modules through injected adapters. An
adapter is not considered connected merely because its interface exists.

## Scope

- Instrument: XAUUSD only.
- Decision clock: closed M15 event.
- Context timeframes: M30, H1, H4, D1.
- Label target: TAKE_PROFIT / STOP_LOSS / TIMEOUT.
- Entry assumption: next M15 bar open.
- Initial label defaults: ATR(14), TP=1.5 ATR, SL=1.0 ATR, maximum 16 M15 bars.
- Ambiguous same-bar barrier touches: exclude by default.
- The collection layer emits no probability and never executes an order.

The label defaults are testable research parameters, not claims of profitability.
The current adapter contract intentionally does not implement OHLC labeling or
model calibration yet.

## Source-level audit snapshot

| Area | Existing source | Audit status | Integration boundary |
|---|---|---|---|
| Technical indicators | `researchos/quant_engine/technical/engine.py` | IMPLEMENTED; runtime adapter not proven by this change | Wrap existing outputs; do not alter calculations |
| Decision pipeline | `researchos/decision_engine/pipeline.py` | IMPLEMENTED; its output is not a TP/SL/TIMEOUT distribution | Keep existing directional score/probability semantics unchanged |
| Evidence collection | `researchos/decision_engine/evidence.py` | IMPLEMENTED; source collection does not prove all domain modules are connected | Convert/attach provenance in an adapter |
| Macro analysis | `researchos/macro/engine.py` | IMPLEMENTED for its existing scope; live freshness/provider coverage unproven | Preserve source timestamp and driver provenance |
| Market Memory | `researchos/market_memory/integration.py` | OPTIONAL adapters; defaults to standalone when unconfigured | Adapter must report NOT_CONFIGURED rather than invent evidence |
| Order book | `researchos/data_engine/orderbook.py` | Data objects/calculations exist; live feed is an external dependency | Declare provider, venue and timestamp; do not represent as global spot FX depth |
| Existing triple-barrier label | `researchos/quant_engine/machine_learning/labels.py` | IMPLEMENTED close-only label | Leave unchanged; add an OHLC-aware labeler in a later additive module |
| Calibrated TP/SL/TIMEOUT model | New fusion contract | MISSING / NOT IMPLEMENTED | No numeric probability until training, temporal validation and calibration are proven |

## Phase 0 completion checklist

- [x] Add isolated request/evidence/engine-result contracts.
- [x] Enforce XAUUSD-only and M15 decision-clock boundaries.
- [x] Enforce timezone-aware, as-of evidence and reject future evidence.
- [x] Record required/optional engine failures and fail closed for missing required engines.
- [x] Keep probability unset and execution disabled.
- [ ] Implement concrete adapters for each audited existing engine.
- [ ] Implement OHLC-aware TP/SL/TIMEOUT labels and ambiguous-bar tests.
- [ ] Connect the adapter registry to the existing research-run lifecycle.
- [ ] Run repository CI and fix any failures on this branch.
- [ ] Prove end-to-end reproducibility on a pinned XAUUSD dataset.

## Interpretation

A passing unit suite for these new contracts proves only the additive contract
behavior. It does not prove that all existing engines are wired together, that
historical labels are correct for real data, or that any outcome model is
calibrated or profitable.
