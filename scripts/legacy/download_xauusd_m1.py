from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1

START = datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

OUTPUT_DIR = Path("data/mt5/xauusd")
CHUNK_DIR = OUTPUT_DIR / "chunks"

FINAL_CSV = OUTPUT_DIR / "XAUUSD_M1_2021_2025_MT5.csv"
MANIFEST_JSON = OUTPUT_DIR / "XAUUSD_M1_2021_2025_MT5.manifest.json"

# Сарын chunk.
CHUNK_DAYS = 31

# MT5 history server/cache заримдаа шууд бүх data-г өгөхгүй.
MAX_RETRIES = 5
RETRY_SECONDS = 3


# ============================================================
# HELPERS
# ============================================================


def fail(message: str) -> None:
    print(f"\nERROR: {message}")
    mt5.shutdown()
    sys.exit(1)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)

            if not block:
                break

            h.update(block)

    return h.hexdigest()


def get_chunks(
    start: datetime,
    end: datetime,
):
    current = start

    while current <= end:
        chunk_end = min(
            current + timedelta(days=CHUNK_DAYS) - timedelta(seconds=1),
            end,
        )

        yield current, chunk_end

        current = chunk_end + timedelta(seconds=1)


def download_chunk(
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  attempt {attempt}/{MAX_RETRIES}: " f"{start.isoformat()} -> {end.isoformat()}")

        rates = mt5.copy_rates_range(
            SYMBOL,
            TIMEFRAME,
            start,
            end,
        )

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)

            df["time"] = pd.to_datetime(
                df["time"],
                unit="s",
                utc=True,
            )

            return df

        print(f"  no data. MT5 error: {mt5.last_error()}")

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_SECONDS)

    return pd.DataFrame()


