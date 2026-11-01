from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from researchos.quant_engine.technical.market_structure import (
    MarketStructureConfig,
    detect_market_structure as _detect_market_structure,
    market_structure_variants,
    run_market_structure_variants,
)
from researchos.quant_engine.technical.market_structure_definition import StructureDefinition


def base_ohlc() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high = np.array([10, 11, 15, 12, 11, 13, 16, 15, 14, 13, 12], dtype=float)
    low = np.array([8, 9, 12, 10, 9, 11, 14, 12, 10, 11, 8], dtype=float)
    close = np.array([9, 10, 13, 11, 10, 12, 15, 13, 11, 12, 9], dtype=float)
    return high, low, close


def utc_timestamps(length: int, *, gap_indices: set[int] | None = None) -> tuple[datetime, ...]:
    gaps = gap_indices or set()
    current = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = [current]
    for index in range(1, length):
        current += timedelta(minutes=2 if index in gaps else 1)
        result.append(current)
    return tuple(result)


def detect_market_structure(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    config: MarketStructureConfig | StructureDefinition | None = None,
    *,
    gap_indices: set[int] | None = None,
):
    return _detect_market_structure(
        high,
        low,
        close,
        config,
        timestamps=utc_timestamps(len(close), gap_indices=gap_indices),
    )


def test_variant_grid_has_56_unique_explicit_definitions() -> None:
    configs = market_structure_variants()
    assert len(configs) == 56
    assert len({item.variant_id for item in configs}) == 56
    assert {item.swing_window for item in configs} == {2, 3, 4, 5, 6, 8, 10}
    assert {item.break_basis for item in configs} == {"wick", "close"}
    assert {item.confirmation_bars for item in configs} == {1, 2}
    assert {item.break_buffer_atr for item in configs} == {0.0, 0.05}


def test_swing_is_not_known_until_right_confirmation_window_closes() -> None:
    high, low, close = base_ohlc()
    result = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="close", atr_period=2),
    )
    swing = next(item for item in result.swings if item.kind == "swing_high")
    assert swing.pivot_index == 2
    assert swing.confirmed_index == 3
    assert swing.confirmed_index > swing.pivot_index


def test_detects_bullish_bos_then_bearish_choch() -> None:
    high, low, close = base_ohlc()
    result = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2),
    )
    assert [(item.kind, item.direction, item.break_index) for item in result.breaks] == [
        ("BOS", "bullish", 6),
        ("CHOCH", "bearish", 10),
    ]
    assert result.final_trend == "bearish"


def test_close_basis_does_not_count_wick_only_break() -> None:
    high, low, close = base_ohlc()
    wick = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2),
    )
    close_only = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="close", atr_period=2),
    )
    assert any(item.break_index == 6 and item.direction == "bullish" for item in wick.breaks)
    assert not any(item.break_index == 6 and item.direction == "bullish" for item in close_only.breaks)


def test_two_bar_confirmation_waits_for_second_completed_bar() -> None:
    high, low, close = base_ohlc()
    high[5] = 15.2
    close[5] = 15.1
    high[6] = 15.4
    close[6] = 15.2
    result = detect_market_structure(
        high, low, close,
        MarketStructureConfig(
            swing_window=1,
            break_basis="close",
            confirmation_bars=2,
            atr_period=2,
        ),
    )
    bullish = [item for item in result.breaks if item.direction == "bullish"]
    assert bullish
    assert bullish[0].break_index == 6


def test_atr_buffer_can_reject_a_small_level_penetration() -> None:
    high, low, close = base_ohlc()
    high[6] = 16.0
    close[6] = 15.5
    unbuffered = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="close", atr_period=2),
    )
    buffered = detect_market_structure(
        high, low, close,
        MarketStructureConfig(
            swing_window=1,
            break_basis="close",
            break_buffer_atr=2.0,
            atr_period=2,
        ),
    )
    assert any(item.break_index == 6 and item.direction == "bullish" for item in unbuffered.breaks)
    assert not any(item.break_index == 6 and item.direction == "bullish" for item in buffered.breaks)


