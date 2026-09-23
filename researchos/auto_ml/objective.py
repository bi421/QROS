import numpy as np\nfrom typing import Any
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from researchos.ml_engine.strategy import Signal
from researchos.quant_engine.backtest import BacktestEngine


class Objective:
    def __init__(self, df_h: pd.DataFrame, train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame, feature_cols: list[str]) -> None:
        self.df_h = df_h
        self.train_df = train_df
        self.val_df = val_df
        self.test_df = test_df
        self.feature_cols = feature_cols

    def make_features(self, df: pd.DataFrame, selected_cols: list[str], target_horizon: int = 1) -> pd.DataFrame:
        df = df.copy()
        close = df["close"]
        # Үндсэн feature-үүд (заавал байх ёстой)
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

        # Зөвхөн сонгогдсон feature-үүдийг үлдээх
        keep_cols = ["ret1", "rsi", "macd", "macd_signal", "macd_diff", "bb_pos", "volatility"]
        if selected_cols:
            keep_cols = [c for c in keep_cols if c in selected_cols] + [f"ret_lag_{lag}" for lag in [1, 2, 3, 5, 10, 20] if f"ret_lag_{lag}" in selected_cols]
        else:
            keep_cols = keep_cols + [f"ret_lag_{lag}" for lag in [1, 2, 3, 5, 10, 20]]

        # Target (дараагийн N лаа)
        df["target"] = (close.shift(-target_horizon) > close).astype(int)
        df = df.replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        return df[keep_cols + ["target"]]

    def __call__(self, trial: Any) -> float:
        # Hyperparameter search space
        n_estimators = trial.suggest_int("n_estimators", 50, 300, step=50)
        max_depth = trial.suggest_int("max_depth", 3, 12)
        learning_rate = trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
        subsample = trial.suggest_float("subsample", 0.6, 1.0)
        colsample_bytree = trial.suggest_float("colsample_bytree", 0.6, 1.0)
        threshold = trial.suggest_float("threshold", 0.40, 0.65)
        target_horizon = trial.suggest_int("target_horizon", 1, 3)

        # Feature selection (аль үзүүлэлтийг оруулах)
        use_rsi = trial.suggest_categorical("use_rsi", [True, False])
        use_macd = trial.suggest_categorical("use_macd", [True, False])
        use_bb = trial.suggest_categorical("use_bb", [True, False])
        use_vol = trial.suggest_categorical("use_vol", [True, False])
        use_lags = trial.suggest_categorical("use_lags", [True, False])

        selected = []
        if use_rsi:
            selected.append("rsi")
        if use_macd:
            selected.extend(["macd", "macd_signal", "macd_diff"])
        if use_bb:
            selected.append("bb_pos")
        if use_vol:
            selected.append("volatility")
        if use_lags:
            selected.extend(["ret_lag_1", "ret_lag_2", "ret_lag_3", "ret_lag_5", "ret_lag_10", "ret_lag_20"])

        # Train features
        train_feat = self.make_features(self.train_df, selected, target_horizon)
        val_feat = self.make_features(self.val_df, selected, target_horizon)
        self.make_features(self.test_df, selected, target_horizon)

        feature_cols = [c for c in train_feat.columns if c != "target"]
        X_train = train_feat[feature_cols].values
        y_train = train_feat["target"].values
        X_val = val_feat[feature_cols].values
        y_val = val_feat["target"].values

        if X_train.shape[0] < 100 or X_val.shape[0] < 50:
            return -999.0

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_val_s = scaler.transform(X_val)

        # Train model
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

        # Validation дээр дохио үүсгэх
        val_probs = model.predict_proba(X_val_s)[:, 1]
        signals = []
        for i, idx in enumerate(self.val_df.index):
            if i < len(val_probs):
                prob = val_probs[i]
                price = self.val_df.loc[idx, "close"]
                if prob > threshold:
                    signals.append(Signal("BUY", price))
                elif prob < (1 - threshold):
                    signals.append(Signal("SELL", price))

        class TempStrategy:
            def generate_signals(self, prices):
                return signals

        engine = BacktestEngine()
        result = engine.run(self.val_df["close"].tolist(), TempStrategy())

        # Шийтгэл: цөөн трейд бол шийтгэх, Sharpe-г нэмэгдүүлэх
        if result.num_trades < 20:
            return -999.0

        # Validation Sharpe (өндөр байх тусмаа сайн)
        return result.sharpe_ratio