def validate_chunk(df: pd.DataFrame) -> None:
    required = {
        "time",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "spread",
        "real_volume",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    if df.empty:
        raise ValueError("Empty dataframe")

    if df["time"].isna().any():
        raise ValueError("NULL timestamps")

    if df["time"].duplicated().any():
        raise ValueError("Duplicate timestamps")

    # OHLC
    bad_ohlc = (df["high"] < df["open"]) | (df["high"] < df["close"]) | (df["high"] < df["low"]) | (df["low"] > df["open"]) | (df["low"] > df["close"]) | (df["low"] > df["high"])

    if bad_ohlc.any():
        raise ValueError(f"Invalid OHLC rows: {int(bad_ohlc.sum())}")

    # Volume
    bad_tick_volume = df["tick_volume"] < 0
    bad_real_volume = df["real_volume"] < 0

    if bad_tick_volume.any():
        raise ValueError(f"Negative tick_volume rows: " f"{int(bad_tick_volume.sum())}")

    if bad_real_volume.any():
        raise ValueError(f"Negative real_volume rows: " f"{int(bad_real_volume.sum())}")

    # Spread
    if (df["spread"] < 0).any():
        raise ValueError(f"Negative spread rows: " f"{int((df['spread'] < 0).sum())}")

    # Sorted
    if not df["time"].is_monotonic_increasing:
        raise ValueError("Timestamp order is not increasing")


def validate_final(df: pd.DataFrame) -> dict:
    validate_chunk(df)

    df = df.sort_values("time").reset_index(drop=True)

    duplicate_count = int(df["time"].duplicated().sum())

    time_diff = df["time"].diff().dropna()

    gap_count = int((time_diff > pd.Timedelta(minutes=1)).sum())

    max_gap = time_diff.max() if not time_diff.empty else pd.Timedelta(0)

    bad_ohlc = (df["high"] < df["open"]) | (df["high"] < df["close"]) | (df["high"] < df["low"]) | (df["low"] > df["open"]) | (df["low"] > df["close"]) | (df["low"] > df["high"])

    invalid_tick_volume = int((df["tick_volume"] < 0).sum())

    invalid_real_volume = int((df["real_volume"] < 0).sum())

    invalid_spread = int((df["spread"] < 0).sum())

    report = {
        "row_count": int(len(df)),
        "unique_timestamps": int(df["time"].nunique()),
        "duplicate_rows": duplicate_count,
        "invalid_ohlc_rows": int(bad_ohlc.sum()),
        "invalid_tick_volume_rows": invalid_tick_volume,
        "invalid_real_volume_rows": invalid_real_volume,
        "invalid_volume_flags": (invalid_tick_volume + invalid_real_volume),
        "invalid_spread_rows": invalid_spread,
        "gap_count_gt_1m": gap_count,
        "max_gap_seconds": (max_gap.total_seconds() if pd.notna(max_gap) else 0),
        "actual_start": df["time"].iloc[0].isoformat(),
        "actual_end": df["time"].iloc[-1].isoformat(),
    }

    passed = report["row_count"] > 0 and report["duplicate_rows"] == 0 and report["invalid_ohlc_rows"] == 0 and report["invalid_volume_flags"] == 0 and report["invalid_spread_rows"] == 0

    report["passed_integrity"] = passed

    return report


# ============================================================
# MAIN
# ============================================================


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    CHUNK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 70)
    print("XAUUSD M1 MT5 HISTORICAL DATA DOWNLOAD")
    print("=" * 70)

    print(f"Symbol : {SYMBOL}")
    print(f"Start  : {START}")
    print(f"End    : {END}")
    print(f"Output : {FINAL_CSV}")
    print()

    # --------------------------------------------------------
    # MT5 INIT
    # --------------------------------------------------------

    if not mt5.initialize():
        fail(f"MT5 initialize failed: " f"{mt5.last_error()}")

    print("MT5 initialized")

    print(
        "MT5 version:",
        mt5.version(),
    )

    terminal = mt5.terminal_info()

    if terminal is not None:
        print(
            "Terminal:",
            terminal.name,
        )

    # --------------------------------------------------------
    # SYMBOL
    # --------------------------------------------------------

    if not mt5.symbol_select(SYMBOL, True):
        fail(f"Cannot select {SYMBOL}: " f"{mt5.last_error()}")

    info = mt5.symbol_info(SYMBOL)

    if info is None:
        fail(f"Cannot get symbol info: " f"{mt5.last_error()}")

    print()
    print("Symbol metadata")
    print("----------------")

    print("description :", info.description)
    print("digits      :", info.digits)
    print("point       :", info.point)
    print("spread      :", info.spread)
    print("contract    :", info.trade_contract_size)
    print("tick size   :", info.trade_tick_size)
    print("tick value  :", info.trade_tick_value)
    print("base        :", info.currency_base)
    print("profit      :", info.currency_profit)

    # --------------------------------------------------------
    # DOWNLOAD MONTHLY CHUNKS
    # --------------------------------------------------------

    all_chunks: list[pd.DataFrame] = []

    chunks = list(
        get_chunks(
            START,
            END,
        )
    )

    print()
    print(f"Total chunks: {len(chunks)}")

    for index, (chunk_start, chunk_end) in enumerate(
        chunks,
        start=1,
    ):
        print()
        print(f"[{index}/{len(chunks)}]")

        df = download_chunk(
            chunk_start,
            chunk_end,
        )

        if df.empty:
            fail(f"No data for chunk " f"{chunk_start} -> {chunk_end}")

        validate_chunk(df)

        # Strict requested interval.
        df = df[(df["time"] >= pd.Timestamp(START)) & (df["time"] <= pd.Timestamp(END))].copy()

        filename = f"XAUUSD_M1_" f"{chunk_start:%Y_%m}.csv"

        chunk_path = CHUNK_DIR / filename

        df.to_csv(
            chunk_path,
            index=False,
        )

        print(f"  rows: {len(df):,}")

        print(f"  first: {df['time'].iloc[0]}")

        print(f"  last : {df['time'].iloc[-1]}")

        print(f"  saved: {chunk_path}")

        all_chunks.append(df)

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("MERGING")
    print("=" * 70)

    final = pd.concat(
        all_chunks,
        ignore_index=True,
    )

    final = final.sort_values("time")

    # Remove nothing silently.
    duplicate_count = int(final["time"].duplicated().sum())

    if duplicate_count:
        fail(f"Duplicate timestamps detected " f"during merge: {duplicate_count}")

    final = final.reset_index(drop=True)

    # --------------------------------------------------------
    # FINAL VALIDATION
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL VALIDATION")
    print("=" * 70)

    report = validate_final(final)

    for key, value in report.items():
        print(f"{key:35}: {value}")

    if not report["passed_integrity"]:
        fail("FINAL INTEGRITY VALIDATION FAILED")

    # --------------------------------------------------------
    # SAVE FINAL CSV
    # --------------------------------------------------------

    final.to_csv(
        FINAL_CSV,
        index=False,
    )

    sha256 = sha256_file(FINAL_CSV)

    print()
    print("CSV saved:")
    print(FINAL_CSV)

    print()
    print("SHA256:")
    print(sha256)

    # --------------------------------------------------------
    # MANIFEST
    # --------------------------------------------------------

    manifest = {
        "dataset": "XAUUSD",
        "timeframe": "M1",
        "source": "MetaTrader5",
        "symbol": SYMBOL,
        "requested_start": START.isoformat(),
        "requested_end": END.isoformat(),
        "terminal": {
            "version": (list(mt5.version()) if mt5.version() else None),
            "name": (terminal.name if terminal else None),
        },
        "symbol_metadata": {
            "description": info.description,
            "digits": info.digits,
            "point": info.point,
            "spread": info.spread,
            "spread_float": info.spread_float,
            "trade_contract_size": (info.trade_contract_size),
            "trade_tick_size": (info.trade_tick_size),
            "trade_tick_value": (info.trade_tick_value),
            "currency_base": (info.currency_base),
            "currency_profit": (info.currency_profit),
        },
        "validation": report,
        "file": {
            "path": str(FINAL_CSV),
            "sha256": sha256,
            "bytes": FINAL_CSV.stat().st_size,
        },
    }

    with MANIFEST_JSON.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            manifest,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("Manifest:")
    print(MANIFEST_JSON)

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print(f"Rows: {len(final):,}")

    print(f"Range: " f"{final['time'].iloc[0]} " f"-> " f"{final['time'].iloc[-1]}")

    print(f"SHA256: {sha256}")

    mt5.shutdown()


if __name__ == "__main__":
    main()
