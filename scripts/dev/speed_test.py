import glob
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from joblib import Parallel, delayed
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from researchos.quant_engine.vectorized_backtest import vectorized_backtest

timings = {}

# 1. Data loading
t0 = time.time()
files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
df = pd.concat(
    [pd.read_csv(f, sep=";", header=None, names=["datetime", "open", "high", "low", "close", "volume"]) for f in files],
    ignore_index=True,
)
df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
df = df.set_index("datetime")
df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
timings["data_loading"] = time.time() - t0

# 2. Train/val/test split
t0 = time.time()
train_mask = df_h.index.year <= 2023
val_mask = df_h.index.year == 2024
test_mask = df_h.index.year >= 2025
train_df, val_df, test_df = df_h[train_mask], df_h[val_mask], df_h[test_mask]
timings["split"] = time.time() - t0


# 3. Feature generation
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


t0 = time.time()
train_feat = make_features(train_df)
val_feat = make_features(val_df)
test_feat = make_features(test_df)
timings["feature_generation"] = time.time() - t0

# 4. Train model
t0 = time.time()
feature_cols = [c for c in train_feat.columns if c != "target"]
X_train, y_train = train_feat[feature_cols].values, train_feat["target"].values
X_val, y_val = val_feat[feature_cols].values, val_feat["target"].values
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s = scaler.transform(X_val)
model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
model.fit(X_train_s, y_train)
timings["model_training"] = time.time() - t0


# 5. Grid search (parallel)
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


t0 = time.time()
thresholds = [0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60]
results = Parallel(n_jobs=-1)(delayed(eval_th)(th) for th in thresholds)
timings["grid_search"] = time.time() - t0

# 6. Test
t0 = time.time()
best_sharpe = -999
best_th = 0.52
for th, res in results:
    if res["num_trades"] >= 20 and res["sharpe"] > best_sharpe:
        best_sharpe = res["sharpe"]
        best_th = th
test_probs = model.predict_proba(X_val_s)[:, 1]  # use val as test (just for timing)
timings["test"] = time.time() - t0

# Summary
print("\n" + "=" * 50)
print("⏱️  ГҮЙЦЭТГЭЛИЙН ХУГАЦААНЫ ШИНЖИЛГЭЭ")
print("=" * 50)
total = 0
for step, duration in timings.items():
    print(f"{step:20s}: {duration:.3f} сек")
    total += duration
print(f"{'Нийт':20s}: {total:.3f} сек")
print("=" * 50)

# Зөвлөмж
slowest = max(timings, key=timings.get)
print(f"\n🐢 Хамгийн удаан хэсэг: '{slowest}' ({timings[slowest]:.3f} сек)")
if slowest == "grid_search":
    print("   → Threshold-ийн тоог 5 болгон бууруулж болно.")
    print("   → Эсвэл векторжсон бэктестийг бүрэн loop-гүй болгох.")
elif slowest == "feature_generation":
    print("   → Feature-ийг кэшлэх (joblib) эсвэл numpy-р векторжсон тооцоолол руу шилжих.")
print("")
