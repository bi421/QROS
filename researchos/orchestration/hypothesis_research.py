"""Pre-registered hypothesis and audit ledger primitives.

This module deliberately does not certify an edge. It records research trials,
loads explicit (possibly unverified) cost assumptions, and prevents a final
holdout from being claimed more than once.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HYPOTHESES: dict[str, dict[str, Any]] = {
    "session_liquidity": {
        "title": "Session liquidity/volatility transition",
        "rationale": "London/New York openings can change participation and volatility; test whether a pre-registered opening-window rule has net value.",
        "parameters": {"session": "LONDON_OPEN", "lookback_bars": 8, "threshold": 1.0},
    },
    "vol_compression_expansion": {
        "title": "Volatility compression then expansion",
        "rationale": "A contraction in realized range may precede a volatility expansion; directional edge must be separately demonstrated, not assumed.",
        "parameters": {"compression_window": 8, "expansion_window": 3, "threshold": 0.8},
    },
    "daily_weekly_reversion": {
        "title": "Daily/weekly extreme mean reversion",
        "rationale": "Large deviations from a frozen daily/weekly reference may revert when liquidity normalizes; trend days are a known failure mode.",
        "parameters": {"reference": "PRIOR_DAY_RANGE", "z_threshold": 1.5, "max_holding_bars": 16},
    },
    "trend_persistence_regime": {
        "title": "Trend persistence conditional on regime",
        "rationale": "Directional persistence may be stronger in sustained-trend regimes than in range regimes; the regime classifier must be causal.",
        "parameters": {"trend_window": 16, "regime_window": 32, "threshold": 1.0},
    },
    "news_window_behavior": {
        "title": "Pre/post scheduled news behavior",
        "rationale": "Scheduled macro releases can alter volatility and liquidity; timestamps and event classifications must be sourced and time-aligned.",
        "parameters": {
            "pre_event_minutes": 30,
            "post_event_minutes": 60,
            "event_class": "HIGH_IMPACT",
        },
    },
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_costs(path: str | Path) -> dict[str, Any]:
    """Read JSON-compatible YAML; JSON is a valid YAML subset and needs no parser dependency."""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported cost configuration schema_version")
    return payload


def cost_model_ready(costs: dict[str, Any]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    if costs.get("status") != "VERIFIED":
        missing.append("cost configuration status is not VERIFIED")
    spread = costs.get("spread", {})
    if spread.get("base_price") is None or not spread.get("source"):
        missing.append("broker spread value/source missing")
    if any(v is None for v in spread.get("session_multipliers", {}).values()):
        missing.append("one or more session spread multipliers missing")
    commission = costs.get("commission", {})
    if (
        commission.get("round_trip_price_per_ounce") is None
        or commission.get("contract_size_ounces") is None
    ):
        missing.append("commission/contract size missing")
    slip = costs.get("slippage", {})
    if slip.get("base_price") is None or slip.get("volatility_multiplier") is None:
        missing.append("slippage model missing")
    swap = costs.get("swap", {})
    if (
        swap.get("long_daily_price_per_ounce") is None
        or swap.get("short_daily_price_per_ounce") is None
    ):
        missing.append("swap inputs missing")
    verification = costs.get("verification", {})
    if not verification.get("evidence_sha256") or not verification.get("verified_at_utc"):
        missing.append("verification evidence hash/timestamp missing")
    return not missing, missing


def verify_trial_registry(registry_path: str | Path) -> dict[str, Any]:
    """Verify each trial hash and the previous-record chain; this is tamper-evident, not tamper-proof."""
    path = Path(registry_path)
    if not path.exists():
        return {"valid": True, "records": 0, "errors": []}
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    previous = "GENESIS"
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON ({exc.msg})")
            continue
        if not isinstance(record, dict):
            errors.append(f"line {line_number}: record must be an object")
            continue
        expected_number = len(records) + 1
        if record.get("trial_number") != expected_number:
            errors.append(f"line {line_number}: trial_number mismatch")
        if record.get("previous_record_sha256") != previous:
            errors.append(f"line {line_number}: previous hash mismatch")
        supplied_hash = record.get("record_sha256")
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        if supplied_hash != sha256_json(payload):
            errors.append(f"line {line_number}: record hash mismatch")
        previous = supplied_hash if isinstance(supplied_hash, str) else "INVALID"
        records.append(record)
    return {"valid": not errors, "records": len(records), "errors": errors}


def register_trial(
    registry_path: str | Path,
    *,
    hypothesis_id: str,
    data_sha256: str,
    code_sha: str,
    phase: str = "EXPLORATORY",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one hash-chained trial record; never silently overwrites trial history."""
    if hypothesis_id not in HYPOTHESES:
        raise ValueError(f"Unknown hypothesis_id: {hypothesis_id}")
    if phase not in {"EXPLORATORY", "CANDIDATE_VALIDATION", "FINAL_HOLDOUT"}:
        raise ValueError("Invalid research phase")
    if len(data_sha256) != 64 or any(c not in "0123456789abcdef" for c in data_sha256.lower()):
        raise ValueError("data_sha256 must be a 64-character SHA-256 hex digest")
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    integrity = verify_trial_registry(path)
    if not integrity["valid"]:
        raise ValueError("TRIAL_REGISTRY_INTEGRITY_FAILURE: " + "; ".join(integrity["errors"]))
    records = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    previous = records[-1]["record_sha256"] if records else "GENESIS"
    payload = {
        "trial_number": len(records) + 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis_id": hypothesis_id,
        "hypothesis_sha256": sha256_json(HYPOTHESES[hypothesis_id]),
        "data_sha256": data_sha256.lower(),
        "code_sha": code_sha,
        "phase": phase,
        "metadata": metadata or {},
        "previous_record_sha256": previous,
    }
    record = {**payload, "record_sha256": sha256_json(payload)}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(record) + "\n")
    return record


