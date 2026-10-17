"""Run deterministic edge-validation diagnostics on a frozen trade-ledger CSV.

Required column: net_pnl. Optional columns: asset, regime. Optional paired
forecast columns: outcome_binary, baseline_probability, augmented_probability.
This command does not authorize execution or prove a strategy edge.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from researchos.orchestration.edge_validation_suite import (
    five_attack_overfitting_suite,
    incremental_log_likelihood_test,
    moving_block_bootstrap_ci,
    outcome_dependence,
    quarter_kelly,
)


def _number(value: str, field: str, row_number: int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"INVALID_{field}:ROW_{row_number}") from exc
    if not math.isfinite(result):
        raise ValueError(f"NONFINITE_{field}:ROW_{row_number}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--block-length", type=int, default=20)
    parser.add_argument("--bootstrap-repetitions", type=int, default=2000)
    parser.add_argument("--omission-repetitions", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=421)
    parser.add_argument("--minimum-kelly-trades", type=int, default=100)
    return parser


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    with args.input.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "net_pnl" not in reader.fieldnames:
            raise ValueError("CSV_REQUIRES_NET_PNL_COLUMN")
        rows = list(reader)
        if len(rows) < 10:
            raise ValueError("LEDGER_REQUIRES_AT_LEAST_10_ROWS")
        pnl = [
            _number(row.get("net_pnl", ""), "NET_PNL", index + 2) for index, row in enumerate(rows)
        ]

        assets = (
            [row.get("asset", "").strip() for row in rows] if "asset" in reader.fieldnames else None
        )
        regimes = (
            [row.get("regime", "").strip() for row in rows]
            if "regime" in reader.fieldnames
            else None
        )
        if assets is not None and any(not item for item in assets):
            raise ValueError("ASSET_LABELS_MUST_NOT_BE_EMPTY")
        if regimes is not None and any(not item for item in regimes):
            raise ValueError("REGIME_LABELS_MUST_NOT_BE_EMPTY")

        # Kelly sizing requires per-trade returns normalized by capital at risk;
        # raw dollar PnL alone is not a defensible sizing input.
        kelly_result: dict[str, Any]
        if "r_multiple" in reader.fieldnames:
            r_multiples = [
                _number(row.get("r_multiple", ""), "R_MULTIPLE", index + 2)
                for index, row in enumerate(rows)
            ]
            kelly_result = quarter_kelly(r_multiples, minimum_trades=args.minimum_kelly_trades)
        else:
            kelly_result = {
                "status": "NOT_COMPUTED_REQUIRES_R_MULTIPLE_COLUMN",
                "decision": "NO_BET",
                "applied_fraction_after_cap": 0.0,
                "research_only": True,
            }

        output: dict[str, Any] = {
            "status": "DIAGNOSTICS_ONLY",
            "input_file": str(args.input),
            "trade_count": len(pnl),
            "net_expectancy": math.fsum(pnl) / len(pnl),
            "quarter_kelly": kelly_result,
            "dependence": outcome_dependence(pnl),
            "block_bootstrap": moving_block_bootstrap_ci(
                pnl,
                block_length=args.block_length,
                repetitions=args.bootstrap_repetitions,
                seed=args.seed,
            ),
            "overfitting_attacks": five_attack_overfitting_suite(
                pnl,
                assets=assets,
                regimes=regimes,
                omission_repetitions=args.omission_repetitions,
                seed=args.seed,
            ),
            "warnings": [
                "The CSV must be a frozen, point-in-time-valid trade ledger with realistic net costs.",
                "Block length is measured in ledger rows; 20 means 20 trades unless rows are daily observations.",
                "Robustness score is not a probability that the edge is real.",
                "This script does not produce an execution command.",
            ],
        }
        forecast_fields = {"outcome_binary", "baseline_probability", "augmented_probability"}
        present = forecast_fields.intersection(reader.fieldnames)
        if present and present != forecast_fields:
            raise ValueError("FORECAST_COLUMNS_MUST_BE_PROVIDED_TOGETHER")
        if present == forecast_fields:
            output["incremental_information_gain"] = incremental_log_likelihood_test(
                [
                    int(_number(row["outcome_binary"], "OUTCOME_BINARY", index + 2))
                    for index, row in enumerate(rows)
                ],
                [
                    _number(row["baseline_probability"], "BASELINE_PROBABILITY", index + 2)
                    for index, row in enumerate(rows)
                ],
                [
                    _number(row["augmented_probability"], "AUGMENTED_PROBABILITY", index + 2)
                    for index, row in enumerate(rows)
                ],
            )
    return output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_audit(args)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "trade_count": result["trade_count"],
                    "net_expectancy": result["net_expectancy"],
                    "bootstrap_ci_lower": result["block_bootstrap"]["ci_lower"],
                    "robustness_score": result["overfitting_attacks"]["robustness_score"],
                    "output": str(args.output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
