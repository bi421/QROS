from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

from researchos.engines.quant.machine_learning.purged_validation import purged_k_fold


def run_ml_macro_strategy() -> None:
    data_path = pathlib.Path("data/curated/xauusd/real_merged_data.csv")
    if not data_path.exists():
        raise FileNotFoundError(f"data not found: {data_path}")

    df = pd.read_csv(data_path, parse_dates=["date"], index_col="date")
    feature_cols = [
        "real_yield_10y", "dxy", "vix", "breakeven_inflation_10y",
        "fed_balance_sheet_change", "geopolitical_risk_index",
        "gold_silver_ratio", "gold_oil_ratio", "gold_btc_correlation",
    ]
    df["target"] = (df["close"].pct_change().shift(-1) > 0).astype(int)
    df_clean = df.dropna(subset=feature_cols + ["target"]).copy()
    X = df_clean[feature_cols].values
    y = df_clean["target"].values

    folds = purged_k_fold(len(X), n_splits=5, purge_gap=5, embargo_gap=2)
    fold_accuracies: list[float] = []
    fold_sharpe: list[float] = []
    for fold in folds:
        X_train, X_test = X[fold.train_indices], X[fold.test_indices]
        y_train, y_test = y[fold.train_indices], y[fold.test_indices]
        model = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42, n_jobs=-1)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        fold_accuracies.append(accuracy_score(y_test, y_pred))
        test_returns = df_clean["close"].pct_change().iloc[fold.test_indices].values
        positions = np.where(y_pred == 1, 1, -1)
        strategy_returns = positions * test_returns
        sigma = np.std(strategy_returns)
        fold_sharpe.append(float(np.mean(strategy_returns) / sigma * np.sqrt(252)) if sigma > 0 else 0.0)

    print(f"Average Purged Accuracy: {np.mean(fold_accuracies):.4f}")
    print(f"Average OOS Sharpe: {np.mean(fold_sharpe):.4f}")


if __name__ == "__main__":
    run_ml_macro_strategy()
