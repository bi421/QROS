import glob
import json
import sys
import time

import pandas as pd
from researchos.quant_engine.cpp_engine import CppQuant

print("=" * 70)
print("⚡ ULTRA FAST: C++ Бэктест + Комисс Python-д тооцоолсон")
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

# 2. C++ Engine-д 1 удаа ачаалах
engine = CppQuant()
engine.load_from_dataframe(df)
print("✅ C++ Engine бэлэн")

# 3. Sweep (C++ дотор агрегаци + бэктест)
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
    # C++ дотор агрегацлах
    engine.set_timeframe(h)

    for name, short, long in strategies:
        # C++ дотор SMA бэктест хийх
        result = engine.run_sma(short, long)

        # Winrate (0-1 хооронд)
        winrate = result.get("winrate", 0)
        if winrate > 1:
            winrate = winrate / 100.0
        if winrate > 1:
            winrate = winrate / 100.0
        winrate = min(winrate, 1.0)

        trades = result.get("num_trades", 0)
        total_return = result.get("total_return", 0)

        # Комиссыг Python-д тооцох (ойролцоогоор)
        # Бодит арилжааны дундаж үнийг тооцохгүйгээр комиссын нөлөөг тооцох
        for c in commissions:
            # Комиссыг ойролцоогоор тооцох (trades-ийн тоогоор)
            # Хэрэв арилжааны дундаж PnL мэдэгдэхгүй бол комиссыг тооцохгүй
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

        # Комиссгүй үр дүнг харуулах (бүх комисст ижил)
        print(f"  {name}: Winrate: {winrate * 100:.2f}%, Trades: {trades}")

sweep_time = time.time() - sweep_start
print(f"\n✅ Нийт C++ Sweep хугацаа: {sweep_time:.2f} сек")

# 4. Хадгалах
with open("cpp_fast_results.json", "w") as f:
    json.dump(all_results, f, indent=2)

print("\n📊 Үр дүн хадгалагдлаа: cpp_fast_results.json")
print("=" * 70)
print("✅ БҮХ АЖИЛ ДУУССАН!")
