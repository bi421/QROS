"""
Compute macro relationships: correlation, rolling correlation, z-score.
"""

from typing import cast

import pandas as pd


class MacroAnalyzer:
    """Analyze macro factors correlation with XAUUSD."""

    @staticmethod
    def compute_correlation(df: pd.DataFrame, target: str = "XAUUSD") -> dict[str, float]:
        """Compute correlation between target and all other factors."""
        correlations = df.corr()[target].drop(target).to_dict()
        return cast(dict[str, float], correlations)

    @staticmethod
    def compute_rolling_correlation(
        df: pd.DataFrame,
        target: str = "XAUUSD",
        window: int = 30,
    ) -> pd.DataFrame:
        """Rolling correlation over time window."""
        rolling_corr = {}
        for col in df.columns:
            if col != target:
                rolling_corr[col] = df[target].rolling(window).corr(df[col])
        return pd.DataFrame(rolling_corr)

    @staticmethod
    def compute_zscore(df: pd.DataFrame, window: int = 30) -> pd.DataFrame:
        """Z-score normalization for each factor."""
        return df.apply(lambda x: (x - x.rolling(window).mean()) / x.rolling(window).std())