def claim_final_holdout(lock_path: str | Path, *, candidate_sha256: str) -> dict[str, Any]:
    """One-time claim for a candidate. A claimed holdout cannot be claimed again."""
    if len(candidate_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in candidate_sha256.lower()
    ):
        raise ValueError("candidate_sha256 must be a 64-character SHA-256 hex digest")
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "status": "CLAIMED_ONCE",
        "candidate_sha256": candidate_sha256.lower(),
        "claimed_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "This local lock is not a security boundary against manual file edits; use controlled CI/storage for production enforcement.",
    }
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(state) + "\n")
    except FileExistsError:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {"candidate_sha256": "UNKNOWN_OR_CORRUPT_LOCK"}
        raise RuntimeError(
            "FINAL_HOLDOUT_ALREADY_CONSUMED; no second claim allowed "
            f"(first candidate={existing.get('candidate_sha256')})"
        ) from None
    return state


def evaluate_candidate_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    """Apply predeclared candidate thresholds; missing metrics fail closed."""
    checks = {
        "net_expectancy_positive": isinstance(metrics.get("net_expectancy"), (int, float))
        and metrics["net_expectancy"] > 0,
        "bootstrap_ci_lower_positive": isinstance(metrics.get("ci_lower"), (int, float))
        and metrics["ci_lower"] > 0,
        "walk_forward_positive_folds_at_least_70pct": isinstance(
            metrics.get("wf_positive_fold_fraction"), (int, float)
        )
        and metrics["wf_positive_fold_fraction"] >= 0.70,
        "net_positive_at_1_5x_cost": isinstance(
            metrics.get("net_expectancy_cost_1_5x"), (int, float)
        )
        and metrics["net_expectancy_cost_1_5x"] > 0,
        "multiple_testing_adjusted_significant": metrics.get("multiple_testing_significant")
        is True,
        "beats_negative_controls": metrics.get("beats_negative_controls") is True,
        "largest_year_or_regime_profit_share_at_most_40pct": isinstance(
            metrics.get("largest_year_or_regime_profit_share"), (int, float)
        )
        and metrics["largest_year_or_regime_profit_share"] <= 0.40,
        "cost_model_verified": metrics.get("cost_model_verified") is True,
        "plateau_stable": metrics.get("plateau_stable") is True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "CANDIDATE" if not failed else "REJECTED",
        "checks": checks,
        "failed_reasons": failed,
        "execution_enabled": False,
        "interpretation": "A CANDIDATE is eligible for one final holdout test; it is not proof of live profitability.",
    }


