# Sequence-gated XAUUSD market-state evidence pipeline

## Purpose

`researchos/orchestration/sequence_gated_xauusd_evidence.py` composes the
existing sequence guard, market-state reconstruction wrapper, and canonical
XAUUSD market-state evidence adapter. It is additive and does not modify the
feature engine, existing research-run lifecycle, or probability calculations.

## Contract

1. Caller supplies the complete raw `EventClock` stream in ingestion order.
2. Per-source sequence gaps, duplicates, regressions, or invalid sequence
   values block reconstruction and return no evidence.
3. A valid sequence permits the existing reconstruction engine to run.
4. The existing evidence adapter then independently requires all configured
   source groups to be present, fresh, and valid before publishing evidence.
5. Probabilities remain unset and execution remains disabled.

## Evidence status

- **IMPLEMENTED:** deterministic composition and fail-closed unit tests.
- **NOT PROVEN:** source-stream completeness; this remains a caller/integration
  responsibility. The wrapper cannot detect an event omitted before its input.
- **EXTERNAL DEPENDENCY:** real broker quote, futures order book/trade flow,
  DXY, and VXY provider adapters and their live data quality.
- **NOT IMPLEMENTED:** live-feed subscription, production-worker wiring, dataset
  replay integration, calibrated TP/SL/TIMEOUT probabilities, or order execution.

This is a safety/integration contract, not evidence of profitable trading.
