"""
ML-based strategy that integrates with BacktestEngine.
"""

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from .features import create_features
from .model import predict


@dataclass
class Signal:
    action: str
    price: float
    timestamp: Any = None


class MLStrategy:
    def __init__(self, model, scaler, feature_names, threshold=0.55):
        self.model = model
        self.scaler = scaler
        self.feature_names = feature_names
        self.threshold = threshold

    def generate_signals(self, prices: Sequence[float]) -> list[Signal]:
        if len(prices) < 50:
            return []

        df = pd.DataFrame({"close": prices})
        df_feat = create_features(df)
        if df_feat.empty:
            return []

        probs, preds = predict(self.model, self.scaler, df_feat, self.feature_names)
        valid_idx = df_feat.index
        signals = []
        for i, idx in enumerate(valid_idx):
            if i < len(probs):
                prob = probs[i]
                price = df_feat.loc[idx, "close"]
                # Зөвхөн BUY дохио (өсөх магадлал өндөр үед)
                if prob > self.threshold:
                    signals.append(Signal(action="BUY", price=price))
                # SELL дохиог гаргахгүй – позицоо хаах нь бэктестэд тулгуурлана
        return signals
