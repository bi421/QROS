from datetime import datetime, timedelta, timezone

import pytest

from researchos.orchestration.alternative_data_research import (
    InsiderTransaction,
    adjust_hypothesis_p_values,
    deduplicate_transactions,
    detect_suspicious_batches,
    screen_insider_clusters,
)

UTC = timezone.utc
AS_OF = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def tx(
    transaction_id: str,
    insider_id: str,
    *,
    ticker: str = "ACME",
    event_at: datetime | None = None,
    usable_at: datetime | None = None,
    retrieved_at: datetime = AS_OF,
    amount_usd: float = 10000.0,
    code: str = "P",
    verified: bool | None = True,
    batch_status: str = "CLEAR",
) -> InsiderTransaction:
    event = event_at or AS_OF - timedelta(days=3)
    usable = usable_at or event + timedelta(days=1)
    return InsiderTransaction(
        transaction_id=transaction_id,
        ticker=ticker,
        insider_id=insider_id,
        transaction_code=code,
        event_at=event,
        usable_at=usable,
        retrieved_at=retrieved_at,
        amount_usd=amount_usd,
        source_ref=f"sec:{transaction_id}",
        open_market_verified=verified,
        batch_status=batch_status,  # type: ignore[arg-type]
    )


def test_cluster_requires_three_unique_verified_buyers():
    rows = [tx("1", "alice"), tx("2", "bob"), tx("3", "carol")]
    result = screen_insider_clusters(rows, as_of=AS_OF)
    candidate = result["candidates"][0]
    assert candidate["unique_verified_open_market_buyers"] == 3
    assert candidate["signal_candidate"] is True
    assert candidate["decision_use"] == "RESEARCH_CANDIDATE_ONLY_NOT_TRADE_SIGNAL"


def test_duplicate_transactions_do_not_inflate_cluster():
    original = tx("1", "alice")
    result = screen_insider_clusters([original, original, tx("2", "bob")], as_of=AS_OF)
    assert result["candidates"][0]["unique_verified_open_market_buyers"] == 2
    assert len(deduplicate_transactions([original, original])) == 1


def test_conflicting_duplicate_id_fails_closed():
    with pytest.raises(ValueError, match="CONFLICTING_DUPLICATE_TRANSACTION_ID"):
        deduplicate_transactions([tx("same", "alice"), tx("same", "bob")])


@pytest.mark.parametrize("verified", [False, None])
def test_unverified_open_market_purchase_is_excluded(verified):
    rows = [tx("1", "alice", verified=verified), tx("2", "bob"), tx("3", "carol")]
    candidate = screen_insider_clusters(rows, as_of=AS_OF)["candidates"][0]
    assert candidate["signal_candidate"] is False
    assert candidate["rejected_counts"]["OPEN_MARKET_BUY_NOT_VERIFIED"] == 1


def test_non_purchase_code_is_excluded():
    rows = [tx("1", "alice", code="A"), tx("2", "bob"), tx("3", "carol")]
    candidate = screen_insider_clusters(rows, as_of=AS_OF)["candidates"][0]
    assert candidate["signal_candidate"] is False


def test_future_public_availability_is_excluded():
    future = AS_OF + timedelta(hours=1)
    rows = [
        tx("1", "alice", usable_at=future, retrieved_at=future),
        tx("2", "bob"),
        tx("3", "carol"),
    ]
    result = screen_insider_clusters(rows, as_of=AS_OF)
    candidate = result["candidates"][0]
    assert candidate["signal_candidate"] is False
    assert candidate["rejected_counts"]["NOT_YET_PUBLIC"] == 1
    # The future-public third record must not make the two known records look like a batch.
    assert result["suspicious_batches"] == []


def test_suspicious_batch_fails_closed_until_explicitly_reviewed():
    rows = [tx(str(i), f"person-{i}", batch_status="UNKNOWN") for i in range(3)]
    flags = detect_suspicious_batches(rows)
    assert len(flags) == 1
    assert flags[0]["status"] == "REVIEW_REQUIRED"
    candidate = screen_insider_clusters(rows, as_of=AS_OF)["candidates"][0]
    assert candidate["signal_candidate"] is False
    assert candidate["rejected_counts"]["BATCH_PATTERN_REVIEW_REQUIRED"] == 3
    assert len(screen_insider_clusters(rows, as_of=AS_OF)["suspicious_batches"]) == 1

    # Only explicit source review can clear the suspicious-pattern hold.
    reviewed = [tx(str(i), f"person-{i}", batch_status="CLEAR") for i in range(3)]
    reviewed_result = screen_insider_clusters(reviewed, as_of=AS_OF)
    candidate_reviewed = reviewed_result["candidates"][0]
    assert candidate_reviewed["signal_candidate"] is True
    assert reviewed_result["suspicious_batches"][0]["status"] == "REVIEWED_CLEAR"


def test_batch_detector_counts_unique_people_not_rows():
    rows = [tx("1", "alice"), tx("2", "alice"), tx("3", "bob")]
    assert detect_suspicious_batches(rows) == []


def test_batch_amount_tolerance_is_explicit():
    rows = [
        tx("1", "alice", amount_usd=10000),
        tx("2", "bob", amount_usd=10000.5),
        tx("3", "carol", amount_usd=10001),
    ]
    assert detect_suspicious_batches(rows, amount_tolerance_usd=0.0) == []
    assert detect_suspicious_batches(rows, amount_tolerance_usd=1.0)[0]["unique_insider_count"] == 3


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="EVENT_AT_MUST_BE_TIMEZONE_AWARE"):
        tx("1", "alice", event_at=datetime(2026, 10, 1))


def test_usable_at_before_event_is_rejected():
    event = AS_OF - timedelta(days=1)
    with pytest.raises(ValueError, match="USABLE_AT_PRECEDES_EVENT_AT"):
        tx("1", "alice", event_at=event, usable_at=event - timedelta(seconds=1))


def test_invalid_cluster_parameters_are_rejected():
    with pytest.raises(ValueError, match="WINDOW_DAYS_MUST_BE_POSITIVE_INTEGER"):
        screen_insider_clusters([], as_of=AS_OF, window_days=0)
    with pytest.raises(ValueError, match="AS_OF_MUST_BE_TIMEZONE_AWARE"):
        screen_insider_clusters([], as_of=datetime(2026, 10, 17))


def test_bh_correction_preserves_input_order_and_flags_multiplicity():
    result = adjust_hypothesis_p_values(
        [
            {"hypothesis_id": "h1", "p_value": 0.001},
            {"hypothesis_id": "h2", "p_value": 0.04},
            {"hypothesis_id": "h3", "p_value": 0.7},
        ]
    )
    assert [item["hypothesis_id"] for item in result] == ["h1", "h2", "h3"]
    assert result[0]["reject_at_q"] is True
    assert result[2]["reject_at_q"] is False
    assert result[0]["interpretation"] == "MULTIPLE_TESTING_ADJUSTED_NOT_PROOF_OF_EDGE"


def test_bh_rejects_duplicate_hypothesis_ids_and_bad_p_values():
    with pytest.raises(ValueError, match="DUPLICATE_HYPOTHESIS_ID"):
        adjust_hypothesis_p_values(
            [
                {"hypothesis_id": "same", "p_value": 0.01},
                {"hypothesis_id": "same", "p_value": 0.02},
            ]
        )
    with pytest.raises(ValueError, match="INVALID_P_VALUE"):
        adjust_hypothesis_p_values([{"hypothesis_id": "h1", "p_value": float("nan")}])
