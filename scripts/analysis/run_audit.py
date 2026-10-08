import sys

sys.path.append("cpp_quant/python")
import glob

import cpp_quant_core as core
import pandas as pd
from researchos.quant_engine.cpp_engine import CppQuant

# 1. Өгөгдөл унших
df = pd.concat(
    [
        pd.read_csv(
            f,
            sep=";",
            header=None,
            names=["datetime", "open", "high", "low", "close", "volume"],
            dtype={"datetime": str},
        )
        .assign(datetime=lambda x: pd.to_datetime(x["datetime"], format="%Y%m%d %H%M%S"))
        .dropna(subset=["datetime"])
        .set_index("datetime")
        for f in glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    ]
).sort_index()

# 2. 1D агрегац
df_d = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
print(f"1D Candle: {len(df_d)}")

# 3. Анхны бэктест (CppQuant)
engine = CppQuant()
engine.load_from_dataframe(df_d)
original = engine.run_sma(20, 50)
print(f"Original Winrate: {original['winrate']:.2f}%")
print(f"Original Trades: {original['num_trades']}")

# 4. Аудит (вектор арга)
timestamps = df_d.index.astype("int64") // 10**9  # секунд
opens = df_d["open"].tolist()
highs = df_d["high"].tolist()
lows = df_d["low"].tolist()
closes = df_d["close"].tolist()
volumes = df_d["volume"].tolist()

audit = core.run_sma_audit(timestamps, opens, highs, lows, closes, volumes, 20, 50, 0.0001)
print(f"Audit Winrate: {audit.winrate * 100:.2f}%")
print(f"Audit Trades: {audit.num_trades}")

# 5. Харьцуулалт
# original-ыг AuditResult болгон хувиргах (одоохондоо шууд compare хийхэд тохиромжгүй)
# Бид гараар харьцуулна
print("\n===== COMPARISON =====")
print(f"Original Winrate: {original['winrate']:.2f}%")
print(f"Audit Winrate: {audit.winrate * 100:.2f}%")
print(f"Diff: {abs(original['winrate'] - audit.winrate * 100):.2f}%")
if abs(original["winrate"] - audit.winrate * 100) < 0.5:
    print("✅ Winrate matches! System is correct.")
else:
    print("❌ Winrate mismatch! There is a bug.")
