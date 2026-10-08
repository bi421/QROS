import sys

sys.path.append("cpp_quant/python")
import glob

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

# 3. C++ engine ашиглан бэктест
engine = CppQuant()
engine.load_from_dataframe(df_d)
result = engine.run_sma(20, 50)

# 4. PnL жагсаалт
pnls = [trade[4] for trade in result["trades"]]  # trade[4] = pnl
print(f"Нийт арилжаа: {len(pnls)}")
print(f"Winrate: {result['winrate']:.2f}%")

# 5. Bootstrap CI (C++)
ci_low, ci_high = engine.get_bootstrap_winrate_ci(pnls, iterations=1000, ci=0.95)
print(f"95% Bootstrap CI (Winrate): [{ci_low * 100:.2f}%, {ci_high * 100:.2f}%]")
