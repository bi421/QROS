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
The additive labeler now exists at `researchos/quant_engine/machine_learning/ohlc_triple_barrier.py`. It is not yet connected to a dataset loader or research-run lifecycle. Model calibration remains unimplemented.

## Source-level audit snapshot

| Area | Existing source | Audit status | Integration boundary |
|---|---|---|---|
| Technical indicators | `researchos/quant_engine/technical/engine.py` | Existing engine + additive adapter implemented in this adapter change; dataset replay unproven | Preserve calculations; validate adapter against pinned real data |
| Decision pipeline | `researchos/decision_engine/pipeline.py` | IMPLEMENTED; its output is not a TP/SL/TIMEOUT distribution | Keep existing directional score/probability semantics unchanged |
| Evidence collection | `researchos/decision_engine/evidence.py` | IMPLEMENTED; source collection does not prove all domain modules are connected | Convert/attach provenance in an adapter |
| Macro analysis | `researchos/macro/engine.py` | IMPLEMENTED for its existing scope; live freshness/provider coverage unproven | Preserve source timestamp and driver provenance |
| Market Memory | `researchos/market_memory/integration.py` | OPTIONAL adapters; defaults to standalone when unconfigured | Adapter must report NOT_CONFIGURED rather than invent evidence |
| Order book | `researchos/data_engine/orderbook.py` | Data objects/calculations exist; live feed is an external dependency | Declare provider, venue and timestamp; do not represent as global spot FX depth |
| Existing triple-barrier label | `researchos/quant_engine/machine_learning/labels.py` | Existing close-only label retained; OHLC-aware labeler added in PR #725 | Keep both APIs separate; prove OHLC labels on pinned data |
| Calibrated TP/SL/TIMEOUT model | New fusion contract | MISSING / NOT IMPLEMENTED | No numeric probability until training, temporal validation and calibration are proven |

## Phase 0 completion checklist

- [x] Add isolated request/evidence/engine-result contracts.
- [x] Enforce XAUUSD-only and M15 decision-clock boundaries.
- [x] Enforce timezone-aware, as-of evidence and reject future evidence.
- [x] Record required/optional engine failures and fail closed for missing required engines.
- [x] Keep probability unset and execution disabled.
- [x] Add concrete adapters for technical indicators and quant geometry/statistics.
- [x] Add a provenance- and freshness-guarded macro evidence adapter contract.
- [ ] Connect a real macro provider and Market Memory; live provider coverage remains unproven.
- [x] Implement standalone OHLC-aware TP/SL/TIMEOUT labels and ambiguous-bar unit tests.
- [ ] Prove labeler results against a pinned, cleaned XAUUSD OHLC dataset.
- [ ] Connect the adapter registry to the existing research-run lifecycle and prove API/worker integration.
- [ ] Run repository CI and fix any failures on this branch.
- [ ] Prove end-to-end reproducibility on a pinned XAUUSD dataset.

## Interpretation

A passing unit suite for these new contracts proves only the additive contract
behavior. It does not prove that all existing engines are wired together, that
historical labels are correct for real data, or that any outcome model is
calibrated or profitable.


## OHLC outcome labeler contract (implemented, not yet dataset-proven)

The additive labeler accepts a chronologically ordered sequence of completed
OHLC bars plus direction and ATR values aligned to each decision bar. The
direction and ATR at index i must be available at that decision time; entry
uses the next bar's open, never the decision bar's close. The entry bar counts
as holding bar 1. A full forward holding window is required before emitting
TAKE_PROFIT, STOP_LOSS, or TIMEOUT.

- Long TP/SL: entry + TP_ATR × ATR; entry − SL_ATR × ATR.
- Short TP/SL: entry − TP_ATR × ATR; entry + SL_ATR × ATR.
- First unambiguous barrier touched wins.
- If TP and SL are both inside the same OHLC candle, default EXCLUDE emits no
  label; CONSERVATIVE_SL_FIRST explicitly emits STOP_LOSS.
