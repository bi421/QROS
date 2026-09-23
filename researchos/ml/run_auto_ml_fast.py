import glob
import sys

import numpy as np
import optuna
import pandas as pd

sys.path.insert(0, ".")
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from researchos.quant_engine.vectorized_backtest import vectorized_backtest


def make_features(df, selected, target_horizon=1):
    df = df.copy()
    close = df["close"]
    df["ret1"] = close.pct_change()
    for lag in [1, 2, 3, 5, 10, 20]:
        df[f"ret_lag_{lag}"] = df["ret1"].shift(lag)
    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    # MACD
    exp1 = close.ewm(span=12).mean()
    exp2 = close.ewm(span=26).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_diff"] = df["macd"] - df["macd_signal"]
    # Bollinger
    mean = close.rolling(20).mean()
    std = close.rolling(20).std()
    df["bb_high"] = mean + 2 * std
    df["bb_low"] = mean - 2 * std
    df["bb_pos"] = (close - df["bb_low"]) / (df["bb_high"] - df["bb_low"])
    # Volatility
    df["volatility"] = df["ret1"].rolling(20).std()

    keep_cols = ["ret1"]
    if "rsi" in selected:
        keep_cols.append("rsi")
    if "macd" in selected:
        keep_cols.extend(["macd", "macd_signal", "macd_diff"])
    if "bb" in selected:
        keep_cols.append("bb_pos")
    if "vol" in selected:
        keep_cols.append("volatility")
    if "lags" in selected:
        keep_cols.extend(["ret_lag_1", "ret_lag_2", "ret_lag_3", "ret_lag_5", "ret_lag_10", "ret_lag_20"])

    # Target
    df["target"] = (close.shift(-target_horizon) > close).astype(int)
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df[keep_cols + ["target"]]


def objective(trial, train_df, val_df):
    # Hyperparameters
    n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
    max_depth = trial.suggest_int("max_depth", 3, 12)
    learning_rate = trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
    subsample = trial.suggest_float("subsample", 0.6, 1.0)
    colsample_bytree = trial.suggest_float("colsample_bytree", 0.6, 1.0)
    threshold = trial.suggest_float("threshold", 0.40, 0.65)
    target_horizon = trial.suggest_int("target_horizon", 1, 3)

    # Feature selection
    use_rsi = trial.suggest_categorical("use_rsi", [True, False])
    use_macd = trial.suggest_categorical("use_macd", [True, False])
    use_bb = trial.suggest_categorical("use_bb", [True, False])
    use_vol = trial.suggest_categorical("use_vol", [True, False])
    use_lags = trial.suggest_categorical("use_lags", [True, False])

    selected = []
    if use_rsi:
        selected.append("rsi")
    if use_macd:
        selected.append("macd")
    if use_bb:
        selected.append("bb")
    if use_vol:
        selected.append("vol")
    if use_lags:
        selected.append("lags")

    train_feat = make_features(train_df, selected, target_horizon)
    val_feat = make_features(val_df, selected, target_horizon)

    feature_cols = [c for c in train_feat.columns if c != "target"]
    X_train = train_feat[feature_cols].values
    y_train = train_feat["target"].values
    X_val = val_feat[feature_cols].values
    y_val = val_feat["target"].values

    if X_train.shape[0] < 100 or X_val.shape[0] < 50:
        return -999.0

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)

    model = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        subsample=subsample,
        colsample_bytree=colsample_bytree,
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
        early_stopping_rounds=20,
    )
    model.fit(X_train_s, y_train, eval_set=[(X_val_s, y_val)], verbose=False)

    val_probs = model.predict_proba(X_val_s)[:, 1]
    signals = []
    for i, idx in enumerate(val_df.index):
        if i < len(val_probs):
            prob = val_probs[i]
            price = val_df.loc[idx, "close"]
            if prob > threshold:
                signals.append(("BUY", price))
            elif prob < (1 - threshold):
                signals.append(("SELL", price))

    result = vectorized_backtest(val_df["close"].tolist(), signals)
    if result["num_trades"] < 20:
        return -999.0
    return result["sharpe"]


