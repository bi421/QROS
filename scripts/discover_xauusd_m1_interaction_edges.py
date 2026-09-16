"""Leakage-safe nested discovery for conditional XAUUSD M1 interactions.

Atomic candidates are ranked on the inner train/validation split only. The
best atomic candidates are combined into pairwise conjunctions, again selected
only on the inner validation slice. The selected interaction is evaluated once
on untouched outer OOS data. Outer labels never participate in candidate
selection.

This module discovers candidates; it does not certify an edge. Any discovered
candidate must pass the separate frozen B-level confirmation gate on untouched
data before being called an edge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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

def _atomic_library(contexts: list[dict]) -> list[Candidate]:
    out: list[Candidate] = []
    directions = sorted({c.get("direction") for c in contexts if c.get("direction")})
    out.extend(Candidate(f"direction={value}", lambda c, value=value: c.get("direction") == value) for value in directions)
    for field in ("market_regime", "volatility_state", "session", "day_of_week"):
        values = sorted({c.get(field) for c in contexts if c.get(field) is not None}, key=str)
        for value in values:
            out.append(Candidate(f"{field}={value}", lambda c, field=field, value=value: c.get(field) == value))
    for field in ("rsi", "preceding_return_1d", "preceding_return_3d", "preceding_return_5d", "macd_histogram", "atr", "tick_volume"):
        values = sorted(float(c[field]) for c in contexts if _finite(c.get(field)))
        if not values:
            continue
        median = statistics.median(values)
        out.append(Candidate(f"{field}>median({median:.12g})", lambda c, field=field, median=median: _finite(c.get(field)) and float(c[field]) > median))
        out.append(Candidate(f"{field}<=median({median:.12g})", lambda c, field=field, median=median: _finite(c.get(field)) and float(c[field]) <= median))
        if field.startswith("preceding_return_") or field == "macd_histogram":
            for op, symbol in ((lambda value: value > 0, ">0"), (lambda value: value < 0, "<0")):
                out.append(Candidate(f"{field}{symbol}", lambda c, field=field, op=op: _finite(c.get(field)) and op(float(c[field]))))
        if field == "rsi":
            for lo, hi in ((0.0, 30.0), (30.0, 50.0), (50.0, 70.0), (70.0, 101.0)):
                out.append(Candidate(f"rsi=[{lo:g},{hi:g})", lambda c, lo=lo, hi=hi: _finite(c.get("rsi")) and lo <= float(c["rsi"]) < hi))
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

def _selected(rows: list[dict], candidate: Candidate) -> list[dict]:
    return [row for row in rows if candidate.predicate(_features(row))]

def _score(inner_train: list[dict], inner_valid: list[dict], candidate: Candidate, min_events: int) -> tuple[float, int]:
    train_selected = _selected(inner_train, candidate)
    valid_selected = _selected(inner_valid, candidate)
    if len(train_selected) < min_events or len(valid_selected) < min_events:
        return float("-inf"), 0
    model = _probability(train_selected)
    baseline = _probability(inner_train)
    return _brier(baseline, valid_selected) - _brier(model, valid_selected), len(valid_selected)

def _conjunction(left: Candidate, right: Candidate) -> Candidate:
    return Candidate(f"({left.name}) AND ({right.name})", lambda context, left=left, right=right: left.predicate(context) and right.predicate(context))

def _ranked_candidates(inner_train: list[dict], inner_valid: list[dict], min_events: int, interaction_top_k: int) -> list[tuple[float, int, str, Candidate]]:
    atomic = _atomic_library([_features(event) for event in inner_train])
    ranked_atomic: list[tuple[float, int, str, Candidate]] = []
    for candidate in atomic:
        improvement, count = _score(inner_train, inner_valid, candidate, min_events)
        if math.isfinite(improvement):
            ranked_atomic.append((improvement, count, candidate.name, candidate))
    ranked_atomic.sort(key=lambda item: (-item[0], -item[1], item[2]))
    seeds = [item[3] for item in ranked_atomic[:interaction_top_k]]
    candidates = list(seeds)
    for index, left in enumerate(seeds):
        for right in seeds[index + 1:]:
            candidates.append(_conjunction(left, right))
    ranked: list[tuple[float, int, str, Candidate]] = []
    for candidate in candidates:
        improvement, count = _score(inner_train, inner_valid, candidate, min_events)
        if math.isfinite(improvement):
            ranked.append((improvement, count, candidate.name, candidate))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranked

def run(source: Path, output: Path, train_size: int, validation_size: int, step_size: int, min_events: int, interaction_top_k: int) -> dict:
    if min_events <= 0 or interaction_top_k < 2:
        raise ValueError("min_events must be positive and interaction_top_k must be >= 2")
    raw = source.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    contract = report.get("contract", {})
    if (contract.get("asset"), contract.get("timeframe")) != ("XAUUSD", "M1"):
        raise ValueError("source is not the XAUUSD M1 contract")
    events = [event for event in report.get("events_data", []) if (event.get("outcome") or {}).get("hit_threshold_1d") is not None]
    events.sort(key=lambda event: (event["timestamp"], event["event_id"]))
    if len(events) < train_size + validation_size:
        raise ValueError("insufficient complete events")
    folds: list[dict] = []
    start = 0
    while start + train_size + validation_size <= len(events):
        train_pool = events[start:start + train_size]
        valid = events[start + train_size:start + train_size + validation_size]
        validation_start = _time(valid[0]["timestamp"])
        train = [row for row in train_pool if _time((row.get("outcome") or {}).get("data_availability", {}).get("realized_end_1d", "")) < validation_start]
        if len(train) < min_events * 2:
            raise RuntimeError("temporal embargo left insufficient training events")
        inner_cut = int(len(train) * 0.70)
        inner_train, inner_valid = train[:inner_cut], train[inner_cut:]
        if len(inner_train) < min_events or len(inner_valid) < min_events:
            raise RuntimeError("inner split is too small")
        ranked = _ranked_candidates(inner_train, inner_valid, min_events, interaction_top_k)
        if not ranked:
            raise RuntimeError(f"fold starting {valid[0]['timestamp']}: no eligible candidate")
        _, _, _, selected = ranked[0]
        selected_train = _selected(train, selected)
        selected_valid = _selected(valid, selected)
        support = len(selected_train) >= min_events and len(selected_valid) >= min_events
        fold = {"fold": len(folds) + 1, "train_start": train[0]["timestamp"], "train_end": train[-1]["timestamp"], "validation_start": valid[0]["timestamp"], "validation_end": valid[-1]["timestamp"], "candidate": selected.name, "candidate_kind": "interaction" if " AND " in selected.name else "atomic", "selected_train_events": len(selected_train), "selected_validation_events": len(selected_valid), "outer_minimum_required": min_events, "outer_support_met": support}
        if support:
            model = _probability(selected_train)
            baseline = _probability(train)
            model_brier = _brier(model, selected_valid)
            baseline_brier = _brier(baseline, selected_valid)
            fold.update({"outer_support_status": "PASS", "training_probability": model, "baseline_probability": baseline, "model_brier": model_brier, "baseline_brier": baseline_brier, "brier_improvement": baseline_brier - model_brier})
        else:
            fold.update({"outer_support_status": "FAIL", "training_probability": None, "baseline_probability": None, "model_brier": None, "baseline_brier": None, "brier_improvement": None})
        folds.append(fold)
        start += step_size
    evaluated = [fold for fold in folds if fold["brier_improvement"] is not None]
    improvements = [fold["brier_improvement"] for fold in evaluated]
    positive = sum(value > 0 for value in improvements)
    negative = sum(value < 0 for value in improvements)
    result = {"stage": "XAUUSD_M1_NESTED_INTERACTION_EDGE_DISCOVERY", "scientific_status": "EXPLORATORY_NO_EDGE_CLAIM", "source_sha256": hashlib.sha256(raw).hexdigest(), "complete_events": len(events), "configuration": {"train_size": train_size, "validation_size": validation_size, "step_size": step_size, "inner_train_fraction": 0.70, "min_events": min_events, "interaction_top_k": interaction_top_k, "outer_labels_used_for_selection": False, "outer_training_embargo": "realized_end_1d < validation_start"}, "fold_count": len(folds), "evaluated_fold_count": len(evaluated), "outer_support_failures": sum(not fold["outer_support_met"] for fold in folds), "selected_oos_events": sum(fold["selected_validation_events"] for fold in evaluated), "positive_folds": positive, "negative_folds": negative, "positive_fold_rate": positive / len(improvements) if improvements else None, "mean_brier_improvement": statistics.fmean(improvements) if improvements else None, "folds": folds, "scientific_gate": {"status": "NO_EDGE_OR_INCONCLUSIVE", "reason": "Interaction discovery is exploratory; confirmation must use untouched data and the frozen B-level statistical gate."}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/xauusd_m1_interaction_edge_discovery.json"))
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--validation-size", type=int, default=500)
    parser.add_argument("--step-size", type=int, default=500)
    parser.add_argument("--min-events", type=int, default=100)
    parser.add_argument("--interaction-top-k", type=int, default=12)
    args = parser.parse_args()
    result = run(args.source, args.output, args.train_size, args.validation_size, args.step_size, args.min_events, args.interaction_top_k)
    print(json.dumps({key: result[key] for key in ("fold_count", "evaluated_fold_count", "outer_support_failures", "selected_oos_events", "positive_folds", "negative_folds", "positive_fold_rate", "mean_brier_improvement")}, indent=2))
    print(f"Artifact: {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
