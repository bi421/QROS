"""Phase 5.2 entrypoint — macro-augmented XAUUSD predictive-value experiment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from researchos.data_engine.loader import CsvLoader
from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config, run_phase52, run_phase52_comparison
from researchos.experiments.phase52.alignment import validate_exact_timestamp_alignment
from researchos.experiments.phase52.timestamp_adapter import normalize_epoch_timestamp_csv


def _load_candles(csv_path: str, fmt: str, symbol: str, timeframe: str) -> tuple[list[float], list[float], list[float], list[float], list[Any]]:
    loader = CsvLoader()
    if fmt == "mt5":
        candles = loader.load_mt5_candles(csv_path, symbol=symbol, timeframe=timeframe)
    elif fmt == "tradingview":
        candles = loader.load_tradingview_candles(csv_path, symbol=symbol, timeframe=timeframe)
    else:
        candles = loader.load_candles_auto(csv_path, symbol=symbol, timeframe=timeframe)
    return ([c.close for c in candles], [c.high for c in candles], [c.low for c in candles], [c.volume for c in candles], [c.timestamp for c in candles])


def _load_macro_series(csv_path: str, fmt: str, symbol: str, timeframe: str) -> tuple[list[float], list[Any]]:
    """Load a macro series without repairing or fabricating observations."""
    loader = CsvLoader()
    if fmt == "mt5":
        candles = loader.load_mt5_candles(csv_path, symbol=symbol, timeframe=timeframe)
    elif fmt in {"tradingview", "auto"}:
        with open(csv_path, encoding="utf-8-sig") as f:
            text = f.read()
        normalized = normalize_epoch_timestamp_csv(text)
        if fmt == "tradingview":
            candles = loader.load_tradingview_candles_from_text(normalized, symbol=symbol, timeframe=timeframe)
        else:
            candles = loader.load_candles_auto_from_text(normalized, symbol=symbol, timeframe=timeframe)
    else:
        candles = loader.load_candles_auto(csv_path, symbol=symbol, timeframe=timeframe)
    return [c.close for c in candles], [c.timestamp for c in candles]


def _build_common_observation_sample(
    close: list[float], high: list[float], low: list[float], volume: list[float],
    timestamps: list[Any], macro: dict[str, list[float]], macro_timestamps: dict[str, list[Any]],
    required_symbols: tuple[str, ...],
) -> tuple[list[float], list[float], list[float], list[float], list[Any], dict[str, list[float]], dict[str, list[Any]]]:
    """Build the explicit common-observation sample without calendar repair."""
    if len({*timestamps}) != len(timestamps):
        raise ValueError("XAUUSD: duplicate timestamps")
    macro_maps = {}
    for symbol in required_symbols:
        values = macro.get(symbol)
        factor_ts = macro_timestamps.get(symbol)
        if values is None or factor_ts is None:
            raise ValueError(f"{symbol}: missing macro series")
        if len(values) != len(factor_ts):
            raise ValueError(f"{symbol}: value/timestamp length mismatch")
        if len({*factor_ts}) != len(factor_ts):
            raise ValueError(f"{symbol}: duplicate timestamps")
        macro_maps[symbol] = {ts: i for i, ts in enumerate(factor_ts)}

    selected_price_indices = []
    selected_macro_indices = {s: [] for s in required_symbols}
    common_timestamps = []
    for i, ts in enumerate(timestamps):
        indices = []
        for symbol in required_symbols:
            index = macro_maps[symbol].get(ts)
            if index is None:
                break
            indices.append(index)
        else:
            selected_price_indices.append(i)
            common_timestamps.append(ts)
            for symbol, index in zip(required_symbols, indices):
                selected_macro_indices[symbol].append(index)
    if not common_timestamps:
        raise ValueError("NO COMMON OBSERVATIONS ACROSS XAUUSD AND REQUIRED MACRO SERIES")
    filtered = (
        [close[i] for i in selected_price_indices],
        [high[i] for i in selected_price_indices],
        [low[i] for i in selected_price_indices],
        [volume[i] for i in selected_price_indices],
        common_timestamps,
        {symbol: [macro[symbol][i] for i in selected_macro_indices[symbol]] for symbol in required_symbols},
        {symbol: common_timestamps[:] for symbol in required_symbols},
    )
    for symbol in required_symbols:
        validate_exact_timestamp_alignment(common_timestamps, filtered[6][symbol], symbol)
    return filtered


def _print_result(result: Any) -> None:
    print(f"{result.metadata.get('feature_set', '(legacy)'):18} | {result.outcome:10} | folds={result.num_folds:3d} | accuracy={result.model.accuracy:.4f} | brier={result.model.brier_score:.4f} | hash={result.reproducibility_hash}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 5.2 macro-augmented XAUUSD experiment")
    parser.add_argument("--csv", default="", help="Path to real XAUUSD CSV (MT5/TradingView)")
    parser.add_argument("--dxy", default="", help="Path to real DXY CSV")
    parser.add_argument("--us10y", default="", help="Path to real US10Y CSV")
    parser.add_argument("--vix", default="", help="Path to real VIX CSV")
    parser.add_argument("--format", default="mt5", choices=["mt5", "tradingview", "auto"])
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--train", type=int, default=1200)
    parser.add_argument("--valid", type=int, default=200)
    parser.add_argument("--step", type=int, default=200)
    parser.add_argument("--neighbors", type=int, default=25)
    parser.add_argument("--feature-set", choices=FEATURE_SET_NAMES, default="ALL")
    parser.add_argument("--spread", default="fixed:0.0")
    parser.add_argument("--slippage", default="fixed:0.0")
    parser.add_argument("--commission", default="fixed:0.0")
    parser.add_argument("--out", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)

    missing_files = [name for name, path in (("XAUUSD csv", args.csv), ("DXY csv", args.dxy), ("US10Y csv", args.us10y), ("VIX csv", args.vix)) if not path or not os.path.exists(path)]
    if missing_files:
        print("=" * 60)
        print("OUTCOME: BLOCKED")
        print("REASON:  REAL XAUUSD + MACRO DATA REQUIRED")
        print(f"MISSING FILES: {', '.join(missing_files)}")
        print("=" * 60)
        return 2
    try:
        close, high, low, volume, timestamps = _load_candles(args.csv, args.format, args.symbol, args.timeframe)
        macro, macro_timestamps = {}, {}
        for symbol, path in (("DXY", args.dxy), ("US10Y", args.us10y), ("VIX", args.vix)):
            values, factor_timestamps = _load_macro_series(path, args.format, symbol, args.timeframe)
            macro[symbol], macro_timestamps[symbol] = values, factor_timestamps
        close, high, low, volume, timestamps, macro, macro_timestamps = _build_common_observation_sample(close, high, low, volume, timestamps, macro, macro_timestamps, ("DXY", "US10Y", "VIX"))
    except Exception as e:  # noqa: BLE001
        print(f"BLOCKED — common observation sample construction failed: {e}")
        return 2

    cfg = Phase52Config(symbol=args.symbol, timeframe=args.timeframe, horizon=args.horizon, threshold=args.threshold, train_size=args.train, validation_size=args.valid, step_size=args.step, n_neighbors=args.neighbors, spread_spec=args.spread, slippage_spec=args.slippage, commission_spec=args.commission)
    if args.feature_set == "ALL":
        results = run_phase52_comparison(close, high, low, volume, macro, config=cfg, timestamps=timestamps, macro_timestamps=macro_timestamps)
        print("=" * 100)
        print("PHASE 5.2 FEATURE-SET ISOLATION")
        print("PRICE_ONLY / PRICE + DXY / PRICE + US10Y / PRICE + VIX / PRICE + ALL")
        print("=" * 100)
        for result in results.values():
            _print_result(result)
        print("=" * 100)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in results.items()}, f, indent=2, default=str)
            print(f"Results written to {args.out}")
        return 0 if all(r.outcome != "BLOCKED" for r in results.values()) else 2

    result = run_phase52(close, high, low, volume, macro, cfg, timestamps=timestamps, macro_timestamps=macro_timestamps)
    print("=" * 60)
    print(f"FEATURE SET:         {args.feature_set}")
    print(f"BARS:                {len(close)}")
    print(f"FOLDS:               {result.num_folds}")
    print(f"OUTCOME:             {result.outcome}")
    print(f"REPRODUCIBILITY_HASH:{result.reproducibility_hash}")
    if result.model is not None:
        print(f"MODEL ACCURACY:      {result.model.accuracy:.4f}")
        print(f"MODEL BRIER:         {result.model.brier_score:.4f}")
    if result.cost is not None:
        print(f"NET ACCURACY:        {result.cost.net_accuracy_all:.4f}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        print(f"Result written to {args.out}")
    return 0 if result.outcome != "BLOCKED" else 2


if __name__ == "__main__":
    sys.exit(main())
