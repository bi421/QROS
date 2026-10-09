from datetime import datetime, timezone

from researchos.macro.time.timeline import TimeWindow, WindowType


def test_time_window_accepts_custom_metadata() -> None:
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    window = TimeWindow(
        window_type=WindowType.CUSTOM,
        start=t,
        end=t,
        event_time=t,
        metadata={"name": "custom"},
    )
    assert window.metadata == {"name": "custom"}
    assert isinstance(hash(window), int)
    assert isinstance(window.to_dict(), dict)
