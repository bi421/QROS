from datetime import datetime, timezone

from researchos.market_memory.event_schema import EventOutcome


def test_to_dict_preserves_every_forward_outcome_field() -> None:
    outcome = EventOutcome(
        event_id="event-1",
        asset="XAUUSD",
        timeframe="D1",
        event_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        return_1d=0.01,
        return_2d=0.02,
        return_3d=0.03,
        return_5d=0.05,
        return_10d=0.10,
        return_20d=0.20,
        direction_1d="up",
        direction_2d="up",
        direction_3d="up",
        direction_5d="up",
        direction_10d="up",
        direction_20d="up",
        mfe_1d=0.04,
        mae_1d=-0.01,
        mfe_5d=0.06,
        mae_5d=-0.02,
        mfe_20d=0.08,
        mae_20d=-0.03,
        hit_threshold_1d=True,
        hit_threshold_5d=True,
        hit_threshold_20d=False,
    )

    serialized = outcome.to_dict()

    expected = {
        "return_1d": 0.01,
        "return_2d": 0.02,
        "return_3d": 0.03,
        "return_5d": 0.05,
        "return_10d": 0.10,
        "return_20d": 0.20,
        "direction_1d": "up",
        "direction_2d": "up",
        "direction_3d": "up",
        "direction_5d": "up",
        "direction_10d": "up",
        "direction_20d": "up",
        "mfe_1d": 0.04,
        "mae_1d": -0.01,
        "mfe_5d": 0.06,
        "mae_5d": -0.02,
        "mfe_20d": 0.08,
        "mae_20d": -0.03,
        "hit_threshold_1d": True,
        "hit_threshold_5d": True,
        "hit_threshold_20d": False,
    }
    for field, value in expected.items():
        assert serialized[field] == value, field
