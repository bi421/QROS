from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from researchos.quant_engine.technical.market_structure import detect_market_structure
from researchos.quant_engine.technical.market_structure_adapter import (
    MarketStructureInput,
    market_structure_input_from_frame,
)


def frame_fixture() -> pd.DataFrame:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return pd.DataFrame(
        {
            "time": [start + timedelta(minutes=i) for i in range(4)],
            "open": [10.0, 10.5, 11.0, 10.8],
            "high": [11.0, 12.0, 11.5, 11.2],
            "low": [9.0, 10.0, 10.5, 10.2],
            "close": [10.5, 11.5, 10.8, 10.9],
            "spread": [15, 16, 17, 18],
            "tick_volume": [100, 110, 120, 130],
            "real_volume": [2, 3, 4, 5],
        }
    )


def test_adapter_preserves_ohlc_timestamps_and_mt5_metadata() -> None:
    frame = frame_fixture()
    result = market_structure_input_from_frame(frame, symbol="XAUUSD")
    assert isinstance(result, MarketStructureInput)
    assert result.symbol == "XAUUSD"
    assert result.timeframe == "M1"
    assert result.row_count == 4
    assert result.open == (10.0, 10.5, 11.0, 10.8)
    assert result.high == (11.0, 12.0, 11.5, 11.2)
    assert result.low == (9.0, 10.0, 10.5, 10.2)
    assert result.close == (10.5, 11.5, 10.8, 10.9)
    assert result.spread_points == (15.0, 16.0, 17.0, 18.0)
    assert result.tick_volume == (100.0, 110.0, 120.0, 130.0)
    assert result.real_volume == (2.0, 3.0, 4.0, 5.0)
    assert result.timestamps == tuple(value.to_pydatetime() for value in frame["time"])


def test_adapter_is_read_only_and_does_not_reorder_rows() -> None:
    frame = frame_fixture()
    before = frame.copy(deep=True)
    result = market_structure_input_from_frame(frame, symbol="XAUUSD")
    pd.testing.assert_frame_equal(frame, before)
    assert result.timestamps[0] == before.loc[0, "time"].to_pydatetime()


def test_adapter_preserves_gaps_without_inserting_bars() -> None:
    frame = frame_fixture()
    frame.loc[2:, "time"] = frame.loc[2:, "time"] + timedelta(minutes=5)
    result = market_structure_input_from_frame(frame, symbol="XAUUSD")
    assert result.row_count == len(frame) == 4
    assert (result.timestamps[2] - result.timestamps[1]).total_seconds() == 360


def test_adapter_supports_custom_timestamp_column() -> None:
    frame = frame_fixture().rename(columns={"time": "timestamp"})
    result = market_structure_input_from_frame(
        frame, symbol="XAUUSD", timestamp_column="timestamp"
    )
    assert result.row_count == 4


def test_adapter_optional_metadata_can_be_absent_or_null() -> None:
    frame = frame_fixture().drop(columns=["spread", "tick_volume", "real_volume"])
    result = market_structure_input_from_frame(frame, symbol="XAUUSD")
    assert result.spread_points == (None,) * 4
    assert result.tick_volume == (None,) * 4
    assert result.real_volume == (None,) * 4

    frame["spread"] = [15.0, np.nan, 17.0, 18.0]
    result = market_structure_input_from_frame(frame, symbol="XAUUSD")
    assert result.spread_points == (15.0, None, 17.0, 18.0)


def test_adapter_rejects_non_dataframe_input() -> None:
    with pytest.raises(TypeError, match="pandas DataFrame"):
        market_structure_input_from_frame([], symbol="XAUUSD")  # type: ignore[arg-type]


def test_adapter_rejects_empty_frame() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        market_structure_input_from_frame(frame_fixture().iloc[:0], symbol="XAUUSD")


