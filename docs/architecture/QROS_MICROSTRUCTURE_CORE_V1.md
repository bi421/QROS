# QROS Microstructure Core: Production Architecture V1

## Scope and non-negotiable boundaries

This is an additive microstructure layer for the existing QROS repository, not a replacement for its quant engine, SaaS orchestration, evidence contracts, or frozen research runners. It does not alter existing engine mathematics and it does not place or execute orders.

QROS can measure observed order-flow pressure and price/volume liquidity proxies. It must not label these measurements as proof of institutional intent: XAUUSD is commonly traded OTC, feed depth can be broker-specific, and stop clusters are inferred zones unless the data provider exposes actual orders (usually it does not).

## Existing codebase: reuse rather than duplicate

- C++20 core and nanobind build: `researchos/engines/quant/`
- Existing order-book representation: `include/quant/market/order_book.h`
- Existing deterministic historical event replay: `include/quant/backtest/event_replay.h`
- Existing Python tick/order-book contracts: `researchos/data_engine/tick.py`, `orderbook.py`
- Existing ingestion, validation, repository and dataset boundaries: `researchos/data_engine/`
- Existing XAUUSD multi-engine research routing: `researchos/orchestration/xauusd_research.py`
- New isolated kernel interface: `include/quant/market/microstructure.h`
- New implementation: `src/market/microstructure.cpp`
- New nanobind module: `bindings/microstructure.cpp`, imported as `qros_microstructure`
- New deterministic C++ tests: `tests/test_microstructure.cpp`

Keep data contracts and replay semantics in the existing layers. Do not create a second OHLC/order-book abstraction or change the canonical engine to call an experimental kernel until parity and exact-SHA CI evidence exist.

## Target project layout

```text
researchos/
  data_engine/
    contracts.py                 # canonical validated event contracts
    tick.py / orderbook.py       # existing domain objects
    repository.py                # existing persistence boundary
    streaming/                   # future provider-specific adapters
      event_normalizer.py
      sequence_guard.py
      watermark.py
  engines/quant/
    include/quant/market/
      microstructure.h           # dual timestamps and kernel API
      order_book.h               # existing book model
    src/market/
      microstructure.cpp         # deterministic C++ kernels
    bindings/
      microstructure.cpp         # qros_microstructure; ndarray contract
    tests/
      test_microstructure.cpp
    python/cpp_quant_engine/
      # existing stable backend; new extension remains separately versioned
  orchestration/
    xauusd_research.py            # existing multi-engine orchestration
    latency.py                    # separate freshness/compute gate
  simulation/
    event_driven_replay.py        # future Python orchestration wrapper
    execution_cost_model.py       # future deterministic slippage/queue model
  storage/
    parquet_writer.py             # future immutable partition writer
    duckdb_reader.py              # future point-in-time research queries
docs/architecture/
  QROS_MICROSTRUCTURE_CORE_V1.md
```

The `streaming/`, `simulation/`, and `storage/` entries above are target boundaries, not claims that those modules already exist. DuckDB should be introduced as an explicit optional dependency only when the storage adapter is implemented and tested; Parquet can be written through the selected Arrow-compatible stack. Do not silently make it a required dependency in the existing SaaS runtime.

## Canonical event contract

Every feed event must retain at least:

- `symbol`, `venue/provider`, `source_id`, `sequence`
- `event_time_ns`: source/exchange event timestamp, UTC epoch nanoseconds
- `ingest_time_ns`: local receipt timestamp, UTC epoch nanoseconds
- event kind (trade, quote, book snapshot, book delta), side/flags
- price, size, bid/ask or depth payload as applicable
- feed/session identity, schema version, and source payload hash

Use event time for market chronology and point-in-time joins; use ingest time to measure when QROS could have known the information. Preserve both in all storage and research outputs. A negative `ingest_time - event_time` is a clock-skew observation, not a reason to rewrite either timestamp. Monotonic clocks measure local elapsed durations only; they are not persisted as UTC timestamps.

A feed without trustworthy event timestamps, sequence semantics, or source identity must be marked lower-quality or rejected according to policy. Duplicate sequence, gaps, out-of-order events, reconnect snapshots, and late arrivals require explicit state transitions, not silent sorting or backfilling.

## C++20 and nanobind contract

The new `qros_microstructure` module exposes:

- `order_flow_imbalance(bid_price, bid_size, ask_price, ask_size)`
- `detect_liquidity_sweeps(high, low, close, pool_price)`
- `volume_profile_summary(prices, volumes, tick_size, value_area_fraction=0.70)`