def test_same_bar_double_wick_break_is_marked_ambiguous() -> None:
    high = np.array([10, 11, 15, 12, 11, 13, 16], dtype=float)
    low = np.array([8, 9, 10, 10, 9, 11, 8], dtype=float)
    close = np.array([9, 10, 13, 11, 10, 12, 12], dtype=float)
    result = detect_market_structure(
        high, low, close,
        MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2),
    )
    assert 6 in result.ambiguous_break_indices
    assert not any(item.break_index == 6 for item in result.breaks)


def test_future_perturbation_does_not_rewrite_earlier_events() -> None:
    high, low, close = base_ohlc()
    config = MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2)
    baseline = detect_market_structure(high, low, close, config)
    cutoff = 7

    changed_high = high.copy()
    changed_low = low.copy()
    changed_close = close.copy()
    changed_high[cutoff + 1 :] += 50
    changed_low[cutoff + 1 :] += 50
    changed_close[cutoff + 1 :] += 50
    perturbed = detect_market_structure(changed_high, changed_low, changed_close, config)

    def earlier(result):
        return [
            (item.kind, item.direction, item.level, item.break_index)
            for item in result.breaks
            if item.break_index <= cutoff
        ]

    assert earlier(baseline) == earlier(perturbed)


def test_variant_runner_returns_one_result_per_unique_config() -> None:
    high, low, close = base_ohlc()
    configs = market_structure_variants()[:3]
    results = run_market_structure_variants(
        high, low, close, configs, timestamps=utc_timestamps(len(close))
    )
    assert len(results) == 3
    assert set(results) == {item.variant_id for item in configs}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("swing_window", 0),
        ("swing_window", 1.5),
        ("swing_window", True),
        ("confirmation_bars", 0),
        ("confirmation_bars", 1.5),
        ("atr_period", 0),
        ("break_basis", "body"),
        ("break_buffer_atr", -0.1),
        ("break_buffer_atr", True),
        ("break_buffer_atr", float("nan")),
    ],
)
def test_config_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        MarketStructureConfig(**{field: value})


def test_ohlc_validation_rejects_invalid_geometry() -> None:
    with pytest.raises(ValueError, match="high must be >= low"):
        detect_market_structure([1, 2], [2, 1], [1.5, 1.5])



def test_detector_requires_timezone_aware_utc_timestamps() -> None:
    high, low, close = base_ohlc()
    config = MarketStructureConfig(swing_window=1, atr_period=2)
    with pytest.raises(ValueError, match="timestamps are required"):
        _detect_market_structure(high, low, close, config)

    naive = tuple(datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(len(close)))
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _detect_market_structure(high, low, close, config, timestamps=naive)

    non_utc_zone = tuple(
        datetime(2024, 1, 1, tzinfo=ZoneInfo("Europe/London")) + timedelta(minutes=i)
        for i in range(len(close))
    )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _detect_market_structure(high, low, close, config, timestamps=non_utc_zone)


def test_detector_rejects_duplicate_or_out_of_order_timestamps() -> None:
    high, low, close = base_ohlc()
    config = MarketStructureConfig(swing_window=1, atr_period=2)
    valid = list(utc_timestamps(len(close)))
    duplicate = valid.copy()
    duplicate[3] = duplicate[2]
    with pytest.raises(ValueError, match="strictly increasing"):
        _detect_market_structure(high, low, close, config, timestamps=duplicate)
    out_of_order = valid.copy()
    out_of_order[3], out_of_order[4] = out_of_order[4], out_of_order[3]
    with pytest.raises(ValueError, match="strictly increasing"):
        _detect_market_structure(high, low, close, config, timestamps=out_of_order)


def test_detector_rejects_non_minute_aligned_timestamps() -> None:
    high, low, close = base_ohlc()
    timestamps = list(utc_timestamps(len(close)))
    timestamps[4] += timedelta(seconds=30)
    with pytest.raises(ValueError, match="whole minutes"):
        _detect_market_structure(
            high, low, close, timestamps=timestamps
        )


