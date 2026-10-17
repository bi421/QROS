"""Fetch Quiver insider records and persist raw + normalized evidence artifacts.

Requires QUIVER_API_KEY in the environment. No credential is accepted as a CLI
argument, printed, or written to output files.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from researchos.research_adapters.quiver_insider_api import (
    QUIVER_ADAPTER_VERSION,
    fetch_quiver_insiders,
    normalize_quiver_insider_records,
)

CSV_FIELDS = [
    "transaction_id",
    "ticker",
    "insider_id",
    "transaction_code",
    "event_at",
    "usable_at",
    "retrieved_at",
    "amount_usd",
    "source_ref",
    "open_market_verified",
    "batch_status",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-output", required=True, type=Path)
    parser.add_argument("--csv-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    return parser


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fetched = fetch_quiver_insiders(timeout_seconds=args.timeout_seconds)
        normalized, rejected = normalize_quiver_insider_records(fetched)

        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_bytes(fetched.raw_payload)
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in normalized:
                writer.writerow(
                    {
                        "transaction_id": row.transaction_id,
                        "ticker": row.ticker,
                        "insider_id": row.insider_id,
                        "transaction_code": row.transaction_code,
                        "event_at": row.event_at.isoformat(),
                        "usable_at": row.usable_at.isoformat(),
                        "retrieved_at": row.retrieved_at.isoformat(),
                        "amount_usd": row.amount_usd,
                        "source_ref": row.source_ref,
                        "open_market_verified": (
                            "unknown"
                            if row.open_market_verified is None
                            else str(row.open_market_verified).lower()
                        ),
                        "batch_status": row.batch_status,
                    }
                )

        manifest: dict[str, Any] = {
            "adapter_version": QUIVER_ADAPTER_VERSION,
            "endpoint": fetched.endpoint,
            "retrieved_at": fetched.retrieved_at.isoformat(),
            "response_sha256": fetched.response_sha256,
            "raw_record_count": len(fetched.raw_records),
            "normalized_record_count": len(normalized),
            "rejected_record_count": len(rejected),
            "rejected_records": rejected,
            "raw_output": str(args.raw_output),
            "csv_output": str(args.csv_output),
            "status": "FETCHED_NORMALIZED_BUT_OPEN_MARKET_NOT_VERIFIED_BY_DEFAULT",
            "limitations": [
                "API access and entitlement were used for this fetch only; historical completeness is not proven.",
                "The documented provider fields do not by themselves prove open-market execution.",
                "Name-based insider identity can undercount or misidentify people with matching names.",
                "No XAUUSD predictive edge is established by ingestion or clustering.",
            ],
        }
        _write_text(args.manifest_output, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "raw_records": len(fetched.raw_records),
                    "normalized_records": len(normalized),
                    "rejected_records": len(rejected),
                    "response_sha256": fetched.response_sha256,
                    "manifest_output": str(args.manifest_output),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
