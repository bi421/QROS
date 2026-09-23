import glob

import pandas as pd

from researchos.quant_engine.vectorized_backtest import vectorized_backtest

print("=" * 60)
print("📈 SMA20/100 CROSSOVER – OUT-OF-SAMPLE VALIDATION")
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
close = df_h["close"]

# 2. Train/Val/Test split
train_mask = df_h.index.year <= 2023
val_mask = df_h.index.year == 2024
test_mask = df_h.index.year >= 2025


def run_backtest_on_period(df, mask, fast=20, slow=100):
    sub_df = df[mask]
    if len(sub_df) < slow + 10:
        return {"num_trades": 0, "total_return": 0, "sharpe": 0, "max_drawdown": 0, "win_rate": 0}

    prices = sub_df["close"].values.tolist()
    sma_fast = sub_df["close"].rolling(fast).mean()
    sma_slow = sub_df["close"].rolling(slow).mean()

    signals = []
    for i in range(slow, len(sub_df)):
        if sma_fast.iloc[i] > sma_slow.iloc[i] and sma_fast.iloc[i - 1] <= sma_slow.iloc[i - 1]:
            signals.append(("BUY", sub_df["close"].iloc[i]))
        elif sma_fast.iloc[i] < sma_slow.iloc[i] and sma_fast.iloc[i - 1] >= sma_slow.iloc[i - 1]:
            signals.append(("SELL", sub_df["close"].iloc[i]))

    if not signals:
        return {"num_trades": 0, "total_return": 0, "sharpe": 0, "max_drawdown": 0, "win_rate": 0}

    result = vectorized_backtest(prices, signals)
    return result


print("\n📊 RESULTS BY PERIOD")
print(f"{'Period':10} | {'Trades':6} | {'Return':8} | {'Sharpe':7} | {'MaxDD':8} | {'WinRate':6}")
print("-" * 55)

# Train (2021-2023)
res_train = run_backtest_on_period(df_h, train_mask)
print(f"{'Train':10} | {res_train['num_trades']:6d} | {res_train['total_return']:8.2%} | {res_train['sharpe']:7.2f} | {res_train['max_drawdown']:8.2%} | {res_train['win_rate']:6.2%}")
# Validation (2024)
res_val = run_backtest_on_period(df_h, val_mask)
print(f"{'Val':10} | {res_val['num_trades']:6d} | {res_val['total_return']:8.2%} | {res_val['sharpe']:7.2f} | {res_val['max_drawdown']:8.2%} | {res_val['win_rate']:6.2%}")
# Test (2025-2026)
res_test = run_backtest_on_period(df_h, test_mask)
print(f"{'Test':10} | {res_test['num_trades']:6d} | {res_test['total_return']:8.2%} | {res_test['sharpe']:7.2f} | {res_test['max_drawdown']:8.2%} | {res_test['win_rate']:6.2%}")
# Total (all data)
res_total = run_backtest_on_period(df_h, slice(None))
print(f"{'Total':10} | {res_total['num_trades']:6d} | {res_total['total_return']:8.2%} | {res_total['sharpe']:7.2f} | {res_total['max_drawdown']:8.2%} | {res_total['win_rate']:6.2%}")
print("\n" + "=" * 60)
if res_val["num_trades"] >= 10 and res_val["sharpe"] > 0.5 and res_test["num_trades"] >= 10 and res_test["sharpe"] > 0.5:
    print("✅ SUCCESS: Strategy works consistently across all periods!")
    print("🚀 This strategy is ready for live trading simulation.")
elif res_test["sharpe"] > 0.5:
    print("⚠️ Strategy works on test period but validation was weak. Consider adding TP/SL.")
else:
    print("❌ Strategy failed out-of-sample. Market regime may have changed.")
