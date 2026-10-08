"""
Generate signal file from real macro-factor predictions.
"""
import numpy as np
import pandas as pd

from researchos.engines.quant.signal_file import generate_signal_file_from_predictions, validate_signal_file

# ---- Load XAUUSD (real MT5 export) ----
gold = pd.read_csv("data/curated/xauusd/xauusd_d1_2021_2025_mt5_final.csv")
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
df["target"] = (df["gold_return"].shift(-1) > 0).astype(int)
df = df.iloc[:-1]

factor_cols = ["dxy_return", "vix_level"]
lookback = 252
preds = []
actuals = []
X_all = df[factor_cols].values
y_all = df["target"].values

for i in range(lookback, len(df)):
    X_train = X_all[:i]
    y_train = y_all[:i]
    X_test = X_all[i : i + 1]
    X_train_design = np.column_stack([np.ones(len(X_train)), X_train])
    try:
        coef, *_ = np.linalg.lstsq(X_train_design, y_train, rcond=None)
    except Exception:
        continue
    X_test_design = np.column_stack([np.ones(1), X_test])
    pred_prob = (X_test_design @ coef)[0]
    preds.append(pred_prob)
    actuals.append(y_all[i])

preds = pd.Series(preds, index=df["date"].iloc[lookback : len(df)])
actuals = np.array(actuals)

macro_data = {
    "dxy_return": dxy.set_index("date")["dxy_return"],
    "vix_level": vix.set_index("date")["vix_level"],
}

result = generate_signal_file_from_predictions(
    predictions=preds,
    gold_prices=df.set_index("date")["gold_close"],
    macro_data=macro_data,
    output_path="reports/signals/macro_signals.csv",
    threshold=0.5,
)

print("Signal file generated: reports/signals/macro_signals.csv")
print(f"Total signals: {len(result)}")
print(f"  BUY:  {(result['signal'] == 1).sum()}")
print(f"  SELL: {(result['signal'] == -1).sum()}")
print(f"  HOLD: {(result['signal'] == 0).sum()}")
print()
print(result.head(10).to_string(index=False))
print()
report = validate_signal_file("reports/signals/macro_signals.csv")
print(f"Validation: {'PASS' if report['valid'] else 'FAIL'}")
if report["errors"]:
    print("Errors:", report["errors"])
if report["warnings"]:
    print("Warnings:", report["warnings"])
print("Stats:", report["stats"])
