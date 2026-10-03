"""Legacy C++ binding probe.

This is a manual diagnostic, not a CI test. The supported C++ integration
surface is researchos/engines/quant/tests.
"""

from __future__ import annotations


def main() -> int:
    import cpp_quant_engine as cqe

    backend = cqe.default_backend()
    request = {
        "symbol": "BTC",
        "timeframe": "H1",
        "candles": [{
            "timestamp": "2024-01-01T00:00:00",
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100.5,
            "volume": 1000,
            "timeframe": "H1",
        }],
    }
    result = backend.backtest_run(request)
    print("meta", backend.meta())
    print("backtest", result.final_equity, result.total_bars, result.num_trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
