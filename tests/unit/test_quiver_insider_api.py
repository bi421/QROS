import hashlib
import json
from datetime import datetime, timezone

import pytest

from researchos.research_adapters import quiver_insider_api as quiver

UTC = timezone.utc
RETRIEVED = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def sample_record(**overrides):
    record = {
        "Ticker": "ACME",
        "Date": "2026-10-14T12:00:00Z",
        "Name": "Jane Insider",
        "AcquiredDisposedCode": "A",
        "TransactionCode": "P",
        "Shares": 100,
        "PricePerShare": 25.5,
        "fileDate": "2026-10-15T12:00:00Z",
        "officerTitle": "Chief Financial Officer",
        "directOrIndirectOwnership": "D",
    }
    record.update(overrides)
    return record


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit: int = -1):
        return self.payload if limit < 0 else self.payload[:limit]


def test_normalizer_preserves_times_and_does_not_assume_open_market():
    row = quiver.normalize_quiver_insider_record(sample_record(), retrieved_at=RETRIEVED)
    assert row.ticker == "ACME"
    assert row.amount_usd == pytest.approx(2550.0)
    assert row.event_at == datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert row.usable_at == datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    assert row.retrieved_at == RETRIEVED
    assert row.open_market_verified is None
    assert row.batch_status == "UNKNOWN"
    assert row.transaction_id.startswith("quiver:")


def test_explicit_market_verification_requires_purchase_and_acquisition():
    verified = quiver.normalize_quiver_insider_record(
        sample_record(openMarketVerified=True), retrieved_at=RETRIEVED
    )
    assert verified.open_market_verified is True
    disposed = quiver.normalize_quiver_insider_record(
        sample_record(openMarketVerified=True, AcquiredDisposedCode="D"),
        retrieved_at=RETRIEVED,
    )
    assert disposed.open_market_verified is False
    non_purchase = quiver.normalize_quiver_insider_record(
        sample_record(openMarketVerified=True, TransactionCode="S"),
        retrieved_at=RETRIEVED,
    )
    assert non_purchase.open_market_verified is False


def test_normalizer_rejects_missing_or_invalid_point_in_time_fields():
    with pytest.raises(ValueError, match="MISSING_TIMESTAMP:fileDate"):
        quiver.normalize_quiver_insider_record(sample_record(fileDate=None), retrieved_at=RETRIEVED)
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED:Date"):
        quiver.normalize_quiver_insider_record(
            sample_record(Date="2026-10-14T12:00:00"), retrieved_at=RETRIEVED
        )
    with pytest.raises(ValueError, match="FILE_DATE_AFTER_RETRIEVAL_TIME"):
        quiver.normalize_quiver_insider_record(
            sample_record(fileDate="2026-10-18T12:00:00Z"), retrieved_at=RETRIEVED
        )


def test_batch_normalizer_reports_bad_rows_without_silently_dropping_them():
    payload = json.dumps([sample_record(), {"Ticker": "MISSING_FIELDS"}]).encode()
    fetched = quiver.QuiverFetchResult(
        endpoint=quiver.QUIVER_INSIDER_ENDPOINT,
        retrieved_at=RETRIEVED,
        response_sha256=hashlib.sha256(payload).hexdigest(),
        raw_payload=payload,
        raw_records=tuple(json.loads(payload)),
    )
    accepted, rejected = quiver.normalize_quiver_insider_records(fetched)
    assert len(accepted) == 1
    assert rejected == [{"row_index": "1", "reason": "MISSING_INSIDER_NAME"}]


def test_fetch_uses_documented_https_endpoint_bearer_auth_and_hashes_raw_bytes(monkeypatch):
    payload = json.dumps([sample_record()]).encode()
    observed = {}

    def fake_urlopen(request, timeout):
        observed["url"] = request.full_url
        observed["authorization"] = request.get_header("Authorization")
        observed["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(quiver, "urlopen", fake_urlopen)
    result = quiver.fetch_quiver_insiders("test-token-not-real", timeout_seconds=4)
    assert observed["url"] == "https://api.quiverquant.com/beta/live/insiders"
    assert observed["authorization"] == "Bearer test-token-not-real"
    assert observed["timeout"] == 4.0
    assert result.raw_payload == payload
    assert result.response_sha256 == hashlib.sha256(payload).hexdigest()
    assert len(result.raw_records) == 1


def test_fetch_fails_closed_without_key_or_with_bad_response(monkeypatch):
    with pytest.raises(ValueError, match="QUIVER_API_KEY_REQUIRED"):
        quiver.fetch_quiver_insiders(api_key=" ")

    monkeypatch.setattr(quiver, "urlopen", lambda *_args, **_kwargs: FakeResponse(b"not-json"))
    with pytest.raises(ValueError, match="QUIVER_INVALID_JSON"):
        quiver.fetch_quiver_insiders("test-token-not-real")

    monkeypatch.setattr(quiver, "urlopen", lambda *_args, **_kwargs: FakeResponse(b"{}"))
    with pytest.raises(ValueError, match="QUIVER_RESPONSE_NOT_ARRAY"):
        quiver.fetch_quiver_insiders("test-token-not-real")