def run_auto_ml(n_trials=30, n_jobs=4):
    print("Loading data...")
    files = glob.glob("data/raw/histdata/xauusd/DAT_ASCII_XAUUSD_M1_*.csv")
    df = pd.concat(
        [
            pd.read_csv(
                f,
                sep=";",
                header=None,
                names=["datetime", "open", "high", "low", "close", "volume"],
            )
            for f in files
        ],
        ignore_index=True,
    )
    df["datetime"] = pd.to_datetime(df["datetime"], format="%Y%m%d %H%M%S")
    df = df.set_index("datetime")
    df_h = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    print(f"Data: {len(df_h)} bars (4h)")

    split1 = int(len(df_h) * 0.7)
    split2 = int(len(df_h) * 0.85)
    train_df = df_h.iloc[:split1]
    val_df = df_h.iloc[split1:split2]
    test_df = df_h.iloc[split2:]
    print(f"Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")

    # Optuna study with parallel jobs
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(
        lambda trial: objective(trial, train_df, val_df),
        n_trials=n_trials,
        n_jobs=n_jobs,
        show_progress_bar=True,
    )

    print("\n" + "=" * 50)
    print("🏆 BEST PARAMETERS")
    print("=" * 50)
    for k, v in study.best_params.items():
        print(f"{k}: {v}")
    print(f"Best Validation Sharpe: {study.best_value:.4f}")

    # Test best model
    best = study.best_params
    threshold = best["threshold"]
    target_horizon = best["target_horizon"]
    selected = []
    if best.get("use_rsi"):
        selected.append("rsi")
    if best.get("use_macd"):
        selected.append("macd")
    if best.get("use_bb"):
        selected.append("bb")
    if best.get("use_vol"):
        selected.append("vol")
    if best.get("use_lags"):
        selected.append("lags")

    train_feat = make_features(train_df, selected, target_horizon)
    test_feat = make_features(test_df, selected, target_horizon)
    feature_cols = [c for c in train_feat.columns if c != "target"]
    X_train = train_feat[feature_cols].values
    y_train = train_feat["target"].values
    X_test = test_feat[feature_cols].values
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    model = XGBClassifier(
        n_estimators=best["n_estimators"],
        max_depth=best["max_depth"],
        learning_rate=best["learning_rate"],
        subsample=best["subsample"],
        colsample_bytree=best["colsample_bytree"],
        random_state=42,
        use_label_encoder=False,
        eval_metric="logloss",
    )
    model.fit(X_train_s, y_train)
    test_probs = model.predict_proba(X_test_s)[:, 1]
    signals = []
    for i, idx in enumerate(test_df.index):
        if i < len(test_probs):
            prob = test_probs[i]
            price = test_df.loc[idx, "close"]
            if prob > threshold:
                signals.append(("BUY", price))
            elif prob < (1 - threshold):
                signals.append(("SELL", price))

    test_result = vectorized_backtest(test_df["close"].tolist(), signals)
    print("\n📊 OUT-OF-SAMPLE TEST")
    print(f"Trades: {test_result['num_trades']}")
    print(f"Return: {test_result['total_return']:.2%}")
    print(f"Sharpe: {test_result['sharpe']:.2f}")
    print(f"Max DD: {test_result['max_drawdown']:.2%}")
    print(f"Win Rate: {test_result['win_rate']:.2%}")

    if test_result["num_trades"] >= 30 and test_result["sharpe"] > 0.5:
        print("✅ SUCCESS! Strategy works out-of-sample.")
    else:
        print("❌ FAILED. Still insufficient features.")


if __name__ == "__main__":
    run_auto_ml(n_trials=30, n_jobs=4)
