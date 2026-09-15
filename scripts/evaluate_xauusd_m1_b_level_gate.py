"""Evaluate the frozen XAUUSD M1 walk-forward result against the B-level gate.

This evaluator never refits the probability model. It independently audits the
emitted walk-forward artifact, recomputes fold-level Brier improvements, and
applies deterministic statistical gates. A passing result is probabilistic
forecast evidence only; it is not a profitability or live-trading claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

try:
    from scripts.audit_xauusd_m1_source_to_result import audit as audit_source_to_result
    from scripts.audit_xauusd_m1_walkforward import audit as audit_walkforward
    from scripts.run_xauusd_m1_future_leakage_negative_control import run as run_future_leakage_control
    from scripts.run_xauusd_m1_negative_controls import run as run_label_shuffle_control
except ModuleNotFoundError:
    # Supports direct execution: python scripts/evaluate_xauusd_m1_b_level_gate.py ...
    # without requiring the repository root to be imported as a package first.
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.audit_xauusd_m1_source_to_result import audit as audit_source_to_result
    from scripts.audit_xauusd_m1_walkforward import audit as audit_walkforward
    from scripts.run_xauusd_m1_future_leakage_negative_control import run as run_future_leakage_control
    from scripts.run_xauusd_m1_negative_controls import run as run_label_shuffle_control

MIN_OOS_EVENTS = 10_000
MIN_FOLD_IMPROVEMENT_RATE = 0.70
PERMUTATION_ALPHA = 0.01
SIGN_TEST_ALPHA = 0.05
BOOTSTRAP_RESAMPLES = 20_000
BOOTSTRAP_SEED = 20260914
PERMUTATION_SEED = 20260914
LABEL_SHUFFLE_SEED = 20260910


def _two_sided_sign_test(positive: int, negative: int) -> float:
    n = positive + negative
    if n == 0:
        return 1.0
    k = min(positive, negative)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def _permutation_pvalue(differences: list[float], seed: int) -> tuple[float, int, str]:
    n = len(differences)
    observed = sum(differences) / n
    if n <= 20:
        extreme = 0
        total = 1 << n
        for mask in range(total):
            signed_sum = 0.0
            for i, value in enumerate(differences):
                signed_sum += value if (mask >> i) & 1 else -value
            if signed_sum / n >= observed - 1e-15:
                extreme += 1
        return extreme / total, total, "exact_sign_flip"

    rng = random.Random(seed)
    extreme = 0
    samples = 100_000
    for _ in range(samples):
        signed_sum = sum(value if rng.getrandbits(1) else -value for value in differences)
        if signed_sum / n >= observed - 1e-15:
            extreme += 1
    return (extreme + 1) / (samples + 1), samples, "monte_carlo_sign_flip"


def _bootstrap_ci(differences: list[float], seed: int) -> tuple[float, float]:
    if not differences:
        raise ValueError("no fold differences")
    rng = random.Random(seed)
    n = len(differences)
    means: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        total = sum(differences[rng.randrange(n)] for _ in range(n))
        means.append(total / n)
    means.sort()
    lower = means[int(0.025 * (len(means) - 1))]
    upper = means[int(0.975 * (len(means) - 1))]
    return lower, upper


def _fold_improvements(report: dict) -> list[float]:
    differences: list[float] = []
    for fold in report.get("folds", []):
        model = fold.get("model", {}).get("brier_score")
        baseline = fold.get("baseline", {}).get("brier_score")
        if not isinstance(model, (int, float)) or not isinstance(baseline, (int, float)):
            raise ValueError(f"fold {fold.get('fold')} has invalid Brier scores")
        differences.append(float(baseline) - float(model))
    if not differences:
        raise ValueError("walk-forward artifact contains no fold scores")
    return differences


def evaluate(result_path: Path, source_artifact: Path, output_path: Path) -> dict:
    raw = result_path.read_bytes()
    result = json.loads(raw.decode("utf-8"))
    artifact_sha256 = hashlib.sha256(raw).hexdigest()

    independent_audit = audit_walkforward(result_path)
    if independent_audit["status"] != "PASS":
        raise ValueError("Independent walk-forward audit failed: " + "; ".join(independent_audit["failures"]))

    source_audit = audit_source_to_result(source_artifact, result_path)
    if source_audit["status"] != "PASS":
        raise ValueError("Independent source-to-result audit failed: " + "; ".join(source_audit["failures"]))

    source_raw = source_artifact.read_bytes()
    expected_source_sha = result.get("source_artifact", {}).get("sha256")
    actual_source_sha = hashlib.sha256(source_raw).hexdigest()
    if expected_source_sha != actual_source_sha:
        raise ValueError("Walk-forward source artifact SHA-256 does not match resolved source bytes")

    contract = result.get("contract", {})
    if (contract.get("asset"), contract.get("timeframe"), contract.get("label")) != (
        "XAUUSD", "M1", "hit_threshold_1d"
    ):
        raise ValueError("Unexpected XAUUSD M1 research contract")

    folds = result.get("folds", [])
    differences = _fold_improvements(result)
    oos_events = int(result.get("audit", {}).get("oos_unique_validation_events", 0))
    aggregate_model = float(result["aggregate"]["model"]["brier_score"])
    aggregate_baseline = float(result["aggregate"]["baseline"]["brier_score"])
    aggregate_improvement = aggregate_baseline - aggregate_model
    positive = sum(value > 0 for value in differences)
    negative = sum(value < 0 for value in differences)
    zero = len(differences) - positive - negative
    positive_rate = positive / len(differences)
    ci_low, ci_high = _bootstrap_ci(differences, BOOTSTRAP_SEED)
    permutation_p, permutation_samples, permutation_method = _permutation_pvalue(differences, PERMUTATION_SEED)
    sign_p = _two_sided_sign_test(positive, negative)

    label_shuffle = run_label_shuffle_control(source_artifact, seed=LABEL_SHUFFLE_SEED)
    label_shuffle_pass = (
        label_shuffle["control"]["labels_preserved_as_multiset"]
        and label_shuffle["control"]["complete_events"] >= 2
    )

    leakage_path = output_path.with_name(output_path.stem + "_future_leakage_control.json")
    run_future_leakage_control(result_path, leakage_path)
    leakage_audit = audit_source_to_result(source_artifact, leakage_path)
    leakage_pass = leakage_audit["status"] == "FAIL"

    gates = {
        "independent_walkforward_audit": independent_audit["status"] == "PASS",
        "independent_source_to_result_audit": source_audit["status"] == "PASS",
        "minimum_10000_unique_oos_events": oos_events >= MIN_OOS_EVENTS,
        "positive_aggregate_brier_improvement": aggregate_improvement > 0.0,
        "fold_improvement_ci_above_zero": ci_low > 0.0,
        "paired_permutation_p_below_0_01": permutation_p < PERMUTATION_ALPHA,
        "two_sided_sign_test_below_0_05": sign_p < SIGN_TEST_ALPHA,
        "at_least_70_percent_folds_improve": positive_rate >= MIN_FOLD_IMPROVEMENT_RATE,
        "label_shuffle_negative_control": label_shuffle_pass,
        "temporal_leakage_negative_control": leakage_pass,
    }
    status = "B_LEVEL_PASS" if all(gates.values()) else "NO_EDGE_OR_INCONCLUSIVE"

    report = {
        "stage": "XAUUSD_M1_B_LEVEL_EDGE_VALIDATION",
        "status": status,
        "scientific_boundary": "PROBABILISTIC_FORECAST_IMPROVEMENT_ONLY_NO_PROFITABILITY_CLAIM",
        "hypothesis": {
            "null": "Frozen direction-conditional OOS model does not improve probabilistic forecast quality over frozen per-fold historical-rate baseline.",
            "alternative": "Frozen OOS model improves probabilistic forecast quality over that baseline.",
        },
        "provenance": {
            "walkforward_artifact_sha256": artifact_sha256,
            "source_artifact_sha256": actual_source_sha,
            "contract": contract,
            "oos_unique_validation_events": oos_events,
            "fold_count": len(folds),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "permutation_seed": PERMUTATION_SEED,
            "label_shuffle_seed": LABEL_SHUFFLE_SEED,
        },
        "metrics": {
            "aggregate_model_brier": aggregate_model,
            "aggregate_baseline_brier": aggregate_baseline,
            "aggregate_brier_improvement": aggregate_improvement,
            "fold_brier_improvements": differences,
            "positive_folds": positive,
            "negative_folds": negative,
            "zero_folds": zero,
            "positive_fold_rate": positive_rate,
            "fold_improvement_ci_95": [ci_low, ci_high],
            "paired_permutation_p": permutation_p,
            "paired_permutation_method": permutation_method,
            "paired_permutation_samples": permutation_samples,
            "two_sided_sign_test_p": sign_p,
        },
        "negative_controls": {
            "label_shuffle": label_shuffle["control"],
            "temporal_leakage": {
                "audit_status": leakage_audit["status"],
                "failures": leakage_audit["failures"],
            },
        },
        "gates": gates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/xauusd_m1_b_level_gate.json"))
    args = parser.parse_args()
    report = evaluate(args.result, args.source_artifact, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "B_LEVEL_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
