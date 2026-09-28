"""Phase 5.2 entrypoint — macro-augmented XAUUSD predictive-value experiment."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from researchos.data_engine.loader import CsvLoader
from researchos.experiments.phase52 import FEATURE_SET_NAMES, Phase52Config, run_phase52, run_phase52_comparison
from researchos.experiments.phase52.timestamp_adapter import normalize_epoch_timestamp_csv


def _load_candles(csv_path: str, fmt: str, symbol: str, timeframe: str):
    loader = CsvLoader()
    if fmt == "mt5":
        candles = loader.load_mt5_candles(csv_path, symbol=symbol, timeframe=timeframe)
    elif fmt == "tradingview":
        candles = loader.load_tradingview_candles(csv_path, symbol=symbol, timeframe=timeframe)
    else:
        candles = loader.load_candles_auto(csv_path, symbol=symbol, timeframe=timeframe)
    return ([c.close for c in candles], [c.high for c in candles], [c.low for c in candles], [c.volume for c in candles], [c.timestamp for c in candles])


def _load_macro_series(csv_path: str, fmt: str, symbol: str, timeframe: str):
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


def _calendar_day_key(value: object) -> str:
    """Return the canonical UTC calendar day for a loaded timestamp."""
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _build_common_observation_sample(close, high, low, volume, timestamps, macro, macro_timestamps, required_symbols):
    """Build the governed common sample by UTC calendar day without repair.

    Phase 5.2 daily alignment is defined by exact common UTC calendar days, not
    raw source timestamp equality. Source observations retain their own source
    timestamps during loading; the aligned dataset uses the XAUUSD daily
    timestamp as the canonical observation timestamp.
    """
    price_days = [_calendar_day_key(ts) for ts in timestamps]
    if len(set(price_days)) != len(price_days):
        raise ValueError("XAUUSD: duplicate calendar days")

    macro_maps = {}
    for symbol in required_symbols:
        values = macro.get(symbol)
        factor_ts = macro_timestamps.get(symbol)
        if values is None or factor_ts is None:
            raise ValueError(f"{symbol}: missing macro series")
        if len(values) != len(factor_ts):
            raise ValueError(f"{symbol}: value/timestamp length mismatch")
        factor_days = [_calendar_day_key(ts) for ts in factor_ts]
        if len(set(factor_days)) != len(factor_days):
            raise ValueError(f"{symbol}: duplicate calendar days")
        macro_maps[symbol] = {day: i for i, day in enumerate(factor_days)}

    selected_price_indices = []
    selected_macro_indices = {s: [] for s in required_symbols}
    common_timestamps = []
    for i, day in enumerate(price_days):
        indices = []
        for symbol in required_symbols:
            index = macro_maps[symbol].get(day)
            if index is None:
                break
            indices.append(index)
        else:
            selected_price_indices.append(i)
            common_timestamps.append(timestamps[i])
            for symbol, index in zip(required_symbols, indices):
                selected_macro_indices[symbol].append(index)
    if not common_timestamps:
        raise ValueError("NO COMMON OBSERVATIONS ACROSS XAUUSD AND REQUIRED MACRO SERIES")
    filtered_macro_timestamps = {symbol: common_timestamps[:] for symbol in required_symbols}
    return (
        [close[i] for i in selected_price_indices],
        [high[i] for i in selected_price_indices],
        [low[i] for i in selected_price_indices],
        [volume[i] for i in selected_price_indices],
        common_timestamps,
        {symbol: [macro[symbol][i] for i in selected_macro_indices[symbol]] for symbol in required_symbols},
        filtered_macro_timestamps,
    )


def _print_result(result):
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