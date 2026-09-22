"""
Phase 5.1 entrypoint — run the XAUUSD predictive-value experiment.

Usage:
    python -m researchos.experiments.phase51.scripts.run_phase51_experiment \
        --csv path/to/xauusd_d1.csv --format mt5 --symbol XAUUSD

If no real XAUUSD CSV is supplied, the experiment reports:

    BLOCKED — REAL XAUUSD DATA REQUIRED

This is a data-availability state, NOT a model success/failure verdict.

Real-data prerequisites:
    * XAUUSD (gold) daily candles.
    * >= 2000 bars (>= ~8 years of D1).
    * MT5 or TradingView CSV export with OHLCV columns.
    * Chronologically ordered rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from researchos.data_engine.loader import CsvLoader
from researchos.experiments.phase51 import Phase51Config, run_phase51


def _load_candles(csv_path: str, fmt: str, symbol: str, timeframe: str) -> tuple[list[float], list[float], list[float], list[float], list[Any]]:
    """Load candles from CSV using the verified CsvLoader."""
    loader = CsvLoader()
    if fmt == "mt5":
        candles = loader.load_mt5_candles(csv_path, symbol=symbol, timeframe=timeframe)
    elif fmt == "tradingview":
        candles = loader.load_tradingview_candles(csv_path, symbol=symbol, timeframe=timeframe)
    else:
        candles = loader.load_candles_auto(csv_path, symbol=symbol, timeframe=timeframe)

    close = [c.close for c in candles]
    high = [c.high for c in candles]
    low = [c.low for c in candles]
    volume = [c.volume for c in candles]
    return close, high, low, volume, candles


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5.1 XAUUSD experiment")
    parser.add_argument("--csv", default="", help="Path to real XAUUSD CSV (MT5/TradingView)")
    parser.add_argument("--format", default="mt5", choices=["mt5", "tradingview", "auto"])
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--train", type=int, default=1200)
    parser.add_argument("--valid", type=int, default=200)
    parser.add_argument("--step", type=int, default=200)
    parser.add_argument("--spread", default="fixed:0.0")
    parser.add_argument("--slippage", default="fixed:0.0")
    parser.add_argument("--commission", default="fixed:0.0")
    parser.add_argument("--out", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)

    if not args.csv or not os.path.exists(args.csv):
        result = run_phase51([], [], [], [])
        print("=" * 60)
        print(f"OUTCOME: {result.outcome}")
        print(f"REASON:  {result.validation.reasons[0]}")
        print("=" * 60)
        print("BLOCKED — REAL XAUUSD DATA REQUIRED")
        return 2

    try:
        close, high, low, volume, candles = _load_candles(args.csv, args.format, args.symbol, args.timeframe)
    except Exception as e:  # noqa: BLE001
        print(f"BLOCKED — data load failed: {e}")
        return 2

    cfg = Phase51Config(
        symbol=args.symbol,
        timeframe=args.timeframe,
        horizon=args.horizon,
        threshold=args.threshold,
        train_size=args.train,
        validation_size=args.valid,
        step_size=args.step,
        spread_spec=args.spread,
        slippage_spec=args.slippage,
        commission_spec=args.commission,
    )

    result = run_phase51(close, high, low, volume, cfg)

    print("=" * 60)
    print(f"SYMBOL:     {result.symbol}")
    print(f"TIMEFRAME:  {result.timeframe}")
    print(f"BARS:       {len(close)}")
    print(f"HORIZON:    {result.horizon}")
    print(f"FOLDS:      {result.num_folds}")
    print(f"OUTCOME:    {result.outcome}")
    print(f"REPRODUCIBILITY_HASH: {result.reproducibility_hash}")
    print("=" * 60)

    if result.model is not None:
        print(f"MODEL ACCURACY:  {result.model.accuracy:.4f}")
        if result.baseline is not None:
            print(f"BASELINE ACC:    {result.baseline.accuracy:.4f}")
    if result.cost is not None:
        print(f"NET ACCURACY:    {result.cost.net_accuracy_all:.4f}")
    if result.significance is not None:
        print(f"P-VALUE:         {result.significance.p_value:.4f}")
        print(f"SIGNIFICANT:     {result.significance.significant}")
    print(f"VALIDATION:      {result.validation.outcome}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"Result written to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
