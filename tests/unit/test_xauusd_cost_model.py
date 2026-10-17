from __future__ import annotations

import pytest

from researchos.orchestration.xauusd_cost_model import (
    calculate_trade_costs,
    cost_config_completeness,
    mt5_spread_points_to_price,
)


def _config():
    return {
        "symbol_point": {"value": 0.01, "source": "measured"},
        "contract_size": {"value": 100.0, "source": "measured"},
        "spread": {"raw_unit": "MT5_points"},
        "commission": {"round_turn_usd_per_lot": {"value": 7.0, "source": "assumed"}},
        "slippage": {"order_types": {
            "market_entry": {"price_units_per_fill": 0.10, "source": "assumed"},
            "tp_limit": {"price_units_per_fill": 0.01, "source": "assumed"},
            "sl_stop": {"price_units_per_fill": 0.15, "source": "assumed"},
            "market_exit": {"price_units_per_fill": 0.10, "source": "assumed"},
        }},
    }


def test_mt5_spread_points_convert_using_symbol_point():
    assert mt5_spread_points_to_price(9, 0.01) == pytest.approx(0.09)
    assert mt5_spread_points_to_price(19, 0.01) == pytest.approx(0.19)


@pytest.mark.parametrize("spread,point", [(-1, 0.01), (1, 0), (float("nan"), 0.01), (True, 0.01)])
def test_spread_conversion_fails_closed_for_invalid_units(spread, point):
    with pytest.raises(ValueError):
        mt5_spread_points_to_price(spread, point)


def test_cost_config_explicit_nonzero_assumptions_are_declared_but_not_verified():
    result = cost_config_completeness(_config())
    assert result["cost_basis_declared"] is True
    assert result["costs_verified"] is False
    assert set(result["assumption_fields"]) == {
        "commission", "slippage.market_entry", "slippage.tp_limit",
        "slippage.sl_stop", "slippage.market_exit",
    }


def test_assumed_zero_cost_is_invalid():
    config = _config()
    config["commission"]["round_turn_usd_per_lot"]["value"] = 0.0
    result = cost_config_completeness(config)
    assert result["cost_basis_declared"] is False
    assert "COMMISSION_ASSUMED_ZERO_FORBIDDEN" in result["failures"]


def test_long_uses_entry_ask_exit_bid_and_counts_spread_once():
    result = calculate_trade_costs(
        entry_price=2500, exit_price=2500.21, direction=1,
        entry_spread_points=9, exit_spread_points=19,
        entry_atr=1.0, exit_atr=1.2, config=_config(),
    )
    gross = 2500.21 / 2500 - 1
    executable = 2500.21 / 2500.09 - 1
    assert result["gross_return"] == pytest.approx(gross)
    assert result["entry_executable_price"] == pytest.approx(2500.09)
    assert result["exit_executable_price"] == pytest.approx(2500.21)
    assert result["spread_cost_return"] == pytest.approx(gross - executable)
    assert result["spread_cost_return"] == pytest.approx((gross - executable))
    assert result["spread_accounting"] == "LONG_ENTRY_ASK_EXIT_BID"
    assert result["costs_verified"] is False
    assert result["net_return"] < result["gross_return"]
    assert result["execution_authorized"] is False


def test_short_uses_entry_bid_exit_ask_and_counts_spread_once():
    result = calculate_trade_costs(
        entry_price=2500, exit_price=2499.79, direction=-1,
        entry_spread_points=9, exit_spread_points=19,
        entry_atr=1.0, exit_atr=1.2, config=_config(),
    )
    gross = 1 - 2499.79 / 2500
    executable = 1 - (2499.79 + 0.19) / 2500
    assert result["entry_executable_price"] == pytest.approx(2500)
    assert result["exit_executable_price"] == pytest.approx(2499.98)
    assert result["spread_cost_return"] == pytest.approx(gross - executable)
    assert result["spread_accounting"] == "SHORT_ENTRY_BID_EXIT_ASK"
    assert result["net_return"] < result["gross_return"]


@pytest.mark.parametrize(
    ("exit_reason", "expected_exit_type", "expected_slippage"),
    [
        ("TAKE_PROFIT", "tp_limit", 0.11),
        ("STOP_LOSS", "sl_stop", 0.25),
        ("TIMEOUT", "market_exit", 0.20),
    ],
)
def test_slippage_is_selected_by_order_type_not_atr(exit_reason, expected_exit_type, expected_slippage):
    result = calculate_trade_costs(
        entry_price=2500, exit_price=2501, direction=1,
        entry_spread_points=9, exit_spread_points=9,
        entry_atr=100.0, exit_atr=500.0, config=_config(),
        exit_reason=exit_reason,
    )
    assert result["slippage_exit_order_type"] == expected_exit_type
    assert result["slippage_cost_price"] == pytest.approx(expected_slippage)
    assert result["slippage_cost_return"] == pytest.approx(expected_slippage / 2500.09)
    assert result["execution_authorized"] is False


def test_unknown_exit_reason_fails_closed():
    with pytest.raises(ValueError, match="INVALID_EXIT_REASON"):
        calculate_trade_costs(
            entry_price=2500, exit_price=2501, direction=1,
            entry_spread_points=9, exit_spread_points=9,
            entry_atr=1.0, exit_atr=1.0, config=_config(),
            exit_reason="UNKNOWN",
        )


def test_missing_cost_terms_do_not_emit_net_return():
    config = _config()
    config["slippage"]["order_types"]["market_entry"]["price_units_per_fill"] = None
    result = calculate_trade_costs(
        entry_price=2500, exit_price=2501, direction=1,
        entry_spread_points=9, exit_spread_points=9,
        entry_atr=1.0, exit_atr=1.0, config=config,
    )
    assert result["cost_basis_declared"] is False
    assert result["net_return"] is None
    assert result["execution_authorized"] is False