def test_adapter_rejects_duplicate_column_names() -> None:
    frame = frame_fixture()
    frame.columns = ["time", "open", "high", "low", "close", "spread", "tick_volume", "time"]
    with pytest.raises(ValueError, match="duplicate column"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_missing_required_columns() -> None:
    frame = frame_fixture().drop(columns=["low"])
    with pytest.raises(ValueError, match="missing required columns"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


@pytest.mark.parametrize("timeframe", ["M5", "M15", "H1", "1min"])
def test_adapter_rejects_non_m1_timeframe(timeframe: str) -> None:
    with pytest.raises(ValueError, match="M1 only"):
        market_structure_input_from_frame(frame_fixture(), symbol="XAUUSD", timeframe=timeframe)


@pytest.mark.parametrize("symbol", ["", " XAUUSD", "XAUUSD "])
def test_adapter_rejects_invalid_symbol(symbol: str) -> None:
    with pytest.raises(ValueError, match="symbol"):
        market_structure_input_from_frame(frame_fixture(), symbol=symbol)


def test_adapter_rejects_string_timestamps() -> None:
    frame = frame_fixture()
    frame["time"] = frame["time"].astype(str)
    with pytest.raises(TypeError, match="datetime values"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_naive_timestamps() -> None:
    frame = frame_fixture()
    frame["time"] = frame["time"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_non_utc_timestamps() -> None:
    frame = frame_fixture()
    frame["time"] = frame["time"].dt.tz_convert("Europe/London")
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_duplicate_and_out_of_order_timestamps() -> None:
    frame = frame_fixture()
    frame.loc[2, "time"] = frame.loc[1, "time"]
    with pytest.raises(ValueError, match="strictly increasing"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")

    frame = frame_fixture()
    frame.loc[2, "time"], frame.loc[3, "time"] = frame.loc[3, "time"], frame.loc[2, "time"]
    with pytest.raises(ValueError, match="strictly increasing"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_non_minute_aligned_timestamps() -> None:
    frame = frame_fixture()
    frame.loc[2, "time"] += timedelta(seconds=15)
    with pytest.raises(ValueError, match="whole minutes"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
def test_adapter_rejects_non_numeric_or_non_finite_ohlc(column: str) -> None:
    frame = frame_fixture()
    frame[column] = frame[column].astype(object)
    frame.loc[1, column] = "not-a-price"
    with pytest.raises(TypeError, match="numeric dtype"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")

    frame = frame_fixture()
    frame.loc[1, column] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_boolean_ohlc() -> None:
    frame = frame_fixture()
    frame["open"] = [True, False, True, False]
    with pytest.raises(TypeError, match="numeric dtype"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


@pytest.mark.parametrize(
    "updates",
    [
        {"high": [11.0, 11.0, 11.5, 11.2]},
        {"low": [9.0, 12.0, 10.5, 10.2]},
        {"open": [12.0, 10.5, 11.0, 10.8]},
        {"close": [10.5, 12.5, 10.8, 10.9]},
    ],
)
def test_adapter_rejects_invalid_ohlc_relationships(updates: dict[str, list[float]]) -> None:
    frame = frame_fixture()
    for column, values in updates.items():
        frame[column] = values
    with pytest.raises(ValueError, match="high|low|lie within"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_incomplete_bars() -> None:
    frame = frame_fixture()
    frame["is_complete"] = [True, True, False, True]
    with pytest.raises(ValueError, match="explicitly complete"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_negative_optional_metadata() -> None:
    frame = frame_fixture()
    frame.loc[2, "spread"] = -1
    with pytest.raises(ValueError, match="finite and non-negative"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_adapter_rejects_non_numeric_optional_metadata() -> None:
    frame = frame_fixture()
    frame["spread"] = ["15", "16", "17", "18"]
    with pytest.raises(TypeError, match="numeric dtype"):
        market_structure_input_from_frame(frame, symbol="XAUUSD")


def test_immutable_input_contract_rejects_unequal_lengths() -> None:
    with pytest.raises(ValueError, match="same non-zero length"):
        MarketStructureInput(
            symbol="XAUUSD",
            timeframe="M1",
            timestamps=(datetime(2024, 1, 1, tzinfo=timezone.utc),),
            open=(1.0,), high=(2.0,), low=(0.0,), close=(1.0,),
            spread_points=(), tick_volume=(1.0,), real_volume=(1.0,),
        )


def test_adapter_output_connects_to_detector_using_only_synthetic_fixture() -> None:
    adapted = market_structure_input_from_frame(frame_fixture(), symbol="XAUUSD")
    result = detect_market_structure(
        adapted.high,
        adapted.low,
        adapted.close,
        timestamps=adapted.timestamps,
    )
    assert result.rows == adapted.row_count
    assert result.gap_indices == ()
