"""Run QROS's vectorized, fail-closed XAUUSD parameter audit."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from researchos.orchestration.vectorized_backtest import (
    EngineConfig,
    load_ohlcv_csv,
    run_grid,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohlcv", default=r"C:\Users\User\Documents\XAUUSDM15.csv")
    parser.add_argument(
        "--news", default=None, help="Optional news CSV with timestamp/time/datetime/date column"
    )
    parser.add_argument("--output", default="artifacts/vectorized_xauusd_backtest.json")
    parser.add_argument(
        "--quick", action="store_true", help="Small smoke grid; not suitable for edge claims"
    )
    parser.add_argument("--base-spread-price", type=float, default=None)
    parser.add_argument("--alpha-cost-price", type=float, default=None)
    parser.add_argument("--commission-roundtrip-price", type=float, default=None)
    parser.add_argument(
        "--cost-model-verified",
        action="store_true",
        help="Only after independently verifying target broker/account costs",
    )
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument(
        "--bootstrap-block-trading-days",
        type=int,
        default=20,
        help="Circular bootstrap block length in observed trading days",
    )
    args = parser.parse_args()
    if args.bootstrap_replicates < 100 or args.bootstrap_block_trading_days < 2:
        parser.error("bootstrap replicates >=100 and block length >=2 required")
    config = EngineConfig(
        lookbacks=(4, 8) if args.quick else (4, 8, 16),
        z_thresholds=(1.0,) if args.quick else (0.5, 1.0, 1.5, 2.0),
        take_profit_atr=(1.0,) if args.quick else (1.0, 1.5, 2.0),
        stop_loss_atr=(1.0,) if args.quick else (0.75, 1.0, 1.5),
        horizons=(8,) if args.quick else (8, 16, 32),
        news_buffers_bars=(0,) if args.quick else (0, 1, 2),
        bootstrap_replicates=args.bootstrap_replicates,
        bootstrap_block_trading_days=args.bootstrap_block_trading_days,
        base_spread_price=args.base_spread_price,
        cost_alpha_price=args.alpha_cost_price,
        commission_roundtrip_price=args.commission_roundtrip_price,
        cost_model_verified=args.cost_model_verified,
    )
    started = time.perf_counter()
    data = load_ohlcv_csv(args.ohlcv)
    loaded = time.perf_counter()
    report = run_grid(data, config, args.news)
    finished = time.perf_counter()
    report["performance"] = {
        "load_seconds": round(loaded - started, 6),
        "evaluation_seconds": round(finished - loaded, 6),
        "total_seconds": round(finished - started, 6),
    }
    report["source"] = {
        "path": str(Path(args.ohlcv).resolve()),
        "first_timestamp": str(data["timestamp"][0]),
        "last_timestamp": str(data["timestamp"][-1]),
        "news_path": str(Path(args.news).resolve()) if args.news else None,
        "news_filter_status": "APPLIED" if args.news else "NOT_CONFIGURED",
    }
    write_report(report, args.output)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "status",
                    "rows",
                    "candidate_count",
                    "cost_model",
                    "fdr",
                    "bootstrap",
                    "paired_comparison_summary",
                    "paired_comparison_fdr",
                    "performance",
                    "source",
                )
            },
            indent=2,
            default=str,
        )
    )
    print(f"REPORT={Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
