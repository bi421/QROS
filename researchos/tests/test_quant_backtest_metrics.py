"""Regression tests for quant backtest trade accounting."""

from dataclasses import dataclass

import pytest

from researchos.quant_engine.backtest import BacktestEngine


@dataclass(frozen=True)
class _Signal:
    action: str
    price: float
    timestamp: object = None


class _FixedStrategy:
    def __init__(self, signals):
        self._signals = signals

    def generate_signals(self, prices):
        return list(self._signals)


def test_num_trades_counts_closed_trades_not_buy_entries():
    strategy = _FixedStrategy(
        [
            _Signal("BUY", 100.0),
            _Signal("SELL", 90.0),
            _Signal("BUY", 100.0),
            _Signal("SELL", 110.0),
        ]
    )

    result = BacktestEngine(
        initial_capital=10_000.0,
        commission=0.0,
        slippage=0.0,
    ).run([100.0, 90.0, 100.0, 110.0], strategy)

    assert result.num_trades == 2
    assert result.win_rate == pytest.approx(0.5)


def test_win_rate_uses_net_pnl_including_entry_and_exit_costs():
    strategy = _FixedStrategy(
        [
            _Signal("BUY", 100.0),
            _Signal("SELL", 100.1),
        ]
    )

    result = BacktestEngine(
        initial_capital=10_000.0,
        commission=0.001,
        slippage=0.001,
    ).run([100.0, 100.1], strategy)

    assert result.num_trades == 1
    assert result.win_rate == pytest.approx(0.0)


def test_open_position_is_counted_when_forced_closed_at_last_price():
    strategy = _FixedStrategy([_Signal("BUY", 100.0)])

    result = BacktestEngine(
        initial_capital=10_000.0,
        commission=0.0,
        slippage=0.0,
    ).run([100.0, 110.0], strategy)

    assert result.num_trades == 1
    assert result.win_rate == pytest.approx(1.0)


def test_forced_close_is_included_in_equity_drawdown():
    strategy = _FixedStrategy([_Signal("BUY", 100.0)])

    result = BacktestEngine(
        initial_capital=10_000.0,
        commission=0.0,
        slippage=0.0,
    ).run([100.0, 90.0], strategy)

    assert result.total_return == pytest.approx(-0.10)
    assert result.max_drawdown == pytest.approx(-0.10)


def test_invalid_cost_configuration_is_rejected():
    with pytest.raises(ValueError):
        BacktestEngine(initial_capital=0.0)

    with pytest.raises(ValueError):
        BacktestEngine(commission=-0.001)

    with pytest.raises(ValueError):
        BacktestEngine(commission=0.6, slippage=0.4)
