from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from researchos.quant_engine.technical.market_structure_definition import (
    StructureDefinition,
    definitions_from_grid_payload,
)


def definition(**overrides: object) -> StructureDefinition:
    values: dict[str, object] = {
        "swing_window": 2,
        "break_basis": "wick",
        "confirmation_bars": 1,
        "break_buffer_atr": 0.0,
        "atr_period": 14,
    }
    values.update(overrides)
    return StructureDefinition(**values)  # type: ignore[arg-type]


def test_definition_is_frozen_and_has_stable_content_id() -> None:
    first = definition()
    second = definition()
    assert first == second
    assert first.definition_id == second.definition_id
    assert len(first.definition_id) == 64
    with pytest.raises(FrozenInstanceError):
        first.swing_window = 4  # type: ignore[misc]


def test_definition_id_changes_when_any_strategy_parameter_changes() -> None:
    base = definition()
    changed = definition(break_buffer_atr=0.05)
    assert base.variant_key != changed.variant_key
    assert base.definition_id != changed.definition_id


def test_variant_key_matches_preregistered_grid_naming() -> None:
    item = definition(swing_window=10, break_basis="close", confirmation_bars=2, break_buffer_atr=0.05)
    assert item.variant_key == "sw10_close_c2_atr0500"


def test_grid_materializes_56_unique_immutable_definitions() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "docs/research/market_structure/grid.json").read_text(encoding="utf-8"))
    definitions = definitions_from_grid_payload(payload)
    assert len(definitions) == 56
    assert len({item.variant_key for item in definitions}) == 56
    assert len({item.definition_id for item in definitions}) == 56
    assert [item.variant_key for item in definitions] == [item["variant_key"] for item in payload["variants"]]
    assert all(item.choch_rule == "opposite_confirmed_swing_break" for item in definitions)
    assert all(item.trend_filter == "off" for item in definitions)


def test_grid_rejects_variant_key_drift() -> None:
    payload = {
        "schema_version": "1.0.0",
        "variant_count": 1,
        "variants": [
            {
                "variant_key": "not-the-derived-key",
                "swing_window": 2,
                "break_basis": "wick",
                "confirmation_bars": 1,
                "break_buffer_atr": 0,
                "atr_period": 14,
                "choch_rule": "opposite_confirmed_swing_break",
                "trend_filter": "off",
            }
        ],
    }
    with pytest.raises(ValueError, match="variant_key mismatch"):
        definitions_from_grid_payload(payload)


def test_grid_rejects_duplicate_or_inconsistent_variant_count() -> None:
    payload = {
        "schema_version": "1.0.0",
        "variant_count": 2,
        "variants": [
            {
                "variant_key": "sw02_wick_c1_atr0000",
                "swing_window": 2,
                "break_basis": "wick",
                "confirmation_bars": 1,
                "break_buffer_atr": 0,
                "atr_period": 14,
                "choch_rule": "opposite_confirmed_swing_break",
                "trend_filter": "off",
            }
        ],
    }
    with pytest.raises(ValueError, match="variant_count mismatch"):
        definitions_from_grid_payload(payload)


def test_definition_rejects_unsupported_rules_and_invalid_parameters() -> None:
    with pytest.raises(ValueError, match="swing_window"):
        definition(swing_window=True)
    with pytest.raises(ValueError, match="break_buffer_atr"):
        definition(break_buffer_atr=float("nan"))
    with pytest.raises(ValueError, match="choch_rule"):
        definition(choch_rule="first_break_is_choch")
    with pytest.raises(ValueError, match="trend_filter"):
        definition(trend_filter="ema200")

def test_grid_rejects_axis_metadata_drift() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "docs/research/market_structure/grid.json").read_text(encoding="utf-8"))
    payload["axes"]["swing_window"] = [2, 3]
    with pytest.raises(ValueError, match="axis swing_window"):
        definitions_from_grid_payload(payload)


def test_grid_rejects_missing_cartesian_variant() -> None:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "docs/research/market_structure/grid.json").read_text(encoding="utf-8"))
    payload["variants"].pop()
    payload["variant_count"] -= 1
    with pytest.raises(ValueError, match="complete Cartesian product"):
        definitions_from_grid_payload(payload)
