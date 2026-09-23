import sys

sys.path.insert(0, ".")
import glob

import pandas as pd

from researchos.quant_engine.backtest_tpsl import vectorized_backtest_with_tpsl

print("Loading data...")
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
close = df_h["close"]

# SMA20/100 signals
sma20 = close.rolling(20).mean()
sma100 = close.rolling(100).mean()
signals = []
for i in range(100, len(df_h)):
    if sma20.iloc[i] > sma100.iloc[i] and sma20.iloc[i - 1] <= sma100.iloc[i - 1]:
        signals.append(("BUY", close.iloc[i]))
    elif sma20.iloc[i] < sma100.iloc[i] and sma20.iloc[i - 1] >= sma100.iloc[i - 1]:
        signals.append(("SELL", close.iloc[i]))

print(f"Generated {len(signals)} signals")

# Grid search TP/SL
best_sharpe = -999
best_params = None
results = []

for sl in [0.01, 0.02, 0.03, 0.05]:
    for tp in [0.02, 0.04, 0.06, 0.08]:
        result = vectorized_backtest_with_tpsl(
            prices=close.tolist(),
            signals=signals,
            stop_loss_pct=sl,
            take_profit_pct=tp,
            trailing_stop=True,
        )
        results.append((sl, tp, result["sharpe"], result["total_return"], result["max_drawdown"]))
        if result["sharpe"] > best_sharpe:
            best_sharpe = result["sharpe"]
            best_params = (sl, tp)

print("\n📊 Grid Search Results:")
print("SL    | TP    | Sharpe | Return  | Max DD")
print("------|-------|--------|---------|--------")
for sl, tp, sh, ret, dd in results:
    print(f"{sl:.2f}  | {tp:.2f}  | {sh:6.2f} | {ret:7.2%} | {dd:7.2%}")

print(f"\n✅ Best: SL={best_params[0]:.2f}, TP={best_params[1]:.2f} -> Sharpe={best_sharpe:.2f}")
