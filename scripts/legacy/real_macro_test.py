"""
REAL macro-factor test for XAUUSD using actual DXY + VIX data (no synthetic).
Merges data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv with the
freshly downloaded dxy_real_2021_2025.csv / vix_real_2021_2025.csv,
then runs a walk-forward OLS regression predicting next-day gold return
from DXY return + VIX level, and reports OUT-OF-SAMPLE accuracy vs a
majority-class baseline, plus a p-value. No synthetic data anywhere.

Run this in C:\\Users\\User\\Desktop\\ResearchOS
"""
import numpy as np
import pandas as pd
from scipy import stats

# ---- Load XAUUSD (real MT5 export) ----
gold = pd.read_csv("data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv")
print("Gold columns:", list(gold.columns))
print(gold.head(3))

# Try to find date + close columns robustly
date_col = [c for c in gold.columns if c.lower() in ("date", "time", "datetime")][0]
close_col = [c for c in gold.columns if c.lower() == "close"][0]

gold[date_col] = pd.to_datetime(gold[date_col])
gold = gold[[date_col, close_col]].rename(columns={date_col: "date", close_col: "gold_close"})
gold = gold.sort_values("date").reset_index(drop=True)
gold["gold_return"] = gold["gold_close"].pct_change()

# ---- Load DXY ----
dxy = pd.read_csv("dxy_real_2021_2025.csv", skiprows=2)
dxy.columns = ["date", "close", "high", "low", "open", "volume"]
dxy["date"] = pd.to_datetime(dxy["date"])
dxy["dxy_return"] = pd.to_numeric(dxy["close"], errors="coerce").pct_change()
dxy = dxy[["date", "dxy_return"]]

# ---- Load VIX ----
vix = pd.read_csv("vix_real_2021_2025.csv", skiprows=2)
vix.columns = ["date", "close", "high", "low", "open", "volume"]
vix["date"] = pd.to_datetime(vix["date"])
vix["vix_level"] = pd.to_numeric(vix["close"], errors="coerce")
vix = vix[["date", "vix_level"]]

# ---- Merge ----
df = gold.merge(dxy, on="date", how="inner").merge(vix, on="date", how="inner")
df = df.dropna().reset_index(drop=True)
print(f"\nMerged rows: {len(df)}")
print(df.head())

if len(df) < 200:
    print("\nNOT ENOUGH MERGED DATA — stopping.")
    raise SystemExit(1)

# ---- Target: will gold be UP tomorrow? (next-day direction) ----
df["target"] = (df["gold_return"].shift(-1) > 0).astype(int)
df = df.iloc[:-1]  # drop last row (no next-day target)

factor_cols = ["dxy_return", "vix_level"]

# ---- Walk-forward: expanding window, predict next day, no lookahead ----
lookback = 252  # ~1 trading year to train
preds = []
actuals = []

X_all = df[factor_cols].values
y_all = df["target"].values

for i in range(lookback, len(df)):
    X_train = X_all[:i]
    y_train = y_all[:i]
    X_test = X_all[i : i + 1]

    # simple logistic-style: OLS on returns, threshold at 0.5
    # (kept deliberately simple/transparent, not tuned)
    X_train_design = np.column_stack([np.ones(len(X_train)), X_train])
    try:
        coef, *_ = np.linalg.lstsq(X_train_design, y_train, rcond=None)
    except Exception:
        continue

    X_test_design = np.column_stack([np.ones(1), X_test])
    pred_prob = (X_test_design @ coef)[0]
    pred = 1 if pred_prob > 0.5 else 0

    preds.append(pred)
    actuals.append(y_all[i])

preds = np.array(preds)
actuals = np.array(actuals)

model_acc = (preds == actuals).mean()
baseline_acc = max(actuals.mean(), 1 - actuals.mean())  # majority class baseline

# McNemar-ish significance: binomial test vs baseline accuracy
n = len(actuals)
correct = (preds == actuals).sum()
# Test whether model_acc is significantly different from baseline_acc
# using a simple binomial test against baseline_acc as null proportion
binom_result = stats.binomtest(correct, n, baseline_acc, alternative="greater")

print("\n" + "=" * 60)
print(f"OUT-OF-SAMPLE PREDICTIONS: {n}")
print(f"MODEL ACCURACY:    {model_acc:.4f}")
print(f"BASELINE ACCURACY: {baseline_acc:.4f}")
print(f"P-VALUE (model > baseline): {binom_result.pvalue:.4f}")
print(f"SIGNIFICANT (p<0.05): {binom_result.pvalue < 0.05}")
print("=" * 60)
