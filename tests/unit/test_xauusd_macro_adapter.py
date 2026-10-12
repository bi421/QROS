"""Contract tests for the additive XAUUSD macro evidence adapter."""

from datetime import datetime, timedelta, timezone

import pytest

from researchos.macro.engine import ALL_DRIVERS
from researchos.orchestration.xauusd_macro_adapter import (
    MacroDriverObservation,
    XAUUSDMacroEvidenceAdapter,
    XAUUSDMacroSnapshot,
)
from researchos.orchestration.xauusd_research import (
    EngineStatus,
    XAUUSDResearchRequest,
)

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)


def request():
    return XAUUSDResearchRequest(
        run_id="macro-run-1",
        instrument="XAUUSD",
        decision_time=NOW,
        dataset_version="sha256:market-data",
        config_version="xauusd-fusion-v1",
    )


def observation(name, **overrides):
    values = {
        "driver_name": name,
        "score": 65.0,
        "confidence": 0.8,
        "gold_impact_direction": 1,
        "as_of": NOW - timedelta(minutes=5),
        "source_refs": ("source:macro-provider:item-1",),
        "max_age_seconds": 3600,
    }
    values.update(overrides)
    return MacroDriverObservation(**values)


def snapshot(**overrides):
    values = {
        "provider_id": "macro-provider-v1",
        "observations": tuple(observation(name) for name in ALL_DRIVERS),
    }
    values.update(overrides)
    return XAUUSDMacroSnapshot(**values)


def test_maps_all_ten_drivers_with_provenance_and_stable_ids():
    result = XAUUSDMacroEvidenceAdapter()(request(), snapshot())
    assert result.status is EngineStatus.OK
    assert len(result.evidence) == len(ALL_DRIVERS)
    assert result.evidence[0].evidence_id == f"macro-run-1:macro:{ALL_DRIVERS[0]}"
    assert result.evidence[0].source_refs == (
        "macro-provider-v1",
        "source:macro-provider:item-1",
    )
    assert result.evidence[0].direction == 1


def test_missing_driver_fails_closed_without_partial_evidence():
    result = XAUUSDMacroEvidenceAdapter()(
        request(), snapshot(observations=tuple(observation(name) for name in ALL_DRIVERS[:-1]))
    )
    assert result.status is EngineStatus.INSUFFICIENT
    assert result.evidence == ()
    assert result.reason_codes == (f"MACRO_DRIVER_MISSING:{ALL_DRIVERS[-1]}",)


def test_future_macro_observation_fails_closed():
    observations = list(snapshot().observations)
    observations[0] = observation(ALL_DRIVERS[0], as_of=NOW + timedelta(seconds=1))
    result = XAUUSDMacroEvidenceAdapter()(
        request(), XAUUSDMacroSnapshot("macro-provider-v1", tuple(observations))
    )
    assert result.status is EngineStatus.FAILED
    assert result.evidence == ()
    assert result.reason_codes == (f"FUTURE_MACRO_OBSERVATION:{ALL_DRIVERS[0]}",)


def test_stale_macro_observation_is_rejected():
    observations = list(snapshot().observations)
    observations[0] = observation(
        ALL_DRIVERS[0], as_of=NOW - timedelta(hours=2), max_age_seconds=60
    )
    result = XAUUSDMacroEvidenceAdapter()(
        request(), XAUUSDMacroSnapshot("macro-provider-v1", tuple(observations))
    )
    assert result.status is EngineStatus.INSUFFICIENT
    assert result.evidence == ()
    assert result.reason_codes == (f"STALE_MACRO_OBSERVATION:{ALL_DRIVERS[0]}",)


def test_missing_provider_is_reported_not_fabricated():
    result = XAUUSDMacroEvidenceAdapter()(request(), {"drivers": []})
    assert result.status is EngineStatus.NOT_CONFIGURED
    assert result.evidence == ()
    assert result.reason_codes == ("MACRO_PROVIDER_NOT_CONFIGURED",)


@pytest.mark.parametrize(
    "overrides",
    [
        {"score": float("nan")},
        {"score": 101.0},
        {"confidence": -0.1},
        {"gold_impact_direction": 2},
        {"source_refs": ()},
        {"max_age_seconds": 0},
    ],
)
def test_invalid_macro_observations_are_rejected(overrides):
    with pytest.raises(ValueError):
        observation(ALL_DRIVERS[0], **overrides)


def test_duplicate_driver_names_are_rejected():
    with pytest.raises(ValueError, match="DUPLICATE_MACRO_DRIVER"):
        XAUUSDMacroSnapshot(
            "macro-provider-v1",
            (observation(ALL_DRIVERS[0]), observation(ALL_DRIVERS[0])),
        )
