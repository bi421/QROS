"""Reconcile historical FOLLOW interval claims against currently retained evidence.

This is deliberately an evidence-availability audit, not a synthetic rerun. It does not
invent paired returns, reconstruct absent trades, or infer verified broker costs.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "architecture" / "vectorized-xauusd-backtest.md"
BENCHMARK = ROOT / "artifacts" / "vectorized_xauusd_backtest_fullgrid_benchmark_20261017.json"
OUTPUT = ROOT / "artifacts" / "qros_follow_reassessment_20261017.json"


def run() -> dict[str, Any]:
    doc_text = DOC.read_text(encoding="utf-8-sig")
    match = re.search(r"(\d+) were wholly above zero", doc_text)
    if not match:
        raise ValueError("Historical FOLLOW interval count not found in the documented baseline")
    historical_count = int(match.group(1))
    benchmark_bytes = BENCHMARK.read_bytes()
    benchmark = json.loads(benchmark_bytes.decode("utf-8-sig"))
    cost_model = benchmark.get("cost_model", {})
    candidates = benchmark.get("candidates", [])
    # The retained benchmark has aggregate candidate summaries only; no paired event
    # indices, per-trade net returns, or full family of paired p-values are present.
    reasons = [
        "PAIRED_TRADE_LEVEL_NET_RETURNS_NOT_RETAINED",
        "VERIFIED_ALL_IN_BROKER_COSTS_NOT_AVAILABLE",
        "EXACT_FAMILY_FDR_CANNOT_BE_RECONSTRUCTED_FROM_AGGREGATES",
    ]
    report = {
        "schema_version": "qros-follow-reassessment.v1",
        "historical_document": str(DOC.relative_to(ROOT)),
        "historical_reported_positive_ci_intervals": historical_count,
        "benchmark_artifact": str(BENCHMARK.relative_to(ROOT)),
        "benchmark_sha256": hashlib.sha256(benchmark_bytes).hexdigest(),
        "benchmark_candidate_summaries": len(candidates),
        "cost_model_configured": bool(cost_model.get("configured")),
        "cost_model_verified": bool(cost_model.get("verified")),
        "paired_trade_level_net_return_series_available": False,
        "exact_family_trial_p_values_available": False,
        "re_evaluated_count": 0,
        "passed_new_gate_count": 0,
        "statistically_rejected_count": 0,
        "blocked_pending_evidence_count": historical_count,
        "blocked_reasons": reasons,
        "interpretation": (
            "NOT_RE_EVALUABLE_FROM_RETAINED_ARTIFACTS; zero passed means zero evaluated, "
            "not evidence that all historical hypotheses are statistically false."
        ),
        "execution_authorized": False,
    }
    OUTPUT.write_text(json.dumps(report, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
