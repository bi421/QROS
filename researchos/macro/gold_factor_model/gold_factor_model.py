"""
Gold factor model - fixes ambiguous variable name I.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats


class GoldFactorModel:
    """
    Gold factor model for analyzing gold price movements.

    This model decomposes gold returns into factor exposures:
    - US Dollar index (DXY)
    - Real yields (TIPS)
    - Equity markets (SPX)
    - Volatility (VIX)
    - Oil prices
    """

    def __init__(
        self,
        factor_names: Optional[List[str]] = None,
        default_factors: bool = True,
    ):
        """Initialize the gold factor model."""

        if default_factors and factor_names is None:
            self.factor_names = [
                "dxy",
                "real_yield",
                "equities",
                "volatility",
                "oil",
            ]
        else:
            self.factor_names = factor_names or []

        self.model: dict[str, Any] | None = None
        self.coefficients: np.ndarray | None = None
        self.r_squared: float | None = None
        self.residuals: np.ndarray | None = None
        self.factor_returns: np.ndarray | None = None
        self.gold_returns: pd.Series | None = None
        self._is_fitted = False

    def fit(
        self,
        gold_data: pd.DataFrame,
        factor_data: Dict[str, pd.DataFrame],
        frequency: str = "daily",
        lookback: int = 252,
    ) -> "GoldFactorModel":
        """
        Fit the factor model.

        Parameters
        ----------
        gold_data : pd.DataFrame
            DataFrame with gold price data, must include 'close' column.
        factor_data : Dict[str, pd.DataFrame]
            Dictionary mapping factor names to DataFrames with factor returns.
        frequency : str
            Frequency of data ('daily', 'weekly', 'monthly').
        lookback : int
            Number of periods for rolling statistics.

        Returns
        -------
        GoldFactorModel
            Fitted model instance.
        """

        # Compute gold returns
        gold_returns = gold_data["close"].pct_change().dropna()

        # Compute factor returns and align
        factor_returns_dict: dict[str, pd.Series] = {}
        for name, df in factor_data.items():
            if name not in self.factor_names:
                continue
            if "close" in df.columns:
                factor_returns_dict[name] = df["close"].pct_change().dropna()
            elif "return" in df.columns:
                factor_returns_dict[name] = df["return"].dropna()

        # Align all data
        common_index = self.gold_returns.index
        for name, returns in factor_returns_dict.items():
            common_index = common_index.intersection(returns.index)

        gold_returns = gold_returns.loc[common_index]

        X_list: list[pd.Series] = [gold_returns]
        for name in self.factor_names:
            if name in factor_returns_dict:
                X_list.append(factor_returns_dict[name])
            else:
                X_list.append(pd.Series(0, index=common_index))

        factor_df = pd.concat(X_list, axis=1)
        factor_df.columns = ["gold"] + self.factor_names

        # Build design matrix (with intercept)
        X_design = pd.concat(
            [
                pd.Series(1, index=common_index),
                factor_df[self.factor_names],
            ],
            axis=1,
        )
        X_design.columns = ["intercept"] + self.factor_names

        y_arr = gold_returns.values

        # Ridge regression to handle multicollinearity
        lambda_ridge = 0.01
        eye_matrix = np.eye(X_design.shape[1])
        A = X_design.T @ X_design + lambda_ridge * eye_matrix
        b = X_design.T @ y_arr
        coeffs = np.linalg.solve(A, b)

        # Store results
        self.coefficients = coeffs
        self.factor_returns = factor_df.values
        self.residuals = y_arr - X_design.values @ coeffs

        # Compute R-squared
        ss_res = np.sum(self.residuals**2)
        ss_tot = np.sum((y_arr - np.mean(y_arr)) ** 2)
        self.r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        # Store model metadata
        self.model = {
            "coefficients": coeffs,
            "factor_names": self.factor_names,
            "r_squared": self.r_squared,
            "residual_std": np.std(self.residuals),
            "n_observations": len(y_arr),
            "lookback": lookback,
            "frequency": frequency,
        }

        self._is_fitted = True

        return self

    def predict(self, X_new: pd.DataFrame) -> np.ndarray:
        """
        Predict gold returns using the fitted model.

        Parameters
        ----------
        X_new : pd.DataFrame
            New factor data for prediction.

        Returns
        -------
        np.ndarray
            Predicted gold returns.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        if self.coefficients is None:
            raise RuntimeError("Model coefficients are unavailable.")

        # Add intercept column
        X_with_intercept = pd.concat(
            [
                pd.Series(1, index=X_new.index),
                X_new[self.factor_names],
            ],
            axis=1,
        )

        return X_with_intercept.values @ self.coefficients

    def explain_variance(self) -> Dict[str, float]:
        """
        Explain the variance contribution of each factor.

        Returns
        -------
        Dict[str, float]
            Dictionary mapping factor names to their variance contribution %.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        if self.factor_returns is None or self.coefficients is None:
            raise RuntimeError("Model fitted state is incomplete.")
        # Compute factor contributions
        factor_std = np.std(self.factor_returns, axis=0)
        coef_std_product = self.coefficients[1:] * factor_std  # Skip intercept

        # Normalize to percentage
        total = np.sum(np.abs(coef_std_product))
        if total > 0:
            contributions = (coef_std_product / total) * 100
        else:
            contributions = np.zeros(len(self.factor_names))

        return dict(zip(self.factor_names, contributions))

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the model fit.

        Returns
        -------
        Dict[str, Any]
            Model summary statistics.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")
        if self.coefficients is None or self.residuals is None or self.factor_returns is None or self.r_squared is None:
            raise RuntimeError("Fitted model state is incomplete.")

        # Compute t-statistics for coefficients
        n = len(self.residuals)
        p = len(self.coefficients)
        mse = np.sum(self.residuals**2) / (n - p)

        # Standard errors
        try:
            var_covar = mse * np.linalg.inv(self.factor_returns.T @ self.factor_returns)
            se = np.sqrt(np.diag(var_covar))
            t_stats = self.coefficients / se
            p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df=n - p))
        except np.linalg.LinAlgError:
            t_stats = np.zeros(p)
            p_values = np.ones(p)

        # Factor correlations
        corr_matrix = np.corrcoef(self.factor_returns.T)

        return {
            "r_squared": float(self.r_squared),
            "adjusted_r_squared": float(1 - (1 - self.r_squared) * (n - 1) / (n - p - 1)),
            "residual_std": float(np.std(self.residuals)),
            "n_observations": n,
            "factor_names": self.factor_names,
            "coefficients": {name: float(self.coefficients[i + 1]) for i, name in enumerate(self.factor_names)},
            "t_statistics": {"intercept": float(t_stats[0]), **{name: float(t_stats[i + 1]) for i, name in enumerate(self.factor_names)}},
            "p_values": {"intercept": float(p_values[0]), **{name: float(p_values[i + 1]) for i, name in enumerate(self.factor_names)}},
            "variance_explanation": self.explain_variance(),
            "factor_correlations": corr_matrix.tolist(),
        }

    def plot_diagnostic(self, save_path: Optional[str] = None) -> None:
        """
        Create diagnostic plots for the model.

        Parameters
        ----------
        save_path : str, optional
            Path to save the plot. If None, display the plot.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        try:
            import matplotlib.pyplot as plt
        except ImportError:
            raise ImportError("matplotlib is required for plotting")

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # 1. Residuals vs Fitted
        ax1 = axes[0, 0]
        ax1.scatter(self.predict(pd.DataFrame(self.factor_returns, columns=self.factor_names)), self.residuals, alpha=0.5)
        ax1.axhline(y=0, color="r", linestyle="--")
        ax1.set_xlabel("Fitted Values")
        ax1.set_ylabel("Residuals")
        ax1.set_title("Residuals vs Fitted")

        # 2. Histogram of Residuals
        ax2 = axes[0, 1]
        ax2.hist(self.residuals, bins=30, density=True, alpha=0.7)
        ax2.set_xlabel("Residual")
        ax2.set_ylabel("Density")
        ax2.set_title("Residual Distribution")

        # 3. QQ Plot
        ax3 = axes[1, 0]
        stats.probplot(self.residuals, dist="norm", plot=ax3)
        ax3.set_title("Q-Q Plot")

        # 4. Factor Contributions
        ax4 = axes[1, 1]
        contributions = self.explain_variance()
        ax4.bar(contributions.keys(), contributions.values())
        ax4.set_xlabel("Factor")
        ax4.set_ylabel("Variance Contribution (%)")
        ax4.set_title("Factor Variance Explanation")
        ax4.tick_params(axis="x", rotation=45)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            plt.close()
        else:
            plt.show()

    def forecast(
        self,
        future_factors: pd.DataFrame,
        periods: int = 20,
    ) -> pd.Series:
        """
        Forecast future gold returns.

        Parameters
        ----------
        future_factors : pd.DataFrame
            Future factor data.
        periods : int
            Number of periods to forecast.

        Returns
        -------
        pd.Series
            Forecasted gold returns.
        """
        if not self._is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        if len(future_factors) < periods:
            raise ValueError(f"future_factors must have at least {periods} rows")

        future_factor_df = future_factors.iloc[-periods:][self.factor_names]
        predictions = self.predict(future_factor_df)

        return pd.Series(predictions, index=future_factors.index[-periods:])


