"""Fail-closed research primitives for timestamped alternative data.

This module does not fetch vendor data and does not emit trade instructions.
Provider-specific connectors must map verified source fields into the immutable
records below. Unknown open-market status and suspicious batches are excluded.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from researchos.orchestration.statistical_validation import benjamini_hochberg

ALTERNATIVE_DATA_RESEARCH_VERSION = "ALTERNATIVE_DATA_RESEARCH_V1"
BatchStatus = Literal["CLEAR", "SUSPECT", "CONFIRMED_COMPENSATION", "UNKNOWN"]


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")


def _finite_nonnegative(value: float, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"INVALID_{field.upper()}")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"INVALID_{field.upper()}")


@dataclass(frozen=True, slots=True)
class InsiderTransaction:
    """One normalized filing transaction with explicit point-in-time provenance.

    `open_market_verified` must only be True when the provider/source evidence
    establishes an open-market purchase; transaction code P alone is not enough.
    `usable_at` is the earliest defensible public availability time for backtests.
    """

    transaction_id: str
    ticker: str
    insider_id: str
    transaction_code: str
    event_at: datetime
    usable_at: datetime
    retrieved_at: datetime
    amount_usd: float
    source_ref: str
    open_market_verified: bool | None
    batch_status: BatchStatus = "UNKNOWN"

    def __post_init__(self) -> None:
        for field in ("transaction_id", "ticker", "insider_id", "transaction_code", "source_ref"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field.upper()}_REQUIRED")
        if self.ticker != self.ticker.upper() or self.ticker.strip() != self.ticker:
            raise ValueError("TICKER_MUST_BE_NORMALIZED_UPPERCASE")
        for field in ("event_at", "usable_at", "retrieved_at"):
            _aware(getattr(self, field), field)
        if self.usable_at < self.event_at:
            # A public filing timestamp can be after the transaction. If it is
            # earlier, provider mapping is inconsistent and must be reviewed.
            raise ValueError("USABLE_AT_PRECEDES_EVENT_AT")
        if self.retrieved_at < self.usable_at:
            raise ValueError("RETRIEVED_AT_PRECEDES_USABLE_AT")
        _finite_nonnegative(self.amount_usd, "amount_usd")
        if self.open_market_verified is not None and not isinstance(
            self.open_market_verified, bool
        ):
            raise ValueError("INVALID_OPEN_MARKET_VERIFICATION")
        if self.batch_status not in ("CLEAR", "SUSPECT", "CONFIRMED_COMPENSATION", "UNKNOWN"):
            raise ValueError("INVALID_BATCH_STATUS")


def deduplicate_transactions(rows: Iterable[InsiderTransaction]) -> list[InsiderTransaction]:
    """Deduplicate by source transaction ID; reject conflicting duplicates."""
    by_id: dict[str, InsiderTransaction] = {}
    for row in rows:
        if not isinstance(row, InsiderTransaction):
            raise ValueError("INVALID_TRANSACTION_RECORD")
        previous = by_id.get(row.transaction_id)
        if previous is not None and previous != row:
            raise ValueError("CONFLICTING_DUPLICATE_TRANSACTION_ID")
        by_id[row.transaction_id] = row
    return sorted(by_id.values(), key=lambda row: (row.usable_at, row.transaction_id))


def detect_suspicious_batches(
    rows: Iterable[InsiderTransaction],
    *,
    min_unique_insiders: int = 3,
    amount_tolerance_usd: float = 0.0,
) -> list[dict[str, Any]]:
    """Flag repeated ticker/date/amount/code groups for human/source review.

    Flags are not proof of compensation and do not mutate input records.
    `event_at` is bucketed by UTC calendar date. Amount matching uses the
    explicit tolerance; exact matching is the default.
    """
    if (
        isinstance(min_unique_insiders, bool)
        or not isinstance(min_unique_insiders, int)
        or min_unique_insiders < 2
    ):
        raise ValueError("MIN_UNIQUE_INSIDERS_MUST_BE_AT_LEAST_2")
    _finite_nonnegative(amount_tolerance_usd, "amount_tolerance_usd")
    grouped: dict[tuple[str, date, str], list[InsiderTransaction]] = defaultdict(list)
    unique = deduplicate_transactions(rows)
    for row in unique:
        grouped[
            (row.ticker, row.event_at.astimezone(timezone.utc).date(), row.transaction_code)
        ].append(row)

    findings: list[dict[str, Any]] = []
    for (ticker, event_date, code), group in sorted(grouped.items(), key=lambda item: item[0]):
        by_amount: list[list[InsiderTransaction]] = []
        for row in sorted(group, key=lambda item: item.amount_usd):
            matching = next(
                (
                    bucket
                    for bucket in by_amount
                    if abs(bucket[0].amount_usd - row.amount_usd) <= amount_tolerance_usd
                ),
                None,
            )
            if matching is None:
                by_amount.append([row])
            else:
                matching.append(row)
        for bucket in by_amount:
            insiders = sorted({row.insider_id for row in bucket})
            if len(insiders) >= min_unique_insiders:
                findings.append(
                    {
                        "ticker": ticker,
                        "event_date_utc": event_date.isoformat(),
                        "transaction_code": code,
                        "amount_usd": bucket[0].amount_usd,
                        "transaction_count": len(bucket),
                        "unique_insider_count": len(insiders),
                        "transaction_ids": sorted(row.transaction_id for row in bucket),
                        "status": "REVIEW_REQUIRED",
                        "reason": "SIMILAR_DATE_AMOUNT_CODE_PATTERN_NOT_PROOF_OF_COMPENSATION",
                    }
                )
    return findings


def screen_insider_clusters(
    rows: Iterable[InsiderTransaction],
    *,
    as_of: datetime,
    window_days: int = 60,
    min_unique_insiders: int = 3,
) -> dict[str, Any]:
    """Build point-in-time cluster candidates; this is not a trading signal.

    Only verified open-market buys with a CLEAR batch status are counted.
    Any transaction not yet usable at `as_of` is excluded and reported.
    """
    _aware(as_of, "as_of")
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days < 1:
        raise ValueError("WINDOW_DAYS_MUST_BE_POSITIVE_INTEGER")
    if (
        isinstance(min_unique_insiders, bool)
        or not isinstance(min_unique_insiders, int)
        or min_unique_insiders < 1
    ):
        raise ValueError("MIN_UNIQUE_INSIDERS_MUST_BE_POSITIVE_INTEGER")

    unique = deduplicate_transactions(rows)
    start = as_of - timedelta(days=window_days)
    point_in_time_rows = [
        row for row in unique if row.usable_at <= as_of and start <= row.event_at <= as_of
    ]
    batch_findings = detect_suspicious_batches(point_in_time_rows)
    by_transaction_id = {row.transaction_id: row for row in point_in_time_rows}
    for finding in batch_findings:
        reviewed_rows = [by_transaction_id[item] for item in finding["transaction_ids"]]
        if all(row.batch_status == "CLEAR" for row in reviewed_rows):
            finding["status"] = "REVIEWED_CLEAR"
            finding["reason"] = "EXPLICIT_SOURCE_REVIEW_CLEARED_PATTERN"
    pattern_ids = {
        transaction_id
        for finding in batch_findings
        for transaction_id in finding["transaction_ids"]
    }
    counts: dict[str, set[str]] = defaultdict(set)
    accepted_ids: dict[str, list[str]] = defaultdict(list)
    rejected: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for row in unique:
        if row.usable_at > as_of:
            rejected[row.ticker]["NOT_YET_PUBLIC"] += 1
            continue
        event_at = row.event_at
        if not (start <= event_at <= as_of):
            rejected[row.ticker]["OUTSIDE_EVENT_WINDOW"] += 1
            continue
        if row.transaction_code.upper() != "P" or row.open_market_verified is not True:
            rejected[row.ticker]["OPEN_MARKET_BUY_NOT_VERIFIED"] += 1
            continue
        if row.batch_status != "CLEAR":
            reason = (
                "BATCH_PATTERN_REVIEW_REQUIRED"
                if row.transaction_id in pattern_ids
                else f"BATCH_{row.batch_status}"
            )
            rejected[row.ticker][reason] += 1
            continue
        counts[row.ticker].add(row.insider_id)
        accepted_ids[row.ticker].append(row.transaction_id)

    tickers = sorted(set(counts) | set(rejected))
    candidates = []
    for ticker in tickers:
        insider_count = len(counts[ticker])
        candidates.append(
            {
                "ticker": ticker,
                "window_start": start.isoformat(),
                "as_of": as_of.isoformat(),
                "unique_verified_open_market_buyers": insider_count,
                "transaction_ids": sorted(accepted_ids[ticker]),
                "signal_candidate": insider_count >= min_unique_insiders,
                "status": "CANDIDATE" if insider_count >= min_unique_insiders else "NO_CLUSTER",
                "rejected_counts": dict(sorted(rejected[ticker].items())),
                "decision_use": "RESEARCH_CANDIDATE_ONLY_NOT_TRADE_SIGNAL",
            }
        )
    return {
        "version": ALTERNATIVE_DATA_RESEARCH_VERSION,
        "status": "COMPUTED_RESEARCH_DIAGNOSTIC",
        "as_of": as_of.isoformat(),
        "window_days": window_days,
        "minimum_unique_insiders": min_unique_insiders,
        "suspicious_batches": batch_findings,
        "candidates": candidates,
        "limitations": [
            "No vendor/API data is fetched by this module.",
            "Provider must prove transaction code mapping, open-market status and usable_at.",
            "A cluster is not evidence of predictive edge without preregistered out-of-sample testing.",
        ],
    }


def adjust_hypothesis_p_values(
    hypotheses: Iterable[dict[str, Any]],
    *,
    q: float = 0.05,
) -> list[dict[str, Any]]:
    """Apply the project's existing Benjamini-Hochberg correction to hypotheses."""
    materialized = list(hypotheses)
    ids: list[str] = []
    p_values: list[float] = []
    for item in materialized:
        hypothesis_id = item.get("hypothesis_id")
        p_value = item.get("p_value")
        if not isinstance(hypothesis_id, str) or not hypothesis_id.strip():
            raise ValueError("HYPOTHESIS_ID_REQUIRED")
        if (
            isinstance(p_value, bool)
            or not isinstance(p_value, (int, float))
            or not math.isfinite(float(p_value))
            or not 0.0 <= float(p_value) <= 1.0
        ):
            raise ValueError("INVALID_P_VALUE")
        ids.append(hypothesis_id)
        p_values.append(float(p_value))
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_HYPOTHESIS_ID")
    adjusted = benjamini_hochberg(p_values, q=q)
    return [
        {
            "hypothesis_id": ids[index],
            **result,
            "interpretation": "MULTIPLE_TESTING_ADJUSTED_NOT_PROOF_OF_EDGE",
        }
        for index, result in enumerate(adjusted)
    ]


__all__ = [
    "ALTERNATIVE_DATA_RESEARCH_VERSION",
    "InsiderTransaction",
    "deduplicate_transactions",
    "detect_suspicious_batches",
    "screen_insider_clusters",
    "adjust_hypothesis_p_values",
]
