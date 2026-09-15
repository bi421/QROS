"""Nested, leakage-safe discovery of conditional XAUUSD M1 candidates.

Candidate definitions are created inside each chronological training window.
The inner validation slice selects one candidate. That candidate is then
estimated from prior training data and evaluated once on untouched outer OOS
data. Outer labels are never used for selection.

This is a discovery tool, not a trading strategy or an edge claim.
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
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class Candidate:
    name: str
    predicate: Callable[[dict], bool]


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _label(event: dict) -> int:
    value = (event.get("outcome") or {}).get("hit_threshold_1d")
    if not isinstance(value, bool):
        raise ValueError("complete event is missing boolean hit_threshold_1d")
    return int(value)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must be timezone-aware: {value}")
    return parsed


def _features(event: dict) -> dict:
    features = dict(event.get("context") or {})
    features["direction"] = event.get("direction")
    return features


def _candidate_library(contexts: list[dict]) -> list[Candidate]:
    """Build candidates only from the current inner-training contexts."""
    out: list[Candidate] = []
    directions = sorted({c.get("direction") for c in contexts if c.get("direction")})
    out.extend(
        Candidate(
            f"direction={value}",
            lambda c, value=value: c.get("direction") == value,
        )
        for value in directions
    )

    categorical = ("market_regime", "volatility_state", "session", "day_of_week")
    for field in categorical:
        values = sorted(
            {c.get(field) for c in contexts if c.get(field) is not None}, key=str
        )
        for value in values:
            out.append(
                Candidate(
                    f"{field}={value}",
                    lambda c, field=field, value=value: c.get(field) == value,
                )
            )

    numeric = (
        "rsi",
        "preceding_return_1d",
        "preceding_return_3d",
        "preceding_return_5d",
        "macd_histogram",
        "atr",
        "tick_volume",
    )
    for field in numeric:
        values = sorted(float(c[field]) for c in contexts if _finite(c.get(field)))
        if not values:
            continue
        median = statistics.median(values)
        out.append(
            Candidate(
                f"{field}>median({median:.12g})",
                lambda c, field=field, median=median: _finite(c.get(field))
                and float(c[field]) > median,
            )
        )
        out.append(
            Candidate(
                f"{field}<=median({median:.12g})",
                lambda c, field=field, median=median: _finite(c.get(field))
                and float(c[field]) <= median,
            )
        )
        if field.startswith("preceding_return_") or field == "macd_histogram":
            out.append(
                Candidate(
                    f"{field}>0",
                    lambda c, field=field: _finite(c.get(field))
                    and float(c[field]) > 0,
                )
            )
            out.append(
                Candidate(
                    f"{field}<0",
                    lambda c, field=field: _finite(c.get(field))
                    and float(c[field]) < 0,
                )
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


def _probability(rows: list[dict]) -> float:
    if not rows:
        raise ValueError("cannot estimate from empty training subset")
    # Jeffreys smoothing avoids zero/one probabilities without touching labels.
    return (0.5 + sum(_label(row) for row in rows)) / (1.0 + len(rows))


def _brier(probability: float, rows: list[dict]) -> float:
    if not rows:
        return float("nan")
    return sum((probability - _label(row)) ** 2 for row in rows) / len(rows)


def _candidate_score(
    inner_train: list[dict],
    inner_valid: list[dict],
    candidate: Candidate,
    min_events: int,
) -> tuple[float, int]:
    train_selected = [
        row for row in inner_train if candidate.predicate(_features(row))
    ]
    valid_selected = [
        row for row in inner_valid if candidate.predicate(_features(row))
    ]
    if len(train_selected) < min_events or len(valid_selected) < min_events:
        return float("-inf"), 0
    model = _probability(train_selected)
    baseline = _probability(inner_train)
    improvement = _brier(baseline, valid_selected) - _brier(model, valid_selected)
    return improvement, len(valid_selected)


def _permutation_p(values: list[float], permutations: int, seed: int) -> float:
    if not values:
        return float("nan")
    observed = sum(values)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(permutations):
        signed = sum(value if rng.getrandbits(1) else -value for value in values)
        if abs(signed) >= abs(observed):
            extreme += 1
    return (extreme + 1) / (permutations + 1)


def _sign_test_p(positive: int, negative: int) -> float:
    n = positive + negative
    if n == 0:
        return float("nan")
    tail = sum(math.comb(n, k) for k in range(0, min(positive, negative) + 1))
    return min(1.0, 2.0 * tail / (2**n))


def run(
    source: Path,
    output: Path,
    train_size: int,
    validation_size: int,
    step_size: int,
    min_events: int,
    permutations: int,
) -> dict:
    if train_size <= 0 or validation_size <= 0 or step_size <= 0:
        raise ValueError("window sizes must be positive")
    if step_size < validation_size:
        raise ValueError("step_size must be >= validation_size")
    if min_events <= 0 or permutations <= 0:
        raise ValueError("min_events and permutations must be positive")

    raw = source.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    contract = report.get("contract", {})
    if contract.get("asset") != "XAUUSD" or contract.get("timeframe") != "M1":
        raise ValueError("source is not the XAUUSD M1 contract")

    events = [
        event
        for event in report.get("events_data", [])
        if (event.get("outcome") or {}).get("hit_threshold_1d") is not None
    ]
    events.sort(key=lambda event: (event["timestamp"], event["event_id"]))
    if len(events) < train_size + validation_size:
        raise ValueError("insufficient complete events")

    folds: list[dict] = []
    start = 0
    while start + train_size + validation_size <= len(events):
        train_pool = events[start : start + train_size]
        valid = events[start + train_size : start + train_size + validation_size]
        validation_start = _time(valid[0]["timestamp"])
        train = [
            row
            for row in train_pool
            if _time((row.get("outcome") or {}).get("data_availability", {}).get("realized_end_1d", ""))
            < validation_start
        ]
        if len(train) < min_events * 2:
            raise RuntimeError("temporal embargo left insufficient training events")

        inner_cut = int(len(train) * 0.70)
        inner_train = train[:inner_cut]
        inner_valid = train[inner_cut:]
        if len(inner_train) < min_events or len(inner_valid) < min_events:
            raise RuntimeError("inner split is too small")

        library = _candidate_library([_features(event) for event in inner_train])
        ranked: list[tuple[float, int, str, Candidate]] = []
        for candidate in library:
            improvement, count = _candidate_score(
                inner_train, inner_valid, candidate, min_events
            )
            if math.isfinite(improvement):
                ranked.append((improvement, count, candidate.name, candidate))
        if not ranked:
            raise RuntimeError(
                f"fold starting {valid[0]['timestamp']}: no eligible candidate"
            )
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        _, _, _, selected = ranked[0]

        selected_train = [
            row for row in train if selected.predicate(_features(row))
        ]
        selected_valid = [
            row for row in valid if selected.predicate(_features(row))
        ]
        if len(selected_train) < min_events or len(selected_valid) < min_events:
            raise RuntimeError("selected candidate failed outer minimum")

        model = _probability(selected_train)
        baseline = _probability(train)
        model_brier = _brier(model, selected_valid)
        baseline_brier = _brier(baseline, selected_valid)
        improvement = baseline_brier - model_brier
        folds.append(
            {
                "fold": len(folds) + 1,
                "train_start": train[0]["timestamp"],
                "train_end": train[-1]["timestamp"],
                "validation_start": valid[0]["timestamp"],
                "validation_end": valid[-1]["timestamp"],
                "candidate": selected.name,
                "candidate_count_inner": len(library),
                "selected_train_events": len(selected_train),
                "selected_validation_events": len(selected_valid),
                "training_probability": model,
                "baseline_probability": baseline,
                "model_brier": model_brier,
                "baseline_brier": baseline_brier,
                "brier_improvement": improvement,
            }
        )
        start += step_size

    improvements = [fold["brier_improvement"] for fold in folds]
    positive = sum(value > 0 for value in improvements)
    negative = sum(value < 0 for value in improvements)
    result = {
        "stage": "XAUUSD_M1_NESTED_EDGE_DISCOVERY",
        "scientific_status": "EXPLORATORY_NO_EDGE_CLAIM",
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "complete_events": len(events),
        "configuration": {
            "train_size": train_size,
            "validation_size": validation_size,
            "step_size": step_size,
            "inner_train_fraction": 0.70,
            "min_events": min_events,
            "permutations": permutations,
            "outer_labels_used_for_selection": False,
            "outer_training_embargo": "realized_end_1d < validation_start",
        },
        "fold_count": len(folds),
        "selected_oos_events": sum(
            fold["selected_validation_events"] for fold in folds
        ),
        "positive_folds": positive,
        "negative_folds": negative,
        "positive_fold_rate": positive / len(folds),
        "mean_brier_improvement": statistics.fmean(improvements),
        "permutation_p": _permutation_p(
            improvements, permutations, seed=20260915
        ),
        "sign_test_p": _sign_test_p(positive, negative),
        "folds": folds,
        "scientific_gate": {
            "status": "NO_EDGE_OR_INCONCLUSIVE",
            "reason": "Discovery requires a separate preregistered confirmation gate on untouched data; this artifact is candidate-generation evidence only.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "fold_count",
                    "selected_oos_events",
                    "positive_folds",
                    "negative_folds",
                    "positive_fold_rate",
                    "mean_brier_improvement",
                    "permutation_p",
                    "sign_test_p",
                )
            },
            indent=2,
        )
    )
    print(f"Artifact: {output}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/xauusd_m1_nested_edge_discovery.json"),
    )
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--validation-size", type=int, default=500)
    parser.add_argument("--step-size", type=int, default=500)
    parser.add_argument("--min-events", type=int, default=100)
    parser.add_argument("--permutations", type=int, default=20000)
    args = parser.parse_args()
    run(
        args.source,
        args.output,
        args.train_size,
        args.validation_size,
        args.step_size,
        args.min_events,
        args.permutations,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
