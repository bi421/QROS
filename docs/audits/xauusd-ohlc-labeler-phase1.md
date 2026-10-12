# XAUUSD OHLC triple-barrier labeler — Phase 1

## Scope

The additive module `researchos/orchestration/xauusd_labels.py` labels a signal at a closed M15 event using the next bar open as the assumed entry. The caller supplies the ATR value available at the signal timestamp and a versioned `OutcomeSpec`.

Supported outcomes are `TAKE_PROFIT`, `STOP_LOSS`, and `TIMEOUT`. Incomplete forward windows, absent ATR, absent signals, and ambiguous same-bar TP/SL touches under the default `EXCLUDE` policy return `None` rather than inventing a label.

## Deterministic conventions

- Long: TP is tested against high; SL against low.
- Short: TP is tested against low; SL against high.
- Opening gaps are checked before intrabar extremes and recorded at the observed open.
- If both barriers are touched intrabar, `EXCLUDE` returns no label; `CONSERVATIVE_SL_FIRST` records stop loss.
- Timeout is emitted only after the entire configured holding window is observed, using its final close.
- Bars must have timezone-aware, strictly increasing timestamps and internally valid, finite, positive OHLC values.
- ATR is event-time input and must be finite and positive when present.

## Compatibility and scientific boundary

The existing close-only `triple_barrier` in `researchos/quant_engine/machine_learning/labels.py` is not modified. This new module is not yet wired into the SaaS research-run lifecycle, does not train or calibrate a model, does not produce TP/SL/TIMEOUT probabilities, and does not execute orders. A labeler unit test proves only these deterministic conventions; it does not prove profitability or real-world fill quality.

## Next validation stages

1. Verify these contracts through exact-SHA CI.
2. Wire existing engine adapters and the labeler into an immutable research-run artifact without changing existing engine behavior.
3. Run on a pinned XAUUSD dataset with temporal splits, leakage controls, class counts, and reproducibility hashes.
4. Calibrate outcome probabilities only after those dataset-level gates pass.
