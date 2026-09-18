from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "XAUUSD"
START = datetime(2021, 1, 1, tzinfo=timezone.utc)
END = datetime.now(timezone.utc)
OUT_PATH = Path("data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv")


def main() -> None:
    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}")

    if not mt5.symbol_select(SYMBOL, True):
        mt5.shutdown()
        raise SystemExit(f"symbol_select failed for {SYMBOL}: {mt5.last_error()}")

    rates = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_D1, START, END)
    err = mt5.last_error()
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise SystemExit(f"No data returned. last_error={err}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

    print("ROWS:", len(df))
    print("FIRST:", df["time"].iloc[0])
    print("LAST:", df["time"].iloc[-1])

    if df["time"].iloc[0].year > 2021:
        raise SystemExit(f"BLOCKED: broker history starts at {df['time'].iloc[0]}, " f"not 2021. This is NOT the required dataset - do not proceed.")

    dupes = df["time"].duplicated().sum()
    gaps = df["time"].diff().dt.total_seconds().div(86400)
    big_gaps = (gaps > 4).sum()
    ohlc_invalid = ((df["high"] < df[["open", "close"]].max(axis=1)) | (df["low"] > df[["open", "close"]].min(axis=1)) | (df["high"] < df["low"])).sum()
    zero_vol = (df["tick_volume"] == 0).sum()

    print("DUPLICATES:", dupes)
    print("SUSPICIOUS GAPS (>4d):", big_gaps)
    print("OHLC INVALID:", ohlc_invalid)
    print("ZERO VOLUME BARS:", zero_vol)

    if dupes > 0 or ohlc_invalid > 0:
        raise SystemExit("BLOCKED: data quality check failed. Not writing file.")

    out = pd.DataFrame(
        {
            "Date": df["time"].dt.strftime("%Y.%m.%d"),
            "Time": df["time"].dt.strftime("%H:%M:%S"),
            "Open": df["open"],
            "High": df["high"],
            "Low": df["low"],
            "Close": df["close"],
            "tick_volume": df["tick_volume"],
            "real_volume": df["real_volume"],
            "spread": df["spread"],
        }
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    print(f"WROTE: {OUT_PATH} ({len(out)} rows)")


if __name__ == "__main__":
    main()
