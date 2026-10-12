"""Tests for fail-closed sequence validation before market reconstruction."""
from researchos.orchestration.market_state_reconstruction import (
    EventClock,
    ParallelMarketStateEngine,
)
from researchos.orchestration.validated_market_state_reconstruction import (
    reconstruct_if_sequence_valid,
)


def clock(source: str, sequence: int, offset: int = 0) -> EventClock:
    base = 1_800_000_000_000_000_000 + offset
    return EventClock(source, base, base + 1, sequence)


def test_invalid_sequence_stream_blocks_reconstruction():
    engine = ParallelMarketStateEngine()
    result = reconstruct_if_sequence_valid(
        engine,
        event_clocks=[clock("COMEX", 20), clock("COMEX", 22, 1)],
        symbol="XAUUSD",
        decision_time_ns=1_800_000_000_000_100_000,
    )
    assert result.status == "SEQUENCE_INTEGRITY_FAILED"
    assert result.sequence_integrity.valid is False
    assert result.market_state is None
    assert "SEQUENCE_GAP" in result.sequence_integrity.issue_codes


def test_valid_sequence_stream_runs_existing_engine_without_changing_contract():
    engine = ParallelMarketStateEngine()
    result = reconstruct_if_sequence_valid(
        engine,
        event_clocks=[clock("COMEX", 20), clock("COMEX", 21, 1)],
        symbol="XAUUSD",
        decision_time_ns=1_800_000_000_000_100_000,
    )
    assert result.status == "RECONSTRUCTED"
    assert result.sequence_integrity.valid is True
    assert result.market_state is not None
    assert result.market_state["probabilities"] is None
    assert result.market_state["execution_enabled"] is False


def test_invalid_sequence_stream_does_not_call_reconstruction():
    class ForbiddenEngine:
        def reconstruct(self, **kwargs):
            raise AssertionError("reconstruction must not run for invalid sequence")

    result = reconstruct_if_sequence_valid(
        ForbiddenEngine(),  # type: ignore[arg-type]
        event_clocks=[clock("broker", 1), clock("broker", 1, 1)],
        symbol="XAUUSD",
        decision_time_ns=1_800_000_000_000_100_000,
    )
    assert result.status == "SEQUENCE_INTEGRITY_FAILED"
    assert result.market_state is None
