from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.models import Sequential


class LSTMPredictor:
    def __init__(self, lookback: int = 60) -> None:
        self.lookback = lookback
        self.model: Any = None
        self.scaler = MinMaxScaler()

    def prepare_data(
        self, df: pd.DataFrame, target: str = "close"
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        data = df[target].values.reshape(-1, 1)
        data_scaled = self.scaler.fit_transform(data)
        X, y = [], []
        for i in range(self.lookback, len(data_scaled)):
            X.append(data_scaled[i - self.lookback : i, 0])
            y.append(data_scaled[i, 0])
        return np.array(X), np.array(y)

    def build_model(self, input_shape: tuple[int, ...]) -> Any:
        model = Sequential(
            [
                LSTM(50, return_sequences=True, input_shape=(input_shape[0], 1)),
                Dropout(0.2),
                LSTM(50, return_sequences=False),
                Dropout(0.2),
                Dense(1),
            ]
        )
        model.compile(optimizer="adam", loss="mse")
        self.model = model
        return model

    def train(
        self,
        X: np.ndarray[Any, Any],
        y: np.ndarray[Any, Any],
        epochs: int = 50,
        batch_size: int = 32,
    ) -> None:
        if self.model is None:
            raise RuntimeError("Model must be built before training.")
        es = EarlyStopping(patience=5, restore_best_weights=True)
        self.model.fit(
            X,
            y,
            epochs=epochs,
            batch_size=batch_size,
            validation_split=0.1,
            callbacks=[es],
            verbose=0,
        )

    def predict(self, X: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        if self.model is None:
            raise RuntimeError("Model must be built before prediction.")
        return self.scaler.inverse_transform(self.model.predict(X, verbose=0))