def kelly_fraction(
    win_probability: float,
    average_win_loss_ratio: float,
    *,
    fraction: float = 0.2,
    max_fraction: float = 0.05,
) -> dict[str, Any]:
    """Fractional Kelly diagnostic for binary net win/loss outcomes; never enables live sizing."""
    p, b, gamma, cap = (
        float(win_probability),
        float(average_win_loss_ratio),
        float(fraction),
        float(max_fraction),
    )
    if not 0 < p < 1:
        raise ValueError("win_probability must be strictly between 0 and 1")
    if b <= 0:
        raise ValueError("average_win_loss_ratio must be positive")
    if not 0 < gamma <= 1 or not 0 < cap <= 1:
        raise ValueError("fraction and max_fraction must be in (0, 1]")
    full = p - (1 - p) / b
    fractional = gamma * full
    applied = min(cap, max(0.0, fractional))
    return {
        "full_kelly_fraction": full,
        "fractional_kelly_fraction": fractional,
        "applied_fraction_after_cap": applied,
        "decision": "NO_BET" if applied == 0 else "DIAGNOSTIC_ONLY_NOT_AUTHORIZED_FOR_LIVE_SIZING",
        "warning": "Sensitive to estimation error, dependence, changing regimes and payoff tails; use net, out-of-sample estimates.",
    }


def analyze_trade_dependence(
    trade_pnls: list[float], *, max_lag: int = 10, loss_streak_lengths: tuple[int, ...] = (2, 3, 4)
) -> dict[str, Any]:
    """Descriptive sign-autocorrelation and loss-streak analysis; never changes sizing."""
    import math

    if len(trade_pnls) < 3:
        raise ValueError("At least three trades are required")
    values = [float(x) for x in trade_pnls]
    if any(not math.isfinite(x) for x in values):
        raise ValueError("trade_pnls must be finite")
    signs = [1.0 if x > 0 else -1.0 if x < 0 else 0.0 for x in values]
    mean = sum(signs) / len(signs)
    denom = sum((x - mean) ** 2 for x in signs)
    autocorr = {}
    for lag in range(1, min(max_lag, len(signs) - 1) + 1):
        autocorr[str(lag)] = (
            None
            if denom == 0
            else sum((signs[i] - mean) * (signs[i + lag] - mean) for i in range(len(signs) - lag))
            / denom
        )
    base_rate = sum(x > 0 for x in values) / len(values)
    streaks = {}
    for length in loss_streak_lengths:
        if length < 1:
            raise ValueError("loss streak lengths must be positive")
        observed = wins = 0
        for i in range(length, len(values)):
            if all(values[j] < 0 for j in range(i - length, i)):
                observed += 1
                wins += values[i] > 0
        streaks[str(length)] = {
            "observed_cases": observed,
            "next_trade_win_rate": wins / observed if observed else None,
            "baseline_win_rate": base_rate,
            "interpretation": "DESCRIPTIVE_ONLY; not evidence a reversal is due",
        }
    return {
        "n_trades": len(values),
        "outcome_sign_autocorrelation": autocorr,
        "loss_streak_conditional_win_rates": streaks,
        "baseline_win_rate": base_rate,
        "position_sizing_changed": False,
        "warning": "Requires dependence-aware confidence intervals/permutation tests before inference.",
    }


def _pnl_summary(values: list[float]) -> dict[str, Any]:
    total = sum(values)
    return {
        "n": len(values),
        "net_total": total,
        "net_expectancy": total / len(values) if values else None,
        "profitable": bool(values) and total > 0,
    }


