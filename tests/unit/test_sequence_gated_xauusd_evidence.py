from datetime import datetime, timezone

from researchos.orchestration.market_state_reconstruction import EventClock
from researchos.orchestration.sequence_gated_xauusd_evidence import (
    reconstruct_xauusd_evidence_if_sequence_valid,
)
from researchos.orchestration.xauusd_research import (
    EngineStatus,
    XAUUSDResearchRequest,
)


def _request() -> XAUUSDResearchRequest:
    return XAUUSDResearchRequest(
        run_id="sequence-gate-test",
        instrument="XAUUSD",
        decision_time=datetime.fromtimestamp(1_800_000_000, tz=timezone.utc),
        dataset_version="fixture-v1",
        config_version="config-v1",
    )


def _clock(source: str, sequence: int, offset_ns: int = 0) -> EventClock:
    event_time = 1_800_000_000_000_000_000 + offset_ns
    return EventClock(source, event_time, event_time + 1, sequence)


class _Engine:
    def __init__(self) -> None:
        self.calls = 0

    def reconstruct(self, **kwargs: object) -> dict[str, object]:
        self.calls += 1
        return {
            "instrument": "XAUUSD",
            "decision_time_ns": 1_800_000_000_000_000_000,
            "features": {},
            "probabilities": None,
            "execution_enabled": False,
        }


def test_sequence_gap_blocks_reconstruction_and_evidence_adapter() -> None:
    engine = _Engine()
    result = reconstruct_xauusd_evidence_if_sequence_valid(
        _request(),
        engine,  # type: ignore[arg-type]
        event_clocks=[_clock("COMEX", 10), _clock("COMEX", 12, 1)],
    )

    assert result.reconstruction.status == "SEQUENCE_INTEGRITY_FAILED"
    assert result.reconstruction.market_state is None
    assert engine.calls == 0
    assert result.evidence_result.status == EngineStatus.INSUFFICIENT
    assert result.evidence_result.evidence == ()
    assert result.evidence_result.reason_codes == ("SEQUENCE_INTEGRITY_FAILED",)


def test_valid_sequence_reconstructs_then_applies_existing_source_gate() -> None:
    engine = _Engine()
    result = reconstruct_xauusd_evidence_if_sequence_valid(
        _request(),
        engine,  # type: ignore[arg-type]
        event_clocks=[_clock("COMEX", 10), _clock("COMEX", 11, 1)],
    )

    assert result.reconstruction.status == "RECONSTRUCTED"
    assert engine.calls == 1
    # Empty feature inputs must not be upgraded into partial/false evidence.
    assert result.evidence_result.status == EngineStatus.INSUFFICIENT
    assert result.evidence_result.evidence == ()
    assert any(
        code.startswith("SOURCE_MISSING:")
        for code in result.evidence_result.reason_codes
    )
