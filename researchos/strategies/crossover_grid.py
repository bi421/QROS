import glob

import numpy as np
import pandas as pd

from researchos.quant_engine.vectorized_backtest import vectorized_backtest

print("=" * 60)
print("📈 PROPER SMA CROSSOVER STRATEGY")
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


# Compute ADX (14) for filter
def compute_adx(high, low, close):
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
    return adx


high = df_h["high"]
low = df_h["low"]
adx = compute_adx(high, low, close)

# Define parameter sets: (fast, slow, adx_threshold)
params = [
    (20, 100, None),  # no ADX filter
    (20, 100, 25),  # ADX > 25
    (50, 200, None),
    (50, 200, 25),
]

results = []
for fast, slow, adx_th in params:
    sma_fast = close.rolling(fast).mean()
    sma_slow = close.rolling(slow).mean()

    signals = []
    last_signal = None
    for i in range(slow, len(df_h)):
        # Check crossover
        if sma_fast.iloc[i] > sma_slow.iloc[i] and sma_fast.iloc[i - 1] <= sma_slow.iloc[i - 1]:
            # BUY signal
            if adx_th is None or (pd.notna(adx.iloc[i]) and adx.iloc[i] > adx_th):
                signals.append(("BUY", close.iloc[i]))
                last_signal = "BUY"
        elif sma_fast.iloc[i] < sma_slow.iloc[i] and sma_fast.iloc[i - 1] >= sma_slow.iloc[i - 1]:
            # SELL signal
            if adx_th is None or (pd.notna(adx.iloc[i]) and adx.iloc[i] > adx_th):
                signals.append(("SELL", close.iloc[i]))
                last_signal = "SELL"

    if signals:
        result = vectorized_backtest(close.tolist(), signals)
        results.append(
            {
                "fast": fast,
                "slow": slow,
                "adx": adx_th if adx_th else "None",
                "trades": result["num_trades"],
                "return": result["total_return"],
                "sharpe": result["sharpe"],
                "dd": result["max_drawdown"],
                "win": result["win_rate"],
            }
        )
    else:
        print(f"No signals for SMA{fast}/{slow} with ADX{adx_th}")

# Display results
print("\n📊 PARAMETER COMPARISON")
print("Fast | Slow | ADX | Trades | Return  | Sharpe | MaxDD  | WinRate")
print("-----|------|-----|--------|---------|--------|--------|--------")
for r in results:
    print(f"{r['fast']:4d} | {r['slow']:4d} | {str(r['adx']):3s} | {r['trades']:6d} | {r['return']:7.2%} | {r['sharpe']:6.2f} | {r['dd']:7.2%} | {r['win']:6.2%}")

# Find best by Sharpe (with trades >= 30)
best = max([r for r in results if r["trades"] >= 30], key=lambda x: x["sharpe"], default=None)
if best:
    print(f"\n✅ BEST: SMA{best['fast']}/{best['slow']} with ADX{best['adx']} – Sharpe={best['sharpe']:.2f}, Trades={best['trades']}")
else:
    print("\n⚠️ No parameter set with >=30 trades.")
