import sys

sys.path.append("cpp_quant/python")
import glob

import pandas as pd
from researchos.quant_engine.cpp_engine import CppQuant

# Өгөгдөл унших
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

# 1D агрегац
df_d = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

engine = CppQuant()
engine.load_from_dataframe(df_d)

print("===== БҮХ СТРАТЕГИЙН ХАРЬЦУУЛАЛТ (1D) =====")
print(f"Candle: {len(df_d)}")

# 1. SMA 20/50
r = engine.run_sma(20, 50)
print(f"SMA 20/50: Winrate {r['winrate']:.2f}%, Trades {r['num_trades']}")

# 2. SMA 50/200
r = engine.run_sma(50, 200)
print(f"SMA 50/200: Winrate {r['winrate']:.2f}%, Trades {r['num_trades']}")

# 3. RSI 14
r = engine.run_rsi(14, 30, 70)
print(f"RSI 14: Winrate {r['winrate']:.2f}%, Trades {r['num_trades']}")

# 4. MACD
r = engine.run_macd(12, 26, 9, 200)
print(f"MACD: Winrate {r['winrate']:.2f}%, Trades {r['num_trades']}")
