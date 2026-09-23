import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from researchos.quant_engine.vectorized_backtest import vectorized_backtest


def make_features(df: pd.DataFrame, selected: list[str], target_horizon: int = 1) -> pd.DataFrame:
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
    df["target"] = (close.shift(-target_horizon) > close).astype(int)
    df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
    return df[keep_cols + ["target"]]


class AutoMLObjective:
    def __init__(self, train_df: pd.DataFrame, val_df: pd.DataFrame) -> None:
        self.train_df = train_df
        self.val_df = val_df

    def __call__(self, trial: Any) -> float:
        n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
        max_depth = trial.suggest_int("max_depth", 3, 12)
        trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
        threshold = trial.suggest_float("threshold", 0.40, 0.65)
        target_horizon = trial.suggest_int("target_horizon", 1, 3)
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
        train_feat = make_features(self.train_df, selected, target_horizon)
        val_feat = make_features(self.val_df, selected, target_horizon)
        feature_cols = [c for c in train_feat.columns if c != "target"]
        X_train = train_feat[feature_cols].values
        y_train = train_feat["target"].values
        X_val = val_feat[feature_cols].values
        if X_train.shape[0] < 100 or X_val.shape[0] < 50:
            return -999.0
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_val_s = scaler.transform(X_val)
        model = RandomForestClassifier(n_estimators=n_estimators, max_depth=max_depth, random_state=42)
        model.fit(X_train_s, y_train)
        val_probs = model.predict_proba(X_val_s)[:, 1]
        signals = []
        for i, idx in enumerate(self.val_df.index):
            if i < len(val_probs):
                prob = val_probs[i]
                price = self.val_df.loc[idx, "close"]
                if prob > threshold:
                    signals.append(("BUY", price))
                elif prob < (1 - threshold):
                    signals.append(("SELL", price))
        result = vectorized_backtest(self.val_df["close"].tolist(), signals)
        if result["num_trades"] < 20:
            return -999.0
        return result["sharpe"]
