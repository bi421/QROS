import glob
import sys
import time

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

sys.path.insert(0, ".")
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from researchos.quant_engine.vectorized_backtest import vectorized_backtest

print("🔥 RESEARCHOS – БҮГД НЭГ ДОР ХИЙХ АВТОМАТ СИСТЕМ")
print("=" * 50)
print("Loading data...")
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
print(f"Data: {len(df_h)} bars (4h)")

# Train: 2021-2023, Val: 2024, Test: 2025-2026
train_mask = df_h.index.year <= 2023
val_mask = df_h.index.year == 2024
test_mask = df_h.index.year >= 2025
train_df, val_df, test_df = df_h[train_mask], df_h[val_mask], df_h[test_mask]
print(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")


# Feature generation (basic + macro)
def make_features(df):
    df = df.copy()
    close = df["close"]
    df["ret1"] = close.pct_change()
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"ret_lag_{lag}"] = df["ret1"].shift(lag)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    exp1, exp2 = close.ewm(span=12).mean(), close.ewm(span=26).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]
    mean, std = close.rolling(20).mean(), close.rolling(20).std()
    df["bb_high"] = mean + 2 * std
    df["bb_low"] = mean - 2 * std
    df["bb_pos"] = (close - df["bb_low"]) / (df["bb_high"] - df["bb_low"])
    df["volatility"] = df["ret1"].rolling(20).std()
    df["target"] = (close.shift(-1) > close).astype(int)
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df


train_feat = make_features(train_df)
val_feat = make_features(val_df)
test_feat = make_features(test_df)
feature_cols = [c for c in train_feat.columns if c != "target"]
X_train, y_train = train_feat[feature_cols].values, train_feat["target"].values
X_val, y_val = val_feat[feature_cols].values, val_feat["target"].values
X_test, y_test = test_feat[feature_cols].values, test_feat["target"].values

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s = scaler.transform(X_val) if X_val.shape[0] > 0 else np.array([])
X_test_s = scaler.transform(X_test) if X_test.shape[0] > 0 else np.array([])

model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
model.fit(X_train_s, y_train)
print(f"Train accuracy: {model.score(X_train_s, y_train):.2%}")

# Threshold grid search (parallel)
thresholds = [0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60]


def eval_th(th):
    val_probs = model.predict_proba(X_val_s)[:, 1]
    signals = []
    for i, idx in enumerate(val_df.index):
        if i < len(val_probs):
            prob = val_probs[i]
            price = val_df.loc[idx, "close"]
            if prob > th:
                signals.append(("BUY", price))
            elif prob < (1 - th):
                signals.append(("SELL", price))
    res = vectorized_backtest(val_df["close"].tolist(), signals)
    return th, res


print("\n🔍 Validation grid search (parallel)")
print("Threshold | Trades | Return  | Sharpe | MaxDD  | WinRate")
print("----------|--------|---------|--------|--------|--------")
start = time.time()
results = Parallel(n_jobs=-1)(delayed(eval_th)(th) for th in thresholds)
best_sharpe, best_th = -999, 0.55
for th, res in results:
    if res["num_trades"] >= 20 and res["sharpe"] > best_sharpe:
        best_sharpe, best_th = res["sharpe"], th
    print(f"{th:5.2f}     | {res['num_trades']:6d} | {res['total_return']:7.2%} | {res['sharpe']:6.2f} | {res['max_drawdown']:6.2%} | {res['win_rate']:7.2%}")
print(f"Best: {best_th} (Sharpe={best_sharpe:.2f})")

# Test
test_probs = model.predict_proba(X_test_s)[:, 1]
signals = []
for i, idx in enumerate(test_df.index):
    if i < len(test_probs):
        prob, price = test_probs[i], test_df.loc[idx, "close"]
        if prob > best_th:
            signals.append(("BUY", price))
        elif prob < (1 - best_th):
            signals.append(("SELL", price))
res = vectorized_backtest(test_df["close"].tolist(), signals)
print("\n📊 OUT-OF-SAMPLE TEST (2025-2026)")
print(f"Trades: {res['num_trades']}\nReturn: {res['total_return']:.2%}\nSharpe: {res['sharpe']:.2f}\nMax DD: {res['max_drawdown']:.2%}\nWin Rate: {res['win_rate']:.2%}")
print("✅ SUCCESS" if res["num_trades"] >= 30 and res["sharpe"] > 0.5 else "❌ FAILED")