def run_gold_factor_analysis(
    gold_prices: pd.DataFrame,
    factor_data: Dict[str, pd.DataFrame],
    lookback: int = 252,
) -> Dict[str, Any]:
    """
    Run gold factor analysis.

    Parameters
    ----------
    gold_prices : pd.DataFrame
        Gold price data with 'close' column.
    factor_data : Dict[str, pd.DataFrame]
        Factor data dictionary.
    lookback : int
        Lookback period for analysis.

    Returns
    -------
    Dict[str, Any]
        Analysis results.
    """
    model = GoldFactorModel()
    model.fit(gold_prices, factor_data, lookback=lookback)

    summary = model.get_summary()

    return {
        "model_summary": summary,
        "r_squared": summary["r_squared"],
        "adjusted_r_squared": summary["adjusted_r_squared"],
        "factor_contributions": summary["variance_explanation"],
        "significant_factors": [name for name, p in summary["p_values"].items() if p < 0.05 and name != "intercept"],
    }


if __name__ == "__main__":
    # Example usage
    np.random.seed(42)
    n_days = 500

    # Generate sample data
    gold_prices = pd.DataFrame(
        {
            "close": 1800 * np.exp(np.cumsum(np.random.randn(n_days) * 0.005)),
        },
        index=pd.date_range("2023-01-01", periods=n_days, freq="D"),
    )

    factor_data = {
        "dxy": pd.DataFrame(
            {
                "close": 104 * np.exp(np.cumsum(np.random.randn(n_days) * 0.003)),
            }
        ),
        "real_yield": pd.DataFrame(
            {
                "close": 2.0 + np.cumsum(np.random.randn(n_days) * 0.01),
            }
        ),
        "equities": pd.DataFrame(
            {
                "close": 4500 * np.exp(np.cumsum(np.random.randn(n_days) * 0.008)),
            }
        ),
        "volatility": pd.DataFrame(
            {
                "close": 20 + np.cumsum(np.random.randn(n_days) * 0.5),
            }
        ),
        "oil": pd.DataFrame(
            {
                "close": 80 * np.exp(np.cumsum(np.random.randn(n_days) * 0.01)),
            }
        ),
    }

    results = run_gold_factor_analysis(gold_prices, factor_data)
    print(json.dumps(results, indent=2, default=str))


def generate_economic_calendar():
    """Stub: Economic calendar events generator."""
    return pd.DataFrame()


def generate_xauusd_synthetic(n_days=1000, seed=42):
    """Stub: Generate synthetic XAUUSD data."""
    import numpy as np

    np.random.seed(seed)
    dates = pd.date_range("2021-01-01", periods=n_days, freq="D")
    df = pd.DataFrame({"close": 1800 + np.cumsum(np.random.normal(0, 5, n_days)), "open": 1800 + np.cumsum(np.random.normal(0, 5, n_days)), "high": 1800 + np.cumsum(np.random.normal(0, 5, n_days)) + 10, "low": 1800 + np.cumsum(np.random.normal(0, 5, n_days)) - 10, "volume": np.random.uniform(50000, 200000, n_days)}, index=dates)
    df.index.name = "date"
    return df


def run_factor_regression(df, factor_cols):
    """Stub: Run factor regression analysis."""
    return {"coefficients": {}, "r_squared": 0.0}


def run_regime_dependent_regression(df, factor_cols, regime_col):
    """Stub: Run regime-dependent regression."""
    return {"regimes": {}, "coefficients": {}}
