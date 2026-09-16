"""Public boundary for frozen XAUUSD M1 confirmation.

The implementation is kept in a private helper so the public harness cannot
promote a confirmation result to B_LEVEL_PASS unless the separately required
negative controls and provenance audits are explicitly verified.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from scripts._confirm_xauusd_m1_frozen_candidate_impl import (
    Candidate,
    _evaluate_fold,
    _select_frozen_candidate,
    run as _run_impl,
)


def _finalize_scientific_gate(result: dict) -> dict:
    gate = result.get("gate") or {}
    negative_controls = result.get("negative_controls") or {}
    required = (
        negative_controls.get("label_shuffle_control") == "VERIFIED",
        negative_controls.get("temporal_leakage_control") == "VERIFIED",
        gate.get("source_to_result_audit") is True,
        gate.get("walk_forward_audit") is True,
    )
    if all(required):
        return result
    result["scientific_gate"] = "NO_EDGE_OR_INCONCLUSIVE"
    result["scientific_gate_reason"] = (
        "B-level promotion is blocked until label-shuffle, temporal-leakage, "
        "source-to-result, and walk-forward controls are independently verified."
    )
    gate["external_controls_verified"] = False
    result["gate"] = gate
    return result


def run(*args, **kwargs) -> dict:
    output = Path(args[1] if len(args) > 1 else kwargs["output"])
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_output = Path(temp_dir) / "confirmation.json"
        impl_args = list(args)
        if len(impl_args) > 1:
            impl_args[1] = temp_output
            result = _run_impl(*impl_args, **kwargs)
        else:
            impl_kwargs = dict(kwargs)
            impl_kwargs["output"] = temp_output
            result = _run_impl(**impl_kwargs)
        result = _finalize_scientific_gate(result)
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
