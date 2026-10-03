"""Confirm one frozen XAUUSD M1 hypothesis on chronologically untouched data.

The candidate is selected only from a development period. Its definition and
probability are then frozen before the confirmation period is evaluated.
Confirmation labels cannot alter candidate selection or model parameters.
This script does not weaken the repository's B-level acceptance contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime
from math import comb
from pathlib import Path
from typing import Callable

MIN_OOS_EVENTS = 10_000
MIN_FOLD_IMPROVEMENT_RATE = 0.70
PERMUTATION_ALPHA = 0.01
SIGN_TEST_ALPHA = 0.05
BOOTSTRAP_RESAMPLES = 20_000
BOOTSTRAP_SEED = 20260915
PERMUTATION_SEED = 20260916


@dataclass(frozen=True)
class Candidate:
    name: str
    predicate: Callable[[dict], bool]


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _label(row: dict) -> int:
    value = (row.get("outcome") or {}).get("hit_threshold_1d")
    if not isinstance(value, bool):
        raise ValueError("complete event is missing boolean hit_threshold_1d")
    return int(value)


def _features(row: dict) -> dict:
    context = dict(row.get("context") or {})
    context["direction"] = row.get("direction")
    return context


def _probability(rows: list[dict]) -> float:
    if not rows:
        raise ValueError("cannot estimate probability from empty development subset")
    return (0.5 + sum(_label(row) for row in rows)) / (1.0 + len(rows))


def _brier(probability: float, rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    return sum((probability - _label(row)) ** 2 for row in rows) / len(rows)


def _selected(rows: list[dict], candidate: Candidate) -> list[dict]:
    return [row for row in rows if candidate.predicate(_features(row))]


def _atomic_library(rows: list[dict]) -> list[Candidate]:
    contexts = [_features(row) for row in rows]
    out: list[Candidate] = []
    for field in ("direction", "market_regime", "volatility_state", "session", "day_of_week"):
        values = sorted({c.get(field) for c in contexts if c.get(field) is not None}, key=str)
        for value in values:
            out.append(
                Candidate(
                    f"{field}={value}",
                    lambda c, field=field, value=value: c.get(field) == value,
                )
            )
    for field in (
        "rsi", "preceding_return_1d", "preceding_return_3d",
        "preceding_return_5d", "macd_histogram", "atr", "tick_volume",
    ):
        values = sorted(float(c[field]) for c in contexts if _finite(c.get(field)))
        if not values:
            continue
        median = statistics.median(values)
        out.extend(
            [
                Candidate(
                    f"{field}>median({median:.12g})",
                    lambda c, field=field, m=median: _finite(c.get(field)) and float(c[field]) > m,
                ),
                Candidate(
                    f"{field}<=median({median:.12g})",
                    lambda c, field=field, m=median: _finite(c.get(field)) and float(c[field]) <= m,
                ),
            ]
        )
        if field.startswith("preceding_return_") or field == "macd_histogram":
            out.extend(
                [
                    Candidate(
                        f"{field}>0",
                        lambda c, field=field: _finite(c.get(field)) and float(c[field]) > 0,
                    ),
                    Candidate(
                        f"{field}<0",
                        lambda c, field=field: _finite(c.get(field)) and float(c[field]) < 0,
                    ),
                ]
            )
        if field == "rsi":
            for lo, hi in ((0.0, 30.0), (30.0, 50.0), (50.0, 70.0), (70.0, 101.0)):
                out.append(
                    Candidate(
                        f"rsi=[{lo:g},{hi:g})",
                        lambda c, lo=lo, hi=hi: _finite(c.get("rsi"))
                        and lo <= float(c["rsi"]) < hi,
                    )
                )
    return out


def _conjunction(left: Candidate, right: Candidate) -> Candidate:
    return Candidate(
        f"({left.name}) AND ({right.name})",
        lambda context, left=left, right=right: left.predicate(context) and right.predicate(context),
    )


def _development_ranked(
    train: list[dict],
    valid: list[dict],
    min_events: int,
    interaction_top_k: int,
) -> list[tuple[float, int, str, Candidate]]:
    baseline = _probability(train)
    atomic_ranked: list[tuple[float, int, str, Candidate]] = []
    for candidate in _atomic_library(train):
        selected_train = _selected(train, candidate)
        selected_valid = _selected(valid, candidate)
        if len(selected_train) < min_events or len(selected_valid) < min_events:
            continue
        improvement = _brier(baseline, selected_valid) - _brier(
            _probability(selected_train), selected_valid
        )
        atomic_ranked.append((improvement, len(selected_valid), candidate.name, candidate))
    atomic_ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    seeds = [item[3] for item in atomic_ranked[:interaction_top_k]]
    candidates = list(seeds)
    for index, left in enumerate(seeds):
        for right in seeds[index + 1 :]:
            candidates.append(_conjunction(left, right))

    ranked: list[tuple[float, int, str, Candidate]] = []
    for candidate in candidates:
        selected_train = _selected(train, candidate)
        selected_valid = _selected(valid, candidate)
        if len(selected_train) < min_events or len(selected_valid) < min_events:
            continue
        improvement = _brier(baseline, selected_valid) - _brier(
            _probability(selected_train), selected_valid
        )
        ranked.append((improvement, len(selected_valid), candidate.name, candidate))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranked


def _select_frozen_candidate(
    development: list[dict], min_events: int, interaction_top_k: int
) -> tuple[Candidate, dict]:
    split = int(len(development) * 0.70)
    train, valid = development[:split], development[split:]
    ranked = _development_ranked(train, valid, min_events, interaction_top_k)
    if not ranked:
        raise RuntimeError("no development candidate met minimum support")
    score, support, _, candidate = ranked[0]
    selected_train = _selected(train, candidate)
    return candidate, {
        "development_train_events": len(train),
        "development_validation_events": len(valid),
        "selected_train_events": len(selected_train),
        "selected_validation_events": support,
        "development_validation_improvement": score,
        "development_selection_used_confirmation_labels": False,
    }


def _folds(rows: list[dict], fold_size: int) -> list[list[dict]]:
    if fold_size <= 0:
        raise ValueError("fold_size must be positive")
    return [
        rows[i : i + fold_size]
        for i in range(0, len(rows), fold_size)
        if len(rows[i : i + fold_size]) == fold_size
    ]


def _bootstrap_ci(values: list[float]) -> list[float]:
    if not values:
        return [float("nan"), float("nan")]
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        statistics.fmean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return [
        means[int(0.025 * BOOTSTRAP_RESAMPLES)],
        means[int(0.975 * BOOTSTRAP_RESAMPLES) - 1],
    ]


def _permutation_p(values: list[float]) -> float:
    if not values:
        return float("nan")
    rng = random.Random(PERMUTATION_SEED)
    observed = abs(sum(values))
    extreme = 0
    for _ in range(BOOTSTRAP_RESAMPLES):
        signed = abs(sum(value if rng.getrandbits(1) else -value for value in values))
        extreme += signed >= observed
    return (extreme + 1) / (BOOTSTRAP_RESAMPLES + 1)


def _sign_test_p(values: list[float]) -> float:
    positive = sum(value > 0 for value in values)
    negative = sum(value < 0 for value in values)
    n = positive + negative
    if n == 0:
        return 1.0
    lower_tail = sum(comb(n, k) for k in range(positive + 1))
    upper_tail = sum(comb(n, k) for k in range(negative + 1))
    return min(1.0, 2.0 * min(lower_tail, upper_tail) / (2**n))


def _evaluate_fold(fold: list[dict], candidate: Candidate, development: list[dict]) -> dict:
    selected_development = _selected(development, candidate)
    model_probability = _probability(selected_development)
    baseline_probability = _probability(development)
    model_brier = 0.0
    baseline_brier = 0.0
    candidate_events = 0
    for row in fold:
        y = _label(row)
        if candidate.predicate(_features(row)):
            candidate_events += 1
            model_probability_for_row = model_probability
        else:
            model_probability_for_row = baseline_probability
        model_brier += (model_probability_for_row - y) ** 2
        baseline_brier += (baseline_probability - y) ** 2
    count = len(fold)
    return {
        "events": count,
        "candidate_events": candidate_events,
        "model_brier": model_brier / count,
        "baseline_brier": baseline_brier / count,
        "brier_improvement": (baseline_brier - model_brier) / count,
    }


def run(
    source: Path,
    output: Path,
    discovery_end: str,
    confirmation_start: str,
    min_events: int,
    fold_size: int,
    interaction_top_k: int,
) -> dict:
    raw = source.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    contract = report.get("contract", {})
    if (contract.get("asset"), contract.get("timeframe")) != ("XAUUSD", "M1"):
        raise ValueError("source is not the XAUUSD M1 contract")
    events = [
        row for row in report.get("events_data", [])
        if (row.get("outcome") or {}).get("hit_threshold_1d") is not None
    ]
    events.sort(key=lambda row: (row["timestamp"], row["event_id"]))
    discovery_cut = _time(discovery_end)
    confirmation_cut = _time(confirmation_start)
    if discovery_cut >= confirmation_cut:
        raise ValueError("discovery_end must be strictly before confirmation_start")
    development = [row for row in events if _time(row["timestamp"]) < discovery_cut]
    confirmation = [row for row in events if _time(row["timestamp"]) >= confirmation_cut]
    if len(development) < min_events * 4:
        raise ValueError("development period is too small for frozen candidate selection")
    if len(confirmation) < MIN_OOS_EVENTS:
        raise ValueError(
            f"confirmation period has only {len(confirmation)} events; "
            f"B-level requires {MIN_OOS_EVENTS}"
        )

    candidate, selection = _select_frozen_candidate(
        development, min_events, interaction_top_k
    )
    # The candidate is frozen here. No confirmation label is inspected before this point.
    folds = _folds(confirmation, fold_size)
    if len(folds) < 2:
        raise ValueError("confirmation period must contain at least two complete folds")
    diagnostics = [_evaluate_fold(fold, candidate, development) for fold in folds]
    improvements = [item["brier_improvement"] for item in diagnostics]
    ci = _bootstrap_ci(improvements)
    permutation_p = _permutation_p(improvements)
    sign_p = _sign_test_p(improvements)
    positive = sum(value > 0 for value in improvements)
    negative = sum(value < 0 for value in improvements)
    positive_rate = positive / len(improvements)

    gate = {
        "independent_confirmation_oos_events": len(confirmation) >= MIN_OOS_EVENTS,
        "positive_aggregate_brier_improvement": statistics.fmean(improvements) > 0,
        "fold_improvement_ci_above_zero": ci[0] > 0,
        "paired_permutation_p_below_0_01": permutation_p < PERMUTATION_ALPHA,
        "two_sided_sign_test_p_below_0_05": sign_p < SIGN_TEST_ALPHA,
        "at_least_70_percent_folds_improve": positive_rate >= MIN_FOLD_IMPROVEMENT_RATE,
        "confirmation_candidate_frozen": True,
        "confirmation_labels_used_for_selection": False,
        "label_shuffle_negative_control": "REQUIRED_SEPARATE_RUN",
        "temporal_leakage_negative_control": "REQUIRED_SEPARATE_RUN",
    }
    scientific_gate = "B_LEVEL_PASS" if all(
        gate[key]
        for key in (
            "independent_confirmation_oos_events",
            "positive_aggregate_brier_improvement",
            "fold_improvement_ci_above_zero",
            "paired_permutation_p_below_0_01",
            "two_sided_sign_test_p_below_0_05",
            "at_least_70_percent_folds_improve",
        )
    ) else "NO_EDGE_OR_INCONCLUSIVE"

    result = {
        "stage": "XAUUSD_M1_FROZEN_CANDIDATE_CONFIRMATION",
        "scientific_status": "B_LEVEL_CONFIRMATION_TESTED",
        "scientific_gate": scientific_gate,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "discovery_end": discovery_end,
        "confirmation_start": confirmation_start,
        "development_events": len(development),
        "confirmation_events": len(confirmation),
        "frozen_candidate": candidate.name,
        "selection": selection,
        "configuration": {
            "min_events": min_events,
            "fold_size": fold_size,
            "fold_count": len(folds),
            "interaction_top_k": interaction_top_k,
            "minimum_confirmation_oos_events": MIN_OOS_EVENTS,
            "candidate_modified_after_confirmation_start": False,
            "confirmation_labels_used_for_selection": False,
        },
        "confirmation": {
            "aggregate_brier_improvement": statistics.fmean(improvements),
            "fold_improvement_ci_95": ci,
            "paired_permutation_p": permutation_p,
            "sign_test_p": sign_p,
            "positive_folds": positive,
            "negative_folds": negative,
            "positive_fold_rate": positive_rate,
            "candidate_events": sum(item["candidate_events"] for item in diagnostics),
            "folds": diagnostics,
        },
        "gate": gate,
        "negative_controls": {
            "label_shuffle_control": "REQUIRED_SEPARATE_RUN",
            "temporal_leakage_control": "REQUIRED_SEPARATE_RUN",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/xauusd_m1_frozen_confirmation.json"))
    parser.add_argument("--discovery-end", required=True)
    parser.add_argument("--confirmation-start", required=True)
    parser.add_argument("--min-events", type=int, default=100)
    parser.add_argument("--fold-size", type=int, default=250)
    parser.add_argument("--interaction-top-k", type=int, default=12)
    args = parser.parse_args()
    result = run(
        args.source,
        args.output,
        args.discovery_end,
        args.confirmation_start,
        args.min_events,
        args.fold_size,
        args.interaction_top_k,
    )
    print(json.dumps({
        "frozen_candidate": result["frozen_candidate"],
        "development_events": result["development_events"],
        "confirmation_events": result["confirmation_events"],
        "scientific_gate": result["scientific_gate"],
        "confirmation": {k: v for k, v in result["confirmation"].items() if k != "folds"},
    }, indent=2))
    print(f"Artifact: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