def run_five_overfitting_attacks(
    trade_pnls: list[float],
    *,
    asset_labels: list[str] | None = None,
    regime_labels: list[str] | None = None,
    chunks: int = 10,
    omission_fraction: float = 0.30,
    omission_repetitions: int = 1000,
    seed: int = 421,
) -> dict[str, Any]:
    """Run five diagnostic stress tests on chronological net PnLs; never certify an edge."""
    import math
    import random

    values = [float(x) for x in trade_pnls]
    if not values or any(not math.isfinite(x) for x in values):
        raise ValueError("trade_pnls must be non-empty and finite")
    if chunks < 2 or omission_repetitions < 1 or not 0 <= omission_fraction < 1:
        raise ValueError("invalid stress-test configuration")
    if asset_labels is not None and len(asset_labels) != len(values):
        raise ValueError("asset_labels length mismatch")
    if regime_labels is not None and len(regime_labels) != len(values):
        raise ValueError("regime_labels length mismatch")
    attacks: dict[str, Any] = {}
    if asset_labels is None or len(set(asset_labels)) < 2:
        attacks["best_asset_removal"] = {
            "status": "NOT_APPLICABLE",
            "passed": None,
            "reason": "Single-asset data cannot test best-asset dependence.",
        }
    else:
        totals = {
            a: sum(v for v, label in zip(values, asset_labels) if label == a)
            for a in set(asset_labels)
        }
        best = max(totals, key=totals.get)
        rest = [v for v, label in zip(values, asset_labels) if label != best]
        attacks["best_asset_removal"] = {
            "status": "TESTED",
            "removed_asset": best,
            "remaining": _pnl_summary(rest),
            "passed": _pnl_summary(rest)["profitable"],
        }

    chunk_results = []
    for i in range(chunks):
        start, end = i * len(values) // chunks, (i + 1) * len(values) // chunks
        if start < end:
            chunk_results.append({"chunk": i + 1, **_pnl_summary(values[start:end])})
    attacks["time_chunk_stability"] = {
        "status": "TESTED",
        "chunks_requested": chunks,
        "chunks": chunk_results,
        "positive_chunk_fraction": sum(c["profitable"] for c in chunk_results) / len(chunk_results),
        "passed": bool(chunk_results) and all(c["profitable"] for c in chunk_results),
        "rule": "All time chunks must be positive for this strict diagnostic.",
    }
    if regime_labels is None or len(set(regime_labels)) < 2:
        attacks["best_regime_removal"] = {
            "status": "NOT_APPLICABLE",
            "passed": None,
            "reason": "Need at least two independently defined regime labels.",
        }
    else:
        totals = {
            r: sum(v for v, label in zip(values, regime_labels) if label == r)
            for r in set(regime_labels)
        }
        best = max(totals, key=totals.get)
        rest = [v for v, label in zip(values, regime_labels) if label != best]
        attacks["best_regime_removal"] = {
            "status": "TESTED",
            "removed_regime": best,
            "remaining": _pnl_summary(rest),
            "passed": _pnl_summary(rest)["profitable"],
        }
    top_indices = {
        i
        for i, _ in sorted(enumerate(values), key=lambda pair: pair[1], reverse=True)[
            : min(5, len(values))
        ]
    }
    rest = [v for i, v in enumerate(values) if i not in top_indices]
    attacks["top_five_trades_removal"] = {
        "status": "TESTED",
        "removed_count": len(top_indices),
        "removed_net_total": sum(values[i] for i in top_indices),
        "remaining": _pnl_summary(rest),
        "passed": _pnl_summary(rest)["profitable"],
        "warning": "Concentration stress test, not a significance test.",
    }

    rng = random.Random(seed)
    keep_probability = 1.0 - omission_fraction
    totals = [
        sum(v for v in values if rng.random() < keep_probability)
        for _ in range(omission_repetitions)
    ]
    sorted_totals = sorted(totals)
    positive_fraction = sum(x > 0 for x in totals) / len(totals)
    attacks["random_trade_omission"] = {
        "status": "TESTED",
        "omission_fraction": omission_fraction,
        "repetitions": omission_repetitions,
        "seed": seed,
        "positive_net_fraction": positive_fraction,
        "net_total_p05": sorted_totals[int(0.05 * (len(sorted_totals) - 1))],
        "net_total_median": sorted_totals[len(sorted_totals) // 2],
        "passed": positive_fraction >= 0.95,
    }
    return {
        "status": "DIAGNOSTIC_ONLY",
        "baseline": _pnl_summary(values),
        "attacks": attacks,
        "execution_enabled": False,
        "interpretation": "These stress tests are diagnostics, not significance tests or proof of a live edge.",
    }
