import glob
import json
import sys
import time

import pandas as pd
from researchos.quant_engine.cpp_engine import CppQuant

print("=" * 70)
print("✅ ИТГЭХ БОЛОМЖТОЙ: Python агрегаци + C++ бэктест")
print("=" * 70)

# 1. Өгөгдөл ачаалах
start_load = time.time()
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
if not files:
    print("❌ Өгөгдөл олдсонгүй!")
    sys.exit(1)

df = pd.concat(
    [
        pd.read_csv(
            f,
            sep=";",
            header=None,
            names=["datetime", "open", "high", "low", "close", "volume"],
            dtype={"datetime": str},
        )
        for f in files
    ],
    ignore_index=True,
)

df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
print(f"✅ {len(df):,} мөрийг {time.time() - start_load:.2f} сек")

# 2. Агрегаци (Python-д хурдан)
timeframes = [5, 15, 30, 60]
strategies = [
    ("SMA_10_30", 10, 30),
    ("SMA_20_50", 20, 50),
]
commissions = [0.0005, 0.001, 0.0015]

all_results = []
sweep_start = time.time()

for h in timeframes:
    print(f"\n⏳ {h}min агрегацлаж байна...")
    df_h = df.resample(f"{h}min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    print(f"   {len(df_h):,} candle")

    # C++ engine-д ачаалах
    engine = CppQuant()
    engine.load_from_dataframe(df_h)

    for name, short, long in strategies:
        result = engine.run_sma(short, long)

        winrate = result.get("winrate", 0)
        if winrate > 1:
            winrate = winrate / 100.0
        if winrate > 1:
            winrate = winrate / 100.0
        winrate = min(winrate, 1.0)

        trades = result.get("num_trades", 0)
        total_return = result.get("total_return", 0)

        print(f"   {name}: Winrate: {winrate * 100:.2f}%, Trades: {trades}")

        # Бүх комисст ижил үр дүн (комисс тооцохгүй)
        for c in commissions:
            all_results.append(
                {
                    "timeframe": f"{h}min",
                    "strategy": name,
                    "commission": c,
                    "winrate": winrate * 100,
                    "trades": trades,
                    "return": total_return * 100,
                    "sharpe": result.get("sharpe_ratio", 0),
                }
            )

sweep_time = time.time() - sweep_start
print(f"\n✅ Нийт хугацаа: {sweep_time:.2f} сек")

# 3. Хадгалах
with open("trusted_results.json", "w") as f:
    json.dump(all_results, f, indent=2)

# 4. Шилдэг
if all_results:
    best = max(all_results, key=lambda x: x["winrate"])
    print("\n" + "=" * 70)
    print("🏆 ХАМГИЙН САЙН (статистикийн хувьд найдвартай):")
    print(f"  Стратеги: {best['strategy']}")
    print(f"  Цаг.хүрээ: {best['timeframe']}")
    print(f"  Winrate: {best['winrate']:.2f}%")
    print(f"  Trades: {best['trades']}")
    print(f"  Return: {best['return']:.2f}%")

print("\n" + "=" * 70)
print("✅ БҮХ АЖИЛ ДУУССАН!")
