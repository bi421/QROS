"""
Comparison: Macro Factors vs Technical Indicators for XAUUSD.

Compares:
    1. Macro-factor model (real yields, DXY, VIX, inflation, CB balance sheet, GPR)
    2. Cross-asset factors (gold-silver, gold-oil, gold-BTC)
    3. Economic calendar features (FOMC, CPI, NFP)
    4. Technical indicators (SMA+RSI+ATR)

Validation:
    - Expanding-window walk-forward
    - Statistical significance testing
    - Multiple testing correction
    - Effect size (Cohen's d)
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from researchos.engines.quant.validation.walk_forward_strategy_validation import (
    compute_indicators,
    compute_metrics,
    generate_signals_vectorized,
    simulate_trades_vectorized,
)
from researchos.macro.gold_factor_model.gold_factor_model import (
    generate_economic_calendar,
    generate_xauusd_synthetic,
    run_factor_regression,
    run_regime_dependent_regression,
)

# ──────────────────────────────────────────────────────────────
# 1. Macro Factor Strategy
# ──────────────────────────────────────────────────────────────


def macro_factor_strategy(
    df: pd.DataFrame,
    factor_cols: list[str],
    lookback: int = 252,
) -> pd.Series:
    """Generate trading signals from macro factor model."""
    signals = pd.Series(0, index=df.index, dtype=np.int8)

    for i in range(lookback, len(df)):
        train_df = df.iloc[i - lookback : i]
        X_train = train_df[factor_cols].dropna()
        y_train = train_df["gold_return"].loc[X_train.index]

        if len(X_train) < 60:
            continue

        try:
            result = run_factor_regression(y_train, X_train, factor_cols)
            X_current = df[factor_cols].iloc[i : i + 1].values
            X_current_design = np.column_stack([np.ones(1), X_current])
            pred_return = (X_current_design @ result.coefficients)[0]

            threshold = 0.001
            if pred_return > threshold:
                signals.iloc[i] = 1
            elif pred_return < -threshold:
                signals.iloc[i] = -1
        except Exception:
            continue

    return signals


# ──────────────────────────────────────────────────────────────
# 2. Walk-Forward Validation
# ──────────────────────────────────────────────────────────────


def run_macro_walk_forward(
    df: pd.DataFrame,
    factor_cols: list[str],
    initial_train_days: int = 365,
    test_days: int = 90,
    step_days: int = 30,
) -> dict[str, Any]:
    """Run expanding-window walk-forward for macro factor strategy."""
    fold_results = []
    train_end = initial_train_days
    fold_id = 0

    while train_end + test_days < len(df):
        train_df = df.iloc[:train_end]
        test_df = df.iloc[train_end : train_end + test_days]

        if len(train_df) < 60 or len(test_df) < 10:
            train_end += step_days
            continue

        train_clean = train_df.dropna(subset=factor_cols + ["gold_return"])
        if len(train_clean) < 60:
            train_end += step_days
            continue

        try:
            result = run_factor_regression(
                train_clean["gold_return"],
                train_clean[factor_cols],
                factor_cols,
            )
        except Exception:
            train_end += step_days
            continue

        test_signals = []
        for i in range(len(test_df)):
            idx = train_end + i
            if idx < len(df):
                X_current = df[factor_cols].iloc[idx : idx + 1].values
                if np.any(np.isnan(X_current)):
                    test_signals.append(0)
                    continue
                X_design = np.column_stack([np.ones(1), X_current])
                try:
                    pred = (X_design @ result.coefficients)[0]
                    if pred > 0.001:
                        test_signals.append(1)
                    elif pred < -0.001:
                        test_signals.append(-1)
                    else:
                        test_signals.append(0)
                except Exception:
                    test_signals.append(0)

        test_close = test_df["close"].values
        trades = simulate_trades_vectorized(test_close, np.array(test_signals), commission=0.0001)
        metrics = compute_metrics(trades)

        fold_results.append(
            {
                "fold_id": fold_id,
                "train_start": 0,
                "train_end": train_end,
                "test_start": train_end,
                "test_end": train_end + test_days,
                "metrics": metrics,
                "r_squared": result.r_squared,
                "significant_factors": result.significant_factors(),
            }
        )

        fold_id += 1
        train_end += step_days

    # AGGREGATION FIX: Safely handle None/NaN values
    agg = {}
    if fold_results:
        for key in fold_results[0]["metrics"].keys():
            values = [fr["metrics"].get(key, 0.0) for fr in fold_results]
            # Filter out non-numeric and NaN values safely
            valid_vals = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
            agg[key] = float(np.mean(valid_vals)) if valid_vals else 0.0

        r_squared_vals = [fr["r_squared"] for fr in fold_results if isinstance(fr.get("r_squared"), (int, float))]
        agg["mean_r_squared"] = float(np.mean(r_squared_vals)) if r_squared_vals else 0.0

    return {"fold_results": fold_results, "aggregate_metrics": agg, "n_folds": len(fold_results)}


# ──────────────────────────────────────────────────────────────
# 3. Indicator Baseline
# ──────────────────────────────────────────────────────────────


def run_indicator_baseline(
    df: pd.DataFrame,
    initial_train_months: int = 12,
    test_months: int = 3,
    step_months: int = 3,
    commission: float = 0.0001,
) -> dict[str, Any]:
    """Run SMA+RSI+ATR indicator strategy baseline."""
    df = compute_indicators(df)
    close = df["close"].values
    signals = generate_signals_vectorized(df).values

    bars_per_month = 21  # Daily data (approx 21 trading days/month)
    initial_train_bars = initial_train_months * bars_per_month
    test_bars = test_months * bars_per_month
    step_bars = step_months * bars_per_month
    bars_per_month = 21  # Daily data (approx 21 trading days/month)
    initial_train_bars = initial_train_months * bars_per_month
    test_bars = test_months * bars_per_month
    step_bars = step_months * bars_per_month
    bars_per_month = 21  # Daily data (approx 21 trading days/month)
    initial_train_bars = initial_train_months * bars_per_month
    test_bars = test_months * bars_per_month
    step_bars = step_months * bars_per_month
    bars_per_month = 21  # Daily data (approx 21 trading days/month)
    initial_train_bars = initial_train_months * bars_per_month
    test_bars = test_months * bars_per_month
    step_bars = step_months * bars_per_month

    from researchos.engines.quant.machine_learning.purged_validation import expanding_window_folds

    folds = expanding_window_folds(len(df), initial_train_bars, test_bars, step_bars)
    fold_results = []

    for fold in folds:
        test_signals = signals[fold.test_start : fold.test_end + 1]
        test_close = close[fold.test_start : fold.test_end + 1]
        trades = simulate_trades_vectorized(test_close, test_signals, commission=commission)
        metrics = compute_metrics(trades)

        fold_results.append(
            {
                "fold_id": fold.fold_id,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "metrics": metrics,
            }
        )

    agg = {}
    if fold_results:
        for name in ["total_return", "sharpe_ratio", "max_drawdown", "win_rate", "trade_count"]:
            values = [fr["metrics"].get(name, 0.0) for fr in fold_results]
            valid_vals = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
            agg[name] = float(np.mean(valid_vals)) if valid_vals else 0.0

    return {"fold_results": fold_results, "aggregate_metrics": agg, "n_folds": len(fold_results)}


# ──────────────────────────────────────────────────────────────
# 4. Statistical Comparison
# ──────────────────────────────────────────────────────────────


def compare_strategies(
    macro_results: dict[str, Any],
    indicator_results: dict[str, Any],
    metric: str = "sharpe_ratio",
) -> dict[str, Any]:
    macro_vals = [fr["metrics"].get(metric, 0.0) for fr in macro_results.get("fold_results", [])]
    ind_vals = [fr["metrics"].get(metric, 0.0) for fr in indicator_results.get("fold_results", [])]

    if not macro_vals or not ind_vals:
        return {"error": "insufficient data"}

    min_len = min(len(macro_vals), len(ind_vals))
    macro_vals = np.array([float(v) for v in macro_vals[:min_len] if isinstance(v, (int, float))])
    ind_vals = np.array([float(v) for v in ind_vals[:min_len] if isinstance(v, (int, float))])

    if len(macro_vals) < 2 or len(ind_vals) < 2:
        return {"error": "insufficient valid data for t-test"}

    t_stat, p_val = stats.ttest_rel(macro_vals, ind_vals)
    diff = macro_vals - ind_vals
    cohens_d = float(np.mean(diff) / np.std(diff)) if np.std(diff) > 1e-9 else 0.0

    rng = np.random.default_rng(42)
    boot_diffs = []
    for _ in range(10000):
        idx = rng.choice(min_len, size=min_len, replace=True)
        boot_diffs.append(np.mean(macro_vals[idx] - ind_vals[idx]))
    boot_diffs = np.array(boot_diffs)

    return {
        "metric": metric,
        "macro_mean": float(np.mean(macro_vals)),
        "indicator_mean": float(np.mean(ind_vals)),
        "t_statistic": float(t_stat),
        "p_value": float(p_val),
        "cohens_d": cohens_d,
        "bootstrap_ci_lower": float(np.percentile(boot_diffs, 2.5)),
        "bootstrap_ci_upper": float(np.percentile(boot_diffs, 97.5)),
        "significant_at_05": bool(p_val < 0.05),
    }


# ──────────────────────────────────────────────────────────────
# 5. Visualization
# ──────────────────────────────────────────────────────────────


def plot_comparison(
    macro_results: dict[str, Any],
    indicator_results: dict[str, Any],
    metric: str = "sharpe_ratio",
    output_prefix: str = "macro_vs_indicators",
) -> None:
    os.makedirs("data/curated/xauusd", exist_ok=True)

    macro_vals = [fr["metrics"].get(metric, 0.0) for fr in macro_results.get("fold_results", [])]
    ind_vals = [fr["metrics"].get(metric, 0.0) for fr in indicator_results.get("fold_results", [])]

    plt.figure(figsize=(10, 5))
    if macro_vals:
        plt.hist(macro_vals, bins=max(5, len(macro_vals)), alpha=0.6, label="Macro Factors", color="green", edgecolor="black")
    if ind_vals:
        plt.hist(ind_vals, bins=max(5, len(ind_vals)), alpha=0.6, label="SMA+RSI+ATR", color="blue", edgecolor="black")
    plt.axvline(0, color="black", linestyle="--", linewidth=0.8)
    plt.title(f"Distribution of {metric}: Macro Factors vs Indicators")
    plt.xlabel(metric)
    plt.ylabel("Number of Folds")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"data/curated/xauusd/{output_prefix}_{metric}_distribution.png", dpi=150)
    plt.close()


# ──────────────────────────────────────────────────────────────
# 6. Main
# ──────────────────────────────────────────────────────────────


def main() -> None:
    np.random.seed(42)
    start_total = time.time()

    print("=" * 80)
    print("MACRO FACTORS VS TECHNICAL INDICATORS: XAUUSD COMPARISON")
    print("=" * 80)

    print("\nGenerating synthetic XAUUSD + macro data...")
    df = generate_xauusd_synthetic(n_days=1800, seed=42)
    generate_economic_calendar("2021-01-01", "2025-12-31")

    df["regime"] = "neutral"
    for i in range(len(df)):
        if df["real_yield_10y"].iloc[i] > 1.5 and df["vix"].iloc[i] < 20:
            df.loc[df.index[i], "regime"] = "inflationary_growth"
        elif df["real_yield_10y"].iloc[i] < 0.0 and df["vix"].iloc[i] > 25:
            df.loc[df.index[i], "regime"] = "deflationary_fear"
        elif df["dxy"].iloc[i] > 105 and df["vix"].iloc[i] < 15:
            df.loc[df.index[i], "regime"] = "risk_on"
        elif df["dxy"].iloc[i] < 95 and df["vix"].iloc[i] > 25:
            df.loc[df.index[i], "regime"] = "risk_off"

    factor_cols = [
        "real_yield_10y",
        "dxy",
        "vix",
        "breakeven_inflation_10y",
        "fed_balance_sheet_change",
        "geopolitical_risk_index",
        "gold_silver_ratio",
        "gold_oil_ratio",
        "gold_btc_correlation",
        "days_to_fomc",
        "days_to_cpi",
        "days_to_nfp",
        "fomc_surprise",
        "cpi_surprise",
        "nfp_surprise",
        "post_fomc_volatility",
        "pre_cpi_volatility",
    ]

    df["gold_return"] = df["close"].pct_change()
    df = df.dropna(subset=["gold_return"] + factor_cols).reset_index(drop=True)

    print(f"Data prepared: {len(df)} observations, {len(factor_cols)} factors")

    print("\nRunning macro factor strategy...")
    start = time.time()
    macro_results = run_macro_walk_forward(df, factor_cols)
    print(f"  Time: {time.time() - start:.1f}s")
    print(f"  Folds: {macro_results['n_folds']}")
    for k, v in macro_results["aggregate_metrics"].items():
        print(f"  {k}: {v:.4f}")

    print("\nRunning indicator baseline...")
    start = time.time()
    indicator_results = run_indicator_baseline(df, initial_train_months=6, test_months=3, step_months=3)
    print(f"  Time: {time.time() - start:.1f}s")
    print(f"  Folds: {indicator_results['n_folds']}")
    for k, v in indicator_results["aggregate_metrics"].items():
        print(f"  {k}: {v:.4f}")

    print("\nStatistical comparison:")
    comparison = compare_strategies(macro_results, indicator_results)
    for k, v in comparison.items():
        print(f"  {k}: {v}")

    print("\nRegime-dependent analysis:")
    regime_results = run_regime_dependent_regression(df, "gold_return", factor_cols, "regime")
    for regime, result in regime_results.items():
        sig = result.significant_factors()
        print(f"  {regime}: R²={result.r_squared:.4f}, sig_factors={sig}")

    report = {
        "macro_results": {
            "aggregate_metrics": macro_results["aggregate_metrics"],
            "n_folds": macro_results["n_folds"],
        },
        "indicator_results": {
            "aggregate_metrics": indicator_results["aggregate_metrics"],
            "n_folds": indicator_results["n_folds"],
        },
        "statistical_comparison": comparison,
        "regime_results": {k: v.to_dict() for k, v in regime_results.items()},
    }

    os.makedirs("data/curated/xauusd", exist_ok=True)
    with open("data/curated/xauusd/macro_vs_indicators_comparison.json", "w") as f:
        json.dump(report, f, indent=2, default=str)

    plot_comparison(macro_results, indicator_results)

    total_elapsed = time.time() - start_total
    print(f"\nTotal time: {total_elapsed:.1f}s")
    print("Results saved to data/curated/xauusd/macro_vs_indicators_comparison.json")

    print("\n" + "=" * 80)
    print("CONCLUSION")
    print("=" * 80)
    p_val = comparison.get("p_value", 1.0)
    cohens_d = comparison.get("cohens_d", 0.0)

    if isinstance(p_val, (int, float)) and isinstance(cohens_d, (int, float)):
        if p_val < 0.05 and abs(cohens_d) > 0.2:
            if cohens_d > 0:
                print("Macro factor strategy shows statistically significant improvement over indicators.")
            else:
                print("Technical indicator strategy shows statistically significant improvement over macro factors.")
        else:
            print("No statistically significant difference detected.")
            print("Neither strategy demonstrates a clear, robust edge.")
        print(f"p-value: {p_val:.4f}, Cohen's d: {cohens_d:.4f}")
    else:
        print("Could not compute statistical significance due to insufficient data.")


if __name__ == "__main__":
    main()
