"""Run a deterministic alternative-data audit on a normalized CSV export.

This is an offline research utility. It does not call a vendor API or place trades.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from researchos.orchestration.alternative_data_research import (
    BatchStatus,
    InsiderTransaction,
    screen_insider_clusters,
)


def _datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"INVALID_TIMESTAMP:{field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"TIMEZONE_REQUIRED:{field}")
    return parsed


def _optional_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    if normalized in {"", "unknown", "null", "none"}:
        return None
    raise ValueError("INVALID_OPEN_MARKET_VERIFIED")


def _batch_status(value: str | None) -> BatchStatus:
    normalized = (value or "UNKNOWN").strip().upper()
    allowed = {"CLEAR", "SUSPECT", "CONFIRMED_COMPENSATION", "UNKNOWN"}
    if normalized not in allowed:
        raise ValueError("INVALID_BATCH_STATUS")
    return cast(BatchStatus, normalized)


def load_normalized_csv(path: Path) -> list[InsiderTransaction]:
    required = {
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
    }
    records: list[InsiderTransaction] = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        missing = sorted(required - fields)
        if missing:
            raise ValueError("MISSING_REQUIRED_COLUMNS:" + ",".join(missing))
        for line_number, row in enumerate(reader, start=2):
            try:
                records.append(
                    InsiderTransaction(
                        transaction_id=row["transaction_id"],
                        ticker=row["ticker"].strip().upper(),
                        insider_id=row["insider_id"],
                        transaction_code=row["transaction_code"].strip().upper(),
                        event_at=_datetime(row["event_at"], "event_at"),
                        usable_at=_datetime(row["usable_at"], "usable_at"),
                        retrieved_at=_datetime(row["retrieved_at"], "retrieved_at"),
                        amount_usd=float(row["amount_usd"]),
                        source_ref=row["source_ref"],
                        open_market_verified=_optional_bool(row["open_market_verified"]),
                        batch_status=_batch_status(row.get("batch_status")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"INVALID_ROW:{line_number}:{exc}") from exc
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Normalized CSV file")
    parser.add_argument("--as-of", required=True, help="Timezone-aware ISO timestamp")
    parser.add_argument("--window-days", type=int, default=60)
    parser.add_argument("--min-insiders", type=int, default=3)
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        as_of = _datetime(args.as_of, "as_of")
        records = load_normalized_csv(args.input)
        result: dict[str, Any] = screen_insider_clusters(
            records,
            as_of=as_of,
            window_days=args.window_days,
            min_unique_insiders=args.min_insiders,
        )
        result["input_file"] = args.input.name
        result["input_row_count"] = len(records)
        result["source_data_status"] = "USER_SUPPLIED_NORMALIZED_CSV_NOT_VENDOR_VERIFIED"
        rendered = json.dumps(result, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