Inputs are one-dimensional, C-contiguous NumPy float64 arrays. Nanobind borrows the input buffers rather than converting them into Python lists or copying them. The GIL is released during the C++ calculation. Returned arrays own their output storage; output allocation is not zero-copy and should not be described as such.

The initial kernels are deterministic and fail closed on malformed shapes, invalid prices/sizes, crossed books, non-finite values, and invalid volume-profile parameters. The sweep detector only tests a supplied pool level; it does not discover stop orders. The volume profile is a binned profile derived from the supplied price/volume observations; its validity depends on feed volume semantics and tick-size configuration.

### Kernel semantics

- OFI is a Cont-style top-of-book snapshot delta. The first sample returns zero because no previous book state exists. It is not full-depth queue imbalance.
- A sweep above a supplied pool is `high > pool && close < pool`; below is `low < pool && close > pool`. Strict comparisons are intentional.
- Volume profile POC ties choose the lower-price bin. Value-area expansion chooses the side with more adjacent volume and resolves ties to the lower-price side.
- These outputs are evidence features, not standalone entry signals or calibrated probabilities.

## Data pipeline: Polars + DuckDB/Parquet

1. Normalize each provider event while preserving original source timestamps and sequence.
2. Validate event schema, symbol, finite numeric values, sequence and book invariants.
3. Measure ingest delay and local processing duration separately.
4. Apply a source-specific watermark/late-event policy; never allow future rows into a historical decision.
5. Persist immutable raw events and versioned normalized events to Parquet, partitioned by symbol, provider, session/date and event kind as operationally appropriate.
6. Query point-in-time snapshots with DuckDB; use Polars for typed vector transformations and batch feature preparation.
7. Hash input partitions, configuration and output evidence so the same immutable input/version produces reproducible output.

A historical decision at cutoff `T` may only consume records whose event-time and availability rules satisfy that decision's information set. In live-faithful simulation, a record received after the decision's simulated ingest cutoff is unavailable even if its event timestamp is earlier. Late-event corrections should create a new dataset version and rerun, not mutate old evidence.

## Event-driven backtest and latency model

The existing deterministic replay engine is candle-oriented. A tick/book simulator must be a separate mode that consumes events incrementally in deterministic order and does not preload future observations into the decision API.

Each simulated decision/execution should model at least:

- source event time and simulated local ingest time;
- configurable feed/network delay and compute budget;
- decision time and order-arrival time (simulation only);
- spread, slippage, market impact assumptions, queue ahead/depth, partial fills, and timeout/cancel rules;
- the exact data available at each point and the model/configuration version.

Use seeded randomness only where stochastic fill models are needed, and record the seed. Do not claim realistic queue position from L2 snapshots alone; true queue position usually requires order-level feed data. Separate calibration from evaluation and use walk-forward / purged temporal validation. A backtest with no depth or provider latency evidence must report those assumptions as unavailable, not silently assume zero cost.

## UI boundary

The frontend may request and display already-computed historical evidence, spatial liquidity zones, OFI series, freshness/latency telemetry, and provenance. It must not calculate signals, infer trade intent, run risk gates, or make decisions. WebSocket messages should carry versioned, timestamped backend results; the frontend is a presentation layer only.

## Latency and observability SLOs

Measure independent histograms for ingest delay, queue wait, per-kernel runtime, evidence fusion, persistence and total run time. Report p50/p95/p99/max, sample count, clock-quality status and dropped/late event counts. A compute optimization is accepted only when benchmarked on pinned input data and does not weaken validation or determinism.

Do not set production thresholds from arbitrary example numbers. Derive per-source and per-event-class policies from observed telemetry. When required source freshness, sequence integrity, or clock quality cannot be proven, mark the research result rejected/insufficient.

## Status boundaries

- IMPLEMENTED IN THIS CHANGE: C++20 kernel contracts and implementations, nanobind extension target, borrowed contiguous NumPy input contract, deterministic kernel unit tests.
- NOT YET PROVEN: exact-head CI/build success, compiled-extension Python tests, measured performance/zero-copy benchmark, production data-provider compatibility.
- NOT YET IMPLEMENTED: provider streaming adapters, immutable Parquet writer and DuckDB query layer, point-in-time watermark integration, tick-level execution simulator, frontend/API telemetry contract.
- EXTERNAL DEPENDENCIES: actual XAUUSD feed coverage, exchange/provider event timestamp quality, reliable depth/queue data, and real network latency telemetry.
