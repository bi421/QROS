"""Train and predict using ML models."""

from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler


def train_model(
    df: pd.DataFrame,
    model_type: str = "random_forest",
    test_size: float = 0.3,
    random_state: int = 42,
) -> tuple[Any, Any, dict[str, Any]]:
    feature_cols = [col for col in df.columns if col not in ["target", "datetime"]]
    X = df[feature_cols].values
    y = df["target"].values

    split_idx = int(len(X) * (1 - test_size))
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    if model_type == "random_forest":
        model = RandomForestClassifier(n_estimators=150, max_depth=10, min_samples_split=10, random_state=random_state)
    elif model_type == "xgboost":
        try:
            from xgboost import XGBClassifier

            model = XGBClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=6,
                random_state=random_state,
                use_label_encoder=False,
                eval_metric="logloss",
            )
        except ImportError:
            raise ImportError("XGBoost is required. Install it with 'pip install xgboost'.")
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    model.fit(X_train_scaled, y_train)

    train_acc = accuracy_score(y_train, model.predict(X_train_scaled))
    test_acc = accuracy_score(y_test, model.predict(X_test_scaled))

    metrics = {
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "feature_names": feature_cols,
    }
    return model, scaler, metrics


def predict(
    model: Any,
    scaler: Any,
    df: pd.DataFrame,
    feature_names: list[str],
) -> tuple[Any, Any]:
    X = df[feature_names].values
    X_scaled = scaler.transform(X)
    probs = model.predict_proba(X_scaled)[:, 1]
    preds = model.predict(X_scaled)
    return probs, preds


def save_model(
    model: Any,
    scaler: Any,
    metrics: Any,
    filepath: str = "ml_model.pkl",
) -> None:
    joblib.dump({"model": model, "scaler": scaler, "metrics": metrics}, filepath)


def load_model(filepath: str = "ml_model.pkl") -> tuple[Any, Any, Any]:
    data = joblib.load(filepath)
    return data["model"], data["scaler"], data["metrics"]