- Missing/invalid ATR, neutral direction, absent next-bar entry, and incomplete
  horizon are left unlabeled with a reason code.
- OHLC prices must be finite, positive, and internally consistent.

Before dataset-level use, callers must provide chronologically sorted bars,
resolve duplicate/out-of-order timestamps (including repeated-hour/DST cases),
and ensure ATR and direction arrays are causally aligned. This labeler does not
infer timestamps, repair data, calculate ATR, choose signal direction, or claim
that labels are profitable. No calibrated probabilities are emitted.


## Concrete technical/QuantMath adapter phase (merged; dataset replay unproven)

The next additive adapter module is
`researchos/orchestration/xauusd_engine_adapters.py`.

- `XAUUSDMarketSnapshot` requires timestamp-aligned OHLCV windows for M15,
  M30, H1, H4, and D1, with a pinned dataset version and timezone-aware,
  strictly increasing bar-close timestamps.
- `XAUUSDTechnicalEvidenceAdapter` calls the existing technical engine for
  EMA(20), EMA(50), RSI(14), ATR(14), MACD(12,26,9), and SuperTrend(10,3)
  at the last closed bar in each timeframe. It emits raw indicator values and
  explicitly versioned heuristic directions/strengths; these are not calibrated.
- `XAUUSDQuantMathEvidenceAdapter` calls the existing QuantMathEngine on the
  closed M15 close series and emits geometry/statistics evidence with the
  engine's deterministic result hash.
- Both adapters reject dataset-version mismatches and do not use bars closing
  after the requested decision timestamp. The window is bounded to 512 bars
  per timeframe.
- The orchestrator can collect these two engine outputs together, but macro
  driver inputs, Market Memory provider wiring, order-book feeds, a complete
  research-run lifecycle, outcome calibration, and end-to-end dataset replay
  remain separate, unproven work.


## Macro evidence adapter phase (implemented contract; provider wiring unproven)

The additive module `researchos/orchestration/xauusd_macro_adapter.py`
translates already-assessed macro driver observations into the shared evidence
contract. It does not fetch data, call the existing MacroAnalysisEngine, or
change its scoring logic.

- All ten driver identifiers from `researchos/macro/engine.py` are required
  before the adapter publishes evidence; missing drivers produce an
  INSUFFICIENT result with no partial evidence.
- Each observation carries an explicit gold-impact direction, score,
  confidence, timestamp, source references, and provider-defined maximum age.
- Future observations, stale observations, invalid scores/confidence, missing
  provenance, and duplicate driver names are rejected fail-closed.
- The provider ID and source references are preserved in every evidence record.
- The observation timeframe is the M15 decision context; the original
  observation timestamp remains the source's actual `as_of` time.

This is a typed adapter boundary only. A live macro source, transformation
from the existing engine's persisted assessment objects, Market Memory
integration, and a pinned historical replay are not yet implemented or proven.
No calibrated outcome probabilities are produced.


## Composite research input router (contract implemented; data providers unproven)

The additive module `researchos/orchestration/xauusd_research_inputs.py`
routes separate market and macro snapshots into the existing orchestrator:
technical and QuantMath adapters receive the market OHLCV snapshot; the macro
adapter receives the pre-assessed macro snapshot. This resolves the input-shape
mismatch without changing any existing calculation code.

- The default collector declares technical, quant_math, and macro as required.
- Missing snapshots are returned as NOT_CONFIGURED with stable reason codes;
  the orchestrator marks the run INSUFFICIENT_EVIDENCE rather than inventing data.
- Callers may explicitly make an engine optional, but its status and reason are
  retained in the result.
- The result continues to set `probabilities: null` and
  `execution_enabled: false`.

This wires adapter interfaces together only. It does not supply a live market
feed, convert persisted MacroAnalysisEngine objects into macro snapshots, add
Market Memory, or connect the collector to the API/worker lifecycle. Those
remain separate dependencies and require dataset-backed integration tests.
