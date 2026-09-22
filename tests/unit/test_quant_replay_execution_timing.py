from dataclasses import dataclass
from datetime import datetime, timedelta

from researchos.quant_engine.execution import ExecutionSimulationLayer
from researchos.quant_engine.models import OrderSide, Signal
from researchos.quant_engine.replay import ReplayBar, ReplayEngine
from researchos.quant_engine.strategy import StrategyEvaluationInterface


@dataclass(frozen=True)
class TimingStrategy(StrategyEvaluationInterface):
    emit_on: int
    identifier = "timing_test"
    version = "1.0.0"

    def evaluate(self, bar, history, bar_index: int) -> Signal | None:
        if bar_index == self.emit_on:
            return Signal(
                bar_index=bar_index,
                timestamp=bar.timestamp.isoformat(),
                side=OrderSide.BUY,
            )
        return None


def _bars() -> list[ReplayBar]:
    start = datetime(2026, 1, 1)
    return [
        ReplayBar(close=150.0, timestamp=start, open=100.0),
        ReplayBar(close=250.0, timestamp=start + timedelta(days=1), open=200.0),
        ReplayBar(close=350.0, timestamp=start + timedelta(days=2), open=300.0),
    ]


def test_signal_is_filled_at_next_bar_open() -> None:
    execution = ExecutionSimulationLayer(
        initial_capital=1_000.0,
        commission="fixed:0.0",
        slippage="fixed:0.0",
        symbol="XAUUSD",
        position_size=1.0,
    )
    result = ReplayEngine(TimingStrategy(emit_on=0), execution).run(_bars())

    assert len(execution.fills) == 2
    entry_fill = execution.trades[0].entry_fill
    exit_fill = execution.trades[0].exit_fill
    assert entry_fill.fill_price == 200.0
    assert entry_fill.bar_index == 1
    assert entry_fill.order.bar_index == 1
    assert entry_fill.order.side == OrderSide.BUY
    assert exit_fill.fill_price == 350.0
    assert exit_fill.bar_index == 2
    assert execution.trades[0].entry_bar_index == 1
    assert execution.trades[0].exit_bar_index == 2
    assert result["execution_stats"]["signal_fill_timing"] == "next_bar_open"


def test_final_bar_signal_is_not_filled() -> None:
    execution = ExecutionSimulationLayer(
        initial_capital=1_000.0,
        commission="fixed:0.0",
        slippage="fixed:0.0",
        symbol="XAUUSD",
        position_size=1.0,
    )
    result = ReplayEngine(TimingStrategy(emit_on=2), execution).run(_bars())

    assert execution.fills == []
    assert execution.trades == []
    assert result["execution_stats"]["num_orders"] == 0
    assert result["execution_stats"]["signal_fill_timing"] == "next_bar_open"
