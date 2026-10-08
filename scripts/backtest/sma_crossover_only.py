import glob

import pandas as pd

from researchos.quant_engine.vectorized_backtest import vectorized_backtest

print("=" * 60)
print("📈 SMA CROSSOVER (NO FILTER)")
print("=" * 60)

files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
close = df_h["close"]

sma50 = close.rolling(50).mean()
sma200 = close.rolling(200).mean()

# Signals when SMA50 crosses above or below SMA200
signals = []
for i in range(200, len(df_h)):
    if sma50.iloc[i] > sma200.iloc[i]:
        signals.append(("BUY", close.iloc[i]))
    elif sma50.iloc[i] < sma200.iloc[i]:
        signals.append(("SELL", close.iloc[i]))

print(f"Generated {len(signals)} signals (BUY/SELL)")

if signals:
    result = vectorized_backtest(close.tolist(), signals)
    print("\n📊 BACKTEST RESULTS")
    print(f"Trades: {result['num_trades']}")
    print(f"Return: {result['total_return']:.2%}")
    print(f"Sharpe: {result['sharpe']:.2f}")
    print(f"Max DD: {result['max_drawdown']:.2%}")
    print(f"Win Rate: {result['win_rate']:.2%}")
else:
    print("❌ No signals generated – SMA50 and SMA200 never crossed in the data period.")
