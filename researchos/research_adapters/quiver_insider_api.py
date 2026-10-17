"""Quiver Quant insider API connector with point-in-time-safe normalization.

Endpoint and sample field names follow Quiver's published Insider Trades API.
No API key is embedded. The public sample schema does not prove open-market
status, so normalized records remain unverified unless the response explicitly
contains an affirmative `openMarketVerified` field.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from researchos.orchestration.alternative_data_research import InsiderTransaction

QUIVER_INSIDER_ENDPOINT = "https://api.quiverquant.com/beta/live/insiders"
QUIVER_ADAPTER_VERSION = "QUIVER_INSIDER_ADAPTER_V1"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class QuiverFetchResult:
    endpoint: str
    retrieved_at: datetime
    response_sha256: str
    raw_payload: bytes
    raw_records: tuple[dict[str, Any], ...]


def fetch_quiver_insiders(
    api_key: str | None = None,
    *,
    timeout_seconds: float = 20.0,
) -> QuiverFetchResult:
    """Fetch the documented live-insiders endpoint; never log the credential."""
    token = api_key or os.environ.get("QUIVER_API_KEY")
    if not isinstance(token, str) or not token.strip():
        raise ValueError("QUIVER_API_KEY_REQUIRED")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("INVALID_TIMEOUT")
    if not math.isfinite(float(timeout_seconds)) or not 0.1 <= float(timeout_seconds) <= 120.0:
        raise ValueError("INVALID_TIMEOUT")

    request = Request(
        QUIVER_INSIDER_ENDPOINT,
        headers={
            "Authorization": f"Bearer {token.strip()}",
            "Accept": "application/json",
            "User-Agent": "QROS-AlternativeDataResearch/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=float(timeout_seconds)) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise ValueError(f"QUIVER_HTTP_STATUS:{status}")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise ValueError(f"QUIVER_HTTP_STATUS:{exc.code}") from None
    except URLError:
        raise ValueError("QUIVER_CONNECTION_FAILED") from None

    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("QUIVER_RESPONSE_TOO_LARGE")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("QUIVER_INVALID_JSON") from None
    if not isinstance(decoded, list):
        raise ValueError("QUIVER_RESPONSE_NOT_ARRAY")
    if any(not isinstance(item, dict) for item in decoded):
        raise ValueError("QUIVER_RESPONSE_HAS_NON_OBJECT_RECORD")

    retrieved_at = datetime.now(timezone.utc)
    return QuiverFetchResult(
        endpoint=QUIVER_INSIDER_ENDPOINT,
        retrieved_at=retrieved_at,
        response_sha256=hashlib.sha256(payload).hexdigest(),
        raw_payload=payload,
        raw_records=tuple(decoded),
    )


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"MISSING_TIMESTAMP:{field}")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"INVALID_TIMESTAMP:{field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"TIMEZONE_REQUIRED:{field}")
    return parsed


def normalize_quiver_insider_record(
    record: dict[str, Any],
    *,
    retrieved_at: datetime,
) -> InsiderTransaction:
    """Normalize one provider row; do not infer unreported market execution."""
    if not isinstance(record, dict):
        raise ValueError("INVALID_QUIVER_RECORD")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("RETRIEVED_AT_MUST_BE_TIMEZONE_AWARE")

    ticker = record.get("Ticker")
    name = record.get("Name")
    code = record.get("TransactionCode")
    acquired_disposed = record.get("AcquiredDisposedCode")
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("MISSING_TICKER")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("MISSING_INSIDER_NAME")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("MISSING_TRANSACTION_CODE")

    event_at = _parse_timestamp(record.get("Date"), "Date")
    usable_at = _parse_timestamp(record.get("fileDate"), "fileDate")
    if usable_at > retrieved_at:
        raise ValueError("FILE_DATE_AFTER_RETRIEVAL_TIME")

    try:
        shares = float(record["Shares"])
        price = float(record["PricePerShare"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("MISSING_OR_INVALID_SHARES_PRICE") from exc
    if (
        isinstance(record.get("Shares"), bool)
        or isinstance(record.get("PricePerShare"), bool)
        or not math.isfinite(shares)
        or not math.isfinite(price)
        or shares < 0
        or price < 0
    ):
        raise ValueError("INVALID_SHARES_PRICE")

    stable_fields = {
        key: record.get(key)
        for key in (
            "Ticker",
            "Name",
            "Date",
            "fileDate",
            "TransactionCode",
            "AcquiredDisposedCode",
            "Shares",
            "PricePerShare",
            "directOrIndirectOwnership",
            "officerTitle",
        )
    }
    stable_json = json.dumps(stable_fields, sort_keys=True, separators=(",", ":"), default=str)
    transaction_id = hashlib.sha256(stable_json.encode("utf-8")).hexdigest()

    explicit_market_flag = record.get("openMarketVerified")
    verified: bool | None = None
    if isinstance(explicit_market_flag, bool):
        verified = explicit_market_flag
    # The provider's documented sample schema does not include this flag.
    # A true flag is accepted only for a reported acquisition with code P.
    if verified is True and not (
        code.strip().upper() == "P" and str(acquired_disposed).upper() == "A"
    ):
        verified = False

    return InsiderTransaction(
        transaction_id=f"quiver:{transaction_id}",
        ticker=ticker.strip().upper(),
        insider_id=name.strip().casefold(),
        transaction_code=code.strip().upper(),
        event_at=event_at,
        usable_at=usable_at,
        retrieved_at=retrieved_at,
        amount_usd=shares * price,
        source_ref=f"quiver:live/insiders:sha256:{transaction_id}",
        open_market_verified=verified,
        batch_status="UNKNOWN",
    )


def normalize_quiver_insider_records(
    result: QuiverFetchResult,
) -> tuple[list[InsiderTransaction], list[dict[str, str]]]:
    """Normalize valid rows and retain explicit per-row rejection reasons."""
    accepted: list[InsiderTransaction] = []
    rejected: list[dict[str, str]] = []
    for index, record in enumerate(result.raw_records):
        try:
            accepted.append(
                normalize_quiver_insider_record(record, retrieved_at=result.retrieved_at)
            )
        except ValueError as exc:
            rejected.append({"row_index": str(index), "reason": str(exc)})
    return accepted, rejected


__all__ = [
    "QUIVER_INSIDER_ENDPOINT",
    "QUIVER_ADAPTER_VERSION",
    "QuiverFetchResult",
    "fetch_quiver_insiders",
    "normalize_quiver_insider_record",
    "normalize_quiver_insider_records",
]
