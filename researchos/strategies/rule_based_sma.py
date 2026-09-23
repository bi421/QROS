import glob  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

print("=" * 60)
print("📈 RULE-BASED STRATEGY: SMA CROSSOVER + ADX FILTER")
print("=" * 60)

# 1. Өгөгдөл ачаалах
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
print(f"Data: {len(df_h)} bars (4h)")

# 2. SMA 50 and 200
close = df_h["close"]
sma50 = close.rolling(50).mean()
sma200 = close.rolling(200).mean()

# 3. ADX (14) - энгийн тооцоо
high = df_h["high"]
low = df_h["low"]
tr = np.maximum(high - low, np.maximum((high - close.shift()).abs(), (low - close.shift()).abs()))
atr = tr.rolling(14).mean()
up_move = high - high.shift()
down_move = low.shift() - low
plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
plus_dm_smooth = pd.Series(plus_dm).rolling(14).mean()
minus_dm_smooth = pd.Series(minus_dm).rolling(14).mean()
di_plus = 100 * (plus_dm_smooth / atr)
di_minus = 100 * (minus_dm_smooth / atr)
dx = 100 * np.abs(di_plus - di_minus) / (di_plus + di_minus)
adx = dx.rolling(14).mean()

# 4. Дохио: BUY when SMA50 > SMA200 and ADX > 25; SELL when SMA50 < SMA200 and ADX > 25
signals = []
for i in range(200, len(df_h)):
    if adx.iloc[i] > 25:
        if sma50.iloc[i] > sma200.iloc[i]:
            signals.append(("BUY", close.iloc[i]))
        elif sma50.iloc[i] < sma200.iloc[i]:
            signals.append(("SELL", close.iloc[i]))
    # else: no signal

# 5. Бэктест (C++ биш, векторжсон Python ашиглая, учир нь probabilities байхгүй)
from researchos.quant_engine.vectorized_backtest import vectorized_backtest  # noqa: E402

prices = close.tolist()
result = vectorized_backtest(prices, signals)

print("\n📊 BACKTEST RESULTS (2021-2026)")
print(f"Trades: {result['num_trades']}")
print(f"Return: {result['total_return']:.2%}")
print(f"Sharpe: {result['sharpe']:.2f}")
print(f"Max DD: {result['max_drawdown']:.2%}")
print(f"Win Rate: {result['win_rate']:.2%}")
