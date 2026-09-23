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

# Run with TP/SL
result = vectorized_backtest_with_tpsl(
    prices=close.tolist(),
    signals=signals,
    initial_capital=100000,
    stop_loss_pct=0.02,
    take_profit_pct=0.04,
    trailing_stop=True,
)

print(f"Return: {result['total_return']:.2%}")
print(f"Sharpe: {result['sharpe']:.2f}")
print(f"Max DD: {result['max_drawdown']:.2%}")
print(f"Win Rate: {result['win_rate']:.2%}")
print(f"Trades: {result['num_trades']}")