def test_swing_confirmation_window_cannot_cross_a_gap() -> None:
    high, low, close = base_ohlc()
    result = detect_market_structure(
        high,
        low,
        close,
        MarketStructureConfig(swing_window=1, break_basis="close", atr_period=2),
        gap_indices={3},
    )
    assert 3 in result.gap_indices
    assert not any(item.kind == "swing_high" and item.pivot_index == 2 for item in result.swings)


def test_single_bar_break_can_confirm_on_first_bar_after_gap() -> None:
    high, low, close = base_ohlc()
    result = detect_market_structure(
        high,
        low,
        close,
        MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2),
        gap_indices={6},
    )
    assert 6 in result.gap_indices
    assert any(item.direction == "bullish" and item.break_index == 6 for item in result.breaks)


def test_two_bar_break_confirmation_restarts_after_gap() -> None:
    high, low, close = base_ohlc()
    high[5], close[5] = 15.2, 15.1
    high[6], close[6] = 16.0, 15.2
    high[7], close[7] = 16.5, 15.3
    result = detect_market_structure(
        high,
        low,
        close,
        MarketStructureConfig(
            swing_window=1,
            break_basis="close",
            confirmation_bars=2,
            atr_period=2,
        ),
        gap_indices={6},
    )
    assert not any(item.direction == "bullish" and item.break_index == 6 for item in result.breaks)
    assert any(item.direction == "bullish" and item.break_index == 7 for item in result.breaks)


def test_ambiguous_double_wick_does_not_consume_either_level() -> None:
    high = np.array([10, 11, 15, 12, 11, 13, 16, 17], dtype=float)
    low = np.array([8, 9, 10, 10, 9, 11, 8, 11], dtype=float)
    close = np.array([9, 10, 13, 11, 10, 12, 12, 16], dtype=float)
    result = detect_market_structure(
        high,
        low,
        close,
        MarketStructureConfig(swing_window=1, break_basis="wick", atr_period=2),
    )
    assert 6 in result.ambiguous_break_indices
    assert not any(item.break_index == 6 for item in result.breaks)
    assert any(item.direction == "bullish" and item.break_index == 7 for item in result.breaks)


def test_structure_definition_id_propagates_to_result_and_events() -> None:
    high, low, close = base_ohlc()
    definition = StructureDefinition(
        swing_window=1,
        break_basis="wick",
        confirmation_bars=1,
        break_buffer_atr=0.0,
        atr_period=2,
    )
    result = detect_market_structure(high, low, close, definition)
    assert result.variant_id == definition.variant_key
    assert result.definition_id == definition.definition_id
    assert all(item.definition_id == definition.definition_id for item in result.breaks)


def test_variant_runner_accepts_content_addressed_definitions() -> None:
    high, low, close = base_ohlc()
    definition = StructureDefinition(
        swing_window=1,
        break_basis="close",
        confirmation_bars=1,
        break_buffer_atr=0.0,
        atr_period=2,
    )
    results = run_market_structure_variants(
        high,
        low,
        close,
        [definition],
        timestamps=utc_timestamps(len(close)),
    )
    assert tuple(results) == (definition.variant_key,)
    assert results[definition.variant_key].definition_id == definition.definition_id


def test_public_technical_package_exports_definition_and_detector() -> None:
    from researchos.quant_engine.technical import (
        StructureDefinition as PublicDefinition,
        definitions_from_grid_payload as public_grid_loader,
        detect_market_structure as public_detector,
    )

    assert PublicDefinition is StructureDefinition
    assert public_detector is _detect_market_structure
    assert callable(public_grid_loader)


def test_config_variant_keys_match_the_preregistered_grid() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "docs/research/market_structure/grid.json").read_text(encoding="utf-8"))
    expected = [item["variant_key"] for item in payload["variants"]]
    assert [item.variant_id for item in market_structure_variants()] == expected
