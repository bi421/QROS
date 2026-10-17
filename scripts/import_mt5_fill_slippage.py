"""Import MT5 demo fill + request-time quote logs; this script never submits orders."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "timestamp", "symbol", "order_type", "side", "fill_price", "volume", "deal_id", "quote_bid", "quote_ask"
}
ORDER_TYPES = {"market_entry", "tp_limit", "sl_stop", "market_exit"}
SIDES = {"BUY", "SELL"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_slippage_benchmarks(frame: pl.DataFrame) -> pl.DataFrame:
    """Add executable benchmark and signed adverse slippage; never infer missing trigger prices."""
    required = REQUIRED
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"MT5_FILL_COLUMNS_MISSING:{sorted(missing)}")
    frame = frame.with_columns(
        pl.col("symbol").cast(pl.String).str.to_uppercase(),
        pl.col("order_type").cast(pl.String).str.to_lowercase(),
        pl.col("side").cast(pl.String).str.to_uppercase(),
        *[pl.col(name).cast(pl.Float64, strict=True) for name in ("fill_price", "volume", "quote_bid", "quote_ask")],
    )
    if "requested_price" in frame.columns:
        frame = frame.with_columns(pl.col("requested_price").cast(pl.Float64, strict=True))
        trigger = pl.col("requested_price")
    else:
        trigger = pl.lit(None, dtype=pl.Float64)
    is_market = pl.col("order_type").is_in(["market_entry", "market_exit"])
    benchmark = pl.when(is_market & (pl.col("side") == "BUY")).then(pl.col("quote_ask")).when(
        is_market & (pl.col("side") == "SELL")
    ).then(pl.col("quote_bid")).otherwise(trigger)
    frame = frame.with_columns(benchmark.alias("benchmark_price"))
    invalid = frame.filter(
        ~pl.col("order_type").is_in(sorted(ORDER_TYPES))
        | ~pl.col("side").is_in(sorted(SIDES))
        | (pl.col("fill_price") <= 0)
        | (pl.col("volume") <= 0)
        | (pl.col("quote_bid") <= 0)
        | (pl.col("quote_ask") <= 0)
        | (pl.col("quote_ask") < pl.col("quote_bid"))
        | pl.col("deal_id").is_null()
        | pl.col("benchmark_price").is_null()
        | (pl.col("benchmark_price") <= 0)
    )
    if invalid.height:
        raise ValueError(f"MT5_FILL_ROWS_INVALID_OR_MISSING_BENCHMARK:{invalid.height}")
    return frame.with_columns(
        pl.when(pl.col("side") == "BUY").then(pl.col("fill_price") - pl.col("benchmark_price"))
        .otherwise(pl.col("benchmark_price") - pl.col("fill_price")).alias("adverse_slippage_price_units"),
        (pl.col("fill_price") - pl.col("benchmark_price")).alias("signed_fill_minus_benchmark"),
    )


def summarize(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"n": 0, "status": "NO_OBSERVATIONS"}
    return {
        "n": int(len(values)),
        "mean_price_units": float(values.mean()),
        "median_price_units": float(np.median(values)),
        "p90_price_units": float(np.quantile(values, 0.90)),
        "p95_price_units": float(np.quantile(values, 0.95)),
        "p99_price_units": float(np.quantile(values, 0.99)),
        "fraction_adverse": float(np.mean(values > 0)),
        "fraction_price_improved": float(np.mean(values < 0)),
        "status": "PRELIMINARY_MEASURED" if len(values) >= 100 else "INSUFFICIENT_SAMPLE",
    }


def run(source: Path, output_prefix: str) -> dict:
    if not source.is_file():
        raise FileNotFoundError(
            f"MT5 fill log not found: {source}. Export the demo order/deal log plus request-time bid/ask snapshots first."
        )
    frame = pl.read_csv(source, try_parse_dates=True, infer_schema_length=10000)
    frame = apply_slippage_benchmarks(frame).with_columns(pl.lit(sha256(source)).alias("source_sha256"))
    by_symbol = {}
    for symbol in sorted(frame["symbol"].unique().to_list()):
        sym = frame.filter(pl.col("symbol") == symbol)
        by_symbol[symbol] = {}
        for order_type in sorted(ORDER_TYPES):
            subset = sym.filter(pl.col("order_type") == order_type)
            values = subset["adverse_slippage_price_units"].to_numpy()
            by_symbol[symbol][order_type] = summarize(values)
    calibration_verified = bool(by_symbol) and all(
        by_symbol[symbol][order_type].get("n", 0) >= 100
        for symbol in by_symbol for order_type in ORDER_TYPES
    )
    parquet_path = ROOT / "artifacts" / f"{output_prefix}.parquet"
    json_path = ROOT / "artifacts" / f"{output_prefix}.json"
    hash_path = ROOT / "artifacts" / f"{output_prefix}.sha256"
    frame.write_parquet(parquet_path, compression="zstd")
    report = {
        "schema_version": "qros-mt5-fill-slippage-observations.v1",
        "input_path": str(source),
        "input_sha256": sha256(source),
        "rows": frame.height,
        "by_symbol_and_order_type": by_symbol,
        "minimum_per_order_type_for_preliminary_calibration": 100,
        "calibration_sample_complete": calibration_verified,
        "costs_verified": False,
        "costs_verified_reason": "Observed fills are only preliminary until quote/deal reconciliation, representative sessions, and commission schedule are independently verified.",
        "outputs": {
            "parquet": str(parquet_path.relative_to(ROOT)),
            "json": str(json_path.relative_to(ROOT)),
        },
        "execution_authorized": False,
    }
    json_path.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    hash_path.write_text(
        f"{sha256(source)}  {source.name}\n{sha256(parquet_path)}  {parquet_path.name}\n{sha256(json_path)}  {json_path.name}\n",
        encoding="ascii",
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/execution_logs/mt5_demo_fills.csv")
    parser.add_argument("--output-prefix", default="qros_mt5_demo_slippage_observations")
    args = parser.parse_args()
    run(args.input, args.output_prefix)
