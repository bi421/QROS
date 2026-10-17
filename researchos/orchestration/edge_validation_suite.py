"""Fail-closed statistical validation suite for QROS research hypotheses.

This module is research-only: it never places orders and never authorizes execution.
It combines net-PnL diagnostics, fractional Kelly sizing, streak dependence,
five overfitting stress tests, moving-block bootstrap, and a strict decision gate.

Important: a 90% robustness score is a diagnostic threshold, not a 90% probability
that a strategy is real. Statistical significance does not establish causality.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

EDGE_VALIDATION_SUITE_VERSION = "EDGE_VALIDATION_SUITE_V1"


def _validate_returns(values: Sequence[float], *, minimum: int = 1) -> list[float]:
    if len(values) < minimum:
        raise ValueError(f"INSUFFICIENT_OBSERVATIONS:{minimum}")
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("INVALID_RETURN")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("NONFINITE_RETURN")
        result.append(number)
    return result


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("EMPTY_QUANTILE_SAMPLE")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def quarter_kelly(
    outcomes: Sequence[float],
    *,
    fraction: float = 0.25,
    max_fraction: float = 0.01,
    minimum_trades: int = 100,
) -> dict[str, Any]:
    """Estimate quarter-Kelly from net trade outcomes, expressed in R units.

    Full Kelly for binary win/loss outcomes is p - (1-p)/b, where b is the
    mean win divided by absolute mean loss. Mixed/non-binary outcomes are
    approximated by win probability and conditional average win/loss; this is
    a diagnostic approximation and must not be mistaken for general optimal
    sizing under arbitrary payoff distributions.
    """
    pnl = _validate_returns(outcomes, minimum=1)
    for name, value in (("fraction", fraction), ("max_fraction", max_fraction)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"INVALID_{name.upper()}")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("FRACTION_MUST_BE_IN_(0,1]")
    if not 0.0 < max_fraction <= 1.0:
        raise ValueError("MAX_FRACTION_MUST_BE_IN_(0,1]")
    if (
        isinstance(minimum_trades, bool)
        or not isinstance(minimum_trades, int)
        or minimum_trades < 1
    ):
        raise ValueError("MINIMUM_TRADES_MUST_BE_POSITIVE")

    wins = [value for value in pnl if value > 0]
    losses = [-value for value in pnl if value < 0]
    n = len(pnl)
    p = len(wins) / n
    mean_win = _mean(wins)
    mean_loss = _mean(losses)
    if not wins or not losses or mean_loss <= 0.0:
        return {
            "status": "INSUFFICIENT_PAYOFF_DIVERSITY",
            "n": n,
            "win_probability": p,
            "mean_win": mean_win,
            "mean_loss_abs": mean_loss,
            "full_kelly_fraction": None,
            "fractional_kelly_fraction": None,
            "applied_fraction_after_cap": 0.0,
            "decision": "NO_BET",
            "research_only": True,
        }
    payout_ratio = mean_win / mean_loss
    full_kelly = p - (1.0 - p) / payout_ratio
    fractional = fraction * full_kelly
    enough = n >= minimum_trades
    positive_expectancy = _mean(pnl) > 0.0
    applied = min(max_fraction, max(0.0, fractional)) if enough and positive_expectancy else 0.0
    return {
        "status": "DIAGNOSTIC_ONLY"
        if enough and positive_expectancy and fractional > 0
        else "NO_BET",
        "n": n,
        "win_probability": p,
        "mean_win": mean_win,
        "mean_loss_abs": mean_loss,
        "payout_ratio": payout_ratio,
        "net_expectancy_per_trade": _mean(pnl),
        "full_kelly_fraction": full_kelly,
        "fractional_kelly_multiplier": fraction,
        "fractional_kelly_fraction": fractional,
        "max_fraction_cap": max_fraction,
        "applied_fraction_after_cap": applied,
        "minimum_trades": minimum_trades,
        "decision": "DIAGNOSTIC_ONLY" if applied > 0 else "NO_BET",
        "research_only": True,
        "limitations": [
            "Estimated from the supplied sample and vulnerable to estimation error.",
            "Does not account for parameter uncertainty, serial dependence, gaps, or tail risk.",
            "A positive estimate is not permission to execute a trade.",
        ],
    }


def outcome_dependence(outcomes: Sequence[float], *, max_lag: int = 10) -> dict[str, Any]:
    """Describe autocorrelation in signed outcomes and conditional streak results."""
    pnl = _validate_returns(outcomes, minimum=3)
    if isinstance(max_lag, bool) or not isinstance(max_lag, int) or max_lag < 1:
        raise ValueError("MAX_LAG_MUST_BE_POSITIVE")
    signs = [1.0 if value > 0 else (-1.0 if value < 0 else 0.0) for value in pnl]
    mean_sign = _mean(signs)
    denominator = math.fsum((value - mean_sign) ** 2 for value in signs)
    correlations: list[dict[str, Any]] = []
    for lag in range(1, min(max_lag, len(signs) - 1) + 1):
        numerator = math.fsum(
            (signs[index] - mean_sign) * (signs[index + lag] - mean_sign)
            for index in range(len(signs) - lag)
        )
        correlations.append(
            {
                "lag": lag,
                "autocorrelation": numerator / denominator if denominator > 0 else None,
                "n_pairs": len(signs) - lag,
            }
        )

    streaks: dict[int, dict[str, Any]] = {}
    for target in (-1, 1):
        run = 0
        for value in signs:
            if value == target:
                run += 1
            else:
                run = 0
            if run >= 2:
                item = streaks.setdefault(
                    run, {"streak_length": run, "following_n": 0, "following_wins": 0}
                )
                # The next outcome after this completed streak is counted below only when present.
        for length in range(2, min(10, len(signs) - 1) + 1):
            matched = [
                signs[index + 1]
                for index in range(len(signs) - length)
                if all(signs[j] == target for j in range(index, index + length))
            ]
            if matched:
                item = streaks.setdefault(
                    length, {"streak_length": length, "following_n": 0, "following_wins": 0}
                )
                item["following_n"] += len(matched)
                item["following_wins"] += sum(value > 0 for value in matched)
    streak_rows = [
        {
            **item,
            "following_win_rate": item["following_wins"] / item["following_n"]
            if item["following_n"]
            else None,
        }
        for _, item in sorted(streaks.items())
    ]
    return {
        "n": len(pnl),
        "signed_outcome_autocorrelation": correlations,
        "conditional_streak_diagnostics": streak_rows,
        "interpretation": "DESCRIPTIVE_ONLY_NO_AUTOMATIC_RISK_ADJUSTMENT",
        "warning": "A losing streak does not imply a reversal is due.",
    }


def moving_block_bootstrap_ci(
    outcomes: Sequence[float],
    *,
    block_length: int = 20,
    repetitions: int = 2000,
    confidence: float = 0.95,
    seed: int = 421,
) -> dict[str, Any]:
    """Moving-block bootstrap CI for mean net outcome, preserving local ordering."""
    pnl = _validate_returns(outcomes, minimum=2)
    if (
        isinstance(block_length, bool)
        or not isinstance(block_length, int)
        or not 1 <= block_length <= len(pnl)
    ):
        raise ValueError("INVALID_BLOCK_LENGTH")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 200:
        raise ValueError("BOOTSTRAP_REPETITIONS_MUST_BE_AT_LEAST_200")
    if not math.isfinite(confidence) or not 0.5 < confidence < 1.0:
        raise ValueError("INVALID_CONFIDENCE")
    rng = random.Random(seed)
    n = len(pnl)
    starts = list(range(n - block_length + 1))
    means: list[float] = []
    blocks_needed = math.ceil(n / block_length)
    for _ in range(repetitions):
        sample: list[float] = []
        for _ in range(blocks_needed):
            start = rng.choice(starts)
            sample.extend(pnl[start : start + block_length])
        means.append(_mean(sample[:n]))
    alpha = (1.0 - confidence) / 2.0
    return {
        "n": n,
        "block_length": block_length,
        "repetitions": repetitions,
        "confidence": confidence,
        "observed_mean": _mean(pnl),
        "ci_lower": _quantile(means, alpha),
        "ci_upper": _quantile(means, 1.0 - alpha),
        "seed": seed,
        "method": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE",
        "limitations": [
            "Block length must match the dependence horizon; 20 observations is not universally correct.",
            "Bootstrap intervals do not correct data snooping by themselves.",
        ],
    }


def _summary(values: Sequence[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "net_total": math.fsum(values),
        "net_expectancy": _mean(values) if values else None,
        "profitable": bool(values) and math.fsum(values) > 0.0,
    }


def five_attack_overfitting_suite(
    outcomes: Sequence[float],
    *,
    assets: Sequence[str] | None = None,
    regimes: Sequence[str] | None = None,
    chunks: int = 10,
    omission_fraction: float = 0.30,
    omission_repetitions: int = 1000,
    seed: int = 421,
) -> dict[str, Any]:
    """Run five predeclared fragility diagnostics; never infer probability edge is real."""
    pnl = _validate_returns(outcomes, minimum=10)
    if assets is not None and len(assets) != len(pnl):
        raise ValueError("ASSET_LENGTH_MISMATCH")
    if regimes is not None and len(regimes) != len(pnl):
        raise ValueError("REGIME_LENGTH_MISMATCH")
    if isinstance(chunks, bool) or not isinstance(chunks, int) or not 2 <= chunks <= len(pnl):
        raise ValueError("INVALID_CHUNK_COUNT")
    if not 0.0 < omission_fraction < 1.0:
        raise ValueError("OMISSION_FRACTION_MUST_BE_IN_(0,1)")
    if (
        isinstance(omission_repetitions, bool)
        or not isinstance(omission_repetitions, int)
        or omission_repetitions < 100
    ):
        raise ValueError("OMISSION_REPETITIONS_MUST_BE_AT_LEAST_100")

    base = _summary(pnl)
    attacks: dict[str, Any] = {"base": base}
    # 1: Remove the best asset. N/A for a single-asset XAUUSD-only study.
    if assets is None or len(set(assets)) < 2:
        attacks["best_asset_removal"] = {"status": "NOT_APPLICABLE_SINGLE_ASSET", "passed": None}
    else:
        grouped: dict[str, list[float]] = defaultdict(list)
        for asset, value in zip(assets, pnl, strict=True):
            grouped[asset].append(value)
        best_asset = max(grouped, key=lambda key: math.fsum(grouped[key]))
        remaining = [value for asset, value in zip(assets, pnl, strict=True) if asset != best_asset]
        result = _summary(remaining)
        attacks["best_asset_removal"] = {
            "status": "TESTED",
            "removed_asset": best_asset,
            **result,
            "passed": bool(result["profitable"]),
        }

    # 2: Ten chronological chunks; report stability, not an optimization score.
    chunk_rows: list[dict[str, Any]] = []
    for index in range(chunks):
        left = index * len(pnl) // chunks
        right = (index + 1) * len(pnl) // chunks
        chunk_rows.append({"chunk": index + 1, **_summary(pnl[left:right])})
    positive_chunks = sum(bool(row["profitable"]) for row in chunk_rows)
    attacks["chronological_chunk_stability"] = {
        "status": "TESTED",
        "chunks": chunk_rows,
        "positive_chunk_fraction": positive_chunks / chunks,
        "passed": positive_chunks / chunks >= 0.90,
    }

    # 3: Remove the best regime. Regime labels must be predeclared/ex-ante.
    if regimes is None or len(set(regimes)) < 2:
        attacks["best_regime_removal"] = {
            "status": "NOT_APPLICABLE_REGIME_LABELS_MISSING_OR_SINGLE",
            "passed": None,
        }
    else:
        by_regime: dict[str, list[float]] = defaultdict(list)
        for regime, value in zip(regimes, pnl, strict=True):
            by_regime[regime].append(value)
        best_regime = max(by_regime, key=lambda key: math.fsum(by_regime[key]))
        remaining = [
            value for regime, value in zip(regimes, pnl, strict=True) if regime != best_regime
        ]
        result = _summary(remaining)
        attacks["best_regime_removal"] = {
            "status": "TESTED",
            "removed_regime": best_regime,
            **result,
            "passed": bool(result["profitable"]),
        }

    # 4: Remove the five highest individual contributors.
    top_indices = sorted(range(len(pnl)), key=lambda index: pnl[index], reverse=True)[
        : min(5, len(pnl))
    ]
    removed = set(top_indices)
    remaining = [value for index, value in enumerate(pnl) if index not in removed]
    result = _summary(remaining)
    attacks["top_five_trade_removal"] = {
        "status": "TESTED",
        "removed_trade_indices_zero_based": sorted(top_indices),
        **result,
        "passed": bool(result["profitable"]),
    }

    # 5: Randomly omit 30% of individual trades; this does not model clustered missed fills.
    rng = random.Random(seed)
    keep_probability = 1.0 - omission_fraction
    totals = [
        math.fsum(value for value in pnl if rng.random() < keep_probability)
        for _ in range(omission_repetitions)
    ]
    totals.sort()
    positive_fraction = sum(total > 0.0 for total in totals) / len(totals)
    attacks["random_trade_omission"] = {
        "status": "TESTED",
        "omission_fraction": omission_fraction,
        "repetitions": omission_repetitions,
        "seed": seed,
        "positive_net_fraction": positive_fraction,
        "net_total_p05": _quantile(totals, 0.05),
        "net_total_median": _quantile(totals, 0.50),
        "passed": positive_fraction >= 0.95,
    }

    tested = [
        value for key, value in attacks.items() if key != "base" and value.get("passed") is not None
    ]
    passed = sum(value["passed"] is True for value in tested)
    score = passed / len(tested) if tested else 0.0
    return {
        "version": EDGE_VALIDATION_SUITE_VERSION,
        "status": "DIAGNOSTIC_ONLY",
        "base": base,
        "attacks": {key: value for key, value in attacks.items() if key != "base"},
        "tested_attack_count": len(tested),
        "passed_attack_count": passed,
        "robustness_score": score,
        "threshold": 0.90,
        "threshold_passed": bool(tested) and score >= 0.90,
        "interpretation": "ROBUSTNESS_SCORE_IS_NOT_PROBABILITY_THAT_EDGE_IS_REAL",
        "limitations": [
            "Best-asset removal is not applicable to single-asset XAUUSD research.",
            "Regime labels must be defined without looking at the outcome being tested.",
            "Random trade omission does not simulate time-clustered execution failures.",
            "These attacks do not replace walk-forward validation, negative controls, or multiple-testing correction.",
        ],
    }


def incremental_log_likelihood_test(
    outcomes_binary: Sequence[int],
    baseline_probabilities: Sequence[float],
    augmented_probabilities: Sequence[float],
) -> dict[str, Any]:
    """Compare paired baseline/augmented probabilistic forecasts by log loss.

    This is a one-degree-of-freedom likelihood-ratio diagnostic only when the
    models are genuinely nested and regularity assumptions hold. For arbitrary
    separately trained models, use a preregistered paired out-of-sample test.
    """
    n = len(outcomes_binary)
    if n < 10 or len(baseline_probabilities) != n or len(augmented_probabilities) != n:
        raise ValueError("PAIRED_SAMPLES_MUST_MATCH_AND_BE_AT_LEAST_10")
    if any(isinstance(y, bool) or y not in (0, 1) for y in outcomes_binary):
        raise ValueError("OUTCOMES_MUST_BE_BINARY_0_OR_1")

    def log_likelihood(probabilities: Sequence[float]) -> float:
        total = 0.0
        for probability, outcome in zip(probabilities, outcomes_binary, strict=True):
            if isinstance(probability, bool) or not isinstance(probability, (int, float)):
                raise ValueError("INVALID_FORECAST_PROBABILITY")
            p = float(probability)
            if not math.isfinite(p) or not 0.0 < p < 1.0:
                raise ValueError("FORECAST_PROBABILITIES_MUST_BE_STRICTLY_BETWEEN_0_AND_1")
            total += math.log(p if outcome == 1 else 1.0 - p)
        return total

    baseline_ll = log_likelihood(baseline_probabilities)
    augmented_ll = log_likelihood(augmented_probabilities)
    improvement = augmented_ll - baseline_ll
    lr_statistic = max(0.0, 2.0 * improvement)
    # Chi-square(1) survival function, appropriate only under stated assumptions.
    p_value = math.erfc(math.sqrt(lr_statistic / 2.0)) if improvement > 0.0 else 1.0
    return {
        "n": n,
        "baseline_log_likelihood": baseline_ll,
        "augmented_log_likelihood": augmented_ll,
        "log_likelihood_improvement": improvement,
        "likelihood_ratio_statistic": lr_statistic,
        "p_value_unadjusted": p_value,
        "augmented_model_improved": improvement > 0.0,
        "interpretation": "PAIRED_FORECAST_DIAGNOSTIC_REQUIRES_OUT_OF_SAMPLE_AND_MULTIPLE_TESTING_CONTROL",
        "limitations": [
            "A naive likelihood-ratio p-value is not valid for arbitrary non-nested fitted models.",
            "The augmented data must be available at each historical prediction timestamp.",
            "Apply FDR across the preregistered family of tested hypotheses.",
        ],
    }


def cusum_change_points(
    values: Sequence[float],
    *,
    reference_mean: float,
    reference_std: float,
    drift: float = 0.5,
    threshold: float = 5.0,
) -> dict[str, Any]:
    """Detect mean shifts with two-sided standardized CUSUM.

    Reference mean/std, drift and threshold must be fixed from training data
    before holdout evaluation. Alarms are anomaly flags, not trade signals.
    """
    series = _validate_returns(values, minimum=10)
    for name, value in (
        ("reference_mean", reference_mean),
        ("reference_std", reference_std),
        ("drift", drift),
        ("threshold", threshold),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"INVALID_{name.upper()}")
    if reference_std <= 0.0 or drift < 0.0 or threshold <= 0.0:
        raise ValueError("INVALID_CUSUM_PARAMETERS")
    upper = 0.0
    lower = 0.0
    alarms: list[dict[str, Any]] = []
    for index, value in enumerate(series):
        z = (value - reference_mean) / reference_std
        upper = max(0.0, upper + z - drift)
        lower = min(0.0, lower + z + drift)
        if upper >= threshold:
            alarms.append({"index": index, "direction": "UPWARD_MEAN_SHIFT", "cusum": upper})
            upper = 0.0
            lower = 0.0
        elif -lower >= threshold:
            alarms.append({"index": index, "direction": "DOWNWARD_MEAN_SHIFT", "cusum": lower})
            upper = 0.0
            lower = 0.0
    return {
        "n": len(series),
        "reference_mean": reference_mean,
        "reference_std": reference_std,
        "drift": drift,
        "threshold": threshold,
        "alarms": alarms,
        "status": "ANOMALIES_FOUND" if alarms else "NO_CUSUM_ALARM",
        "interpretation": "ANOMALY_DIAGNOSTIC_NOT_TRADE_SIGNAL",
    }


def research_decision_gate(
    *,
    net_expectancy: float,
    bootstrap_ci_lower: float,
    overfitting_score: float,
    fdr_passed: bool,
    costs_verified: bool,
    minimum_sample_passed: bool,
    point_in_time_data_passed: bool,
) -> dict[str, Any]:
    """Combine validation gates into a research status; never an execution command."""
    numeric = {
        "net_expectancy": net_expectancy,
        "bootstrap_ci_lower": bootstrap_ci_lower,
        "overfitting_score": overfitting_score,
    }
    for name, value in numeric.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"INVALID_{name.upper()}")
    checks = {
        "positive_net_expectancy": net_expectancy > 0.0,
        "bootstrap_ci_lower_positive": bootstrap_ci_lower > 0.0,
        "robustness_score_at_least_0_90": overfitting_score >= 0.90 and overfitting_score <= 1.0,
        "fdr_passed": fdr_passed is True,
        "costs_verified": costs_verified is True,
        "minimum_sample_passed": minimum_sample_passed is True,
        "point_in_time_data_passed": point_in_time_data_passed is True,
    }
    all_passed = all(checks.values())
    return {
        "version": EDGE_VALIDATION_SUITE_VERSION,
        "status": "CANDIDATE_FOR_FURTHER_REVIEW" if all_passed else "NO_TRADE",
        "checks": checks,
        "failed_checks": [key for key, passed in checks.items() if not passed],
        "execution_authorized": False,
        "decision_use": "RESEARCH_ONLY",
        "warning": "Passing this gate is not proof of future profitability and does not authorize live execution.",
    }


__all__ = [
    "EDGE_VALIDATION_SUITE_VERSION",
    "quarter_kelly",
    "outcome_dependence",
    "moving_block_bootstrap_ci",
    "five_attack_overfitting_suite",
    "incremental_log_likelihood_test",
    "cusum_change_points",
    "research_decision_gate",
]
