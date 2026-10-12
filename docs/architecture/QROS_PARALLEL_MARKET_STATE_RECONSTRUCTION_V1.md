# QROS Parallel Market State Reconstruction V1

## Scope
Additive XAUUSD research component. It extracts source-specific features concurrently and records data freshness. It does not replace existing QROS modules, place orders, infer institutional intent, or emit uncalibrated probabilities.

## Normalized event contracts
- Broker quote: Quote with event and ingest timestamps, symbol, bid/ask and optional top sizes.
- Exchange/futures L2: BookSnapshot with event and ingest timestamps, symbol and sorted bid/ask levels.
- Trade prints: TradePrint with timestamp, price, size and aggressor side (-1, 0, +1).
- Macro: MacroPoint for DXY/VXY.
All times are UTC epoch nanoseconds. Real adapters must document provider, venue, symbol mapping, units, sequence semantics and licensing.

## Features
Event age, ingest age, transport delay, clock-skew suspicion; quote spread and top-size imbalance; multi-level depth imbalance; signed trade-volume imbalance; DXY/VXY latest value and relative change. Bounded ThreadPoolExecutor fan-out runs four independent kernels.

## Fail-closed behavior
Invalid timestamps, prices, sizes, symbols and crossed books are rejected. Future or stale observations are marked stale. Missing providers remain NOT_CONFIGURED; no data is fabricated. READY_FOR_FUSION requires every source group to be present and fresh.

## Not yet connected
This commit provides normalized input contracts, not live connections. Broker, CME/COMEX, DXY and VXY provider adapters, authentication, reconnect/sequence-gap handling, futures roll mapping, event replay, C++20/nanobind zero-copy integration and out-of-sample probability calibration remain separate work. Futures depth is not global OTC XAUUSD depth.

## Verification boundary
Synthetic unit tests verify contract behavior only. They do not prove live-feed access, production throughput, forecast edge or calibrated probabilities.
