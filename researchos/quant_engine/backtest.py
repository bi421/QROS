"""
Backtest engine with proper trade recording.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class BacktestResult:
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    num_trades: int
    signals: list[Any]


class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(self, prices: list[float], strategy: Any) -> BacktestResult:
        signals = strategy.generate_signals(prices)
        if not signals:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0, signals)

        capital = self.initial_capital
        position = 0.0
        entry_price = 0.0
        trades: list[tuple[str, float, float, float]] = []  # (action, price, size, pnl)
        equity_curve: list[float] = [capital]

        for signal in signals:
            price = signal.price
            if signal.action == "BUY" and position == 0:
                cost_per_unit = price * (1 + self.commission + self.slippage)
                size = capital / cost_per_unit
                if size > 0:
                    capital -= size * cost_per_unit
                    position = size
                    entry_price = price
                    trades.append(("BUY", price, size, 0.0))

            elif signal.action == "SELL" and position > 0:
                revenue_per_unit = price * (1 - self.commission - self.slippage)
                revenue = position * revenue_per_unit
                pnl = revenue - position * entry_price
                capital += revenue
                trades.append(("SELL", price, position, pnl))
                position = 0.0
                entry_price = 0.0

            current_equity = capital + position * price
            equity_curve.append(current_equity)

        if position > 0 and prices:
            closing_price = prices[-1]
            revenue_per_unit = closing_price * (1 - self.commission - self.slippage)
            revenue = position * revenue_per_unit
            pnl = revenue - position * entry_price
            capital += revenue
            trades.append(("CLOSE", closing_price, position, pnl))
            position = 0.0

        final_value = capital
        total_return = (final_value - self.initial_capital) / self.initial_capital

        equity = np.array(equity_curve)
        returns = np.diff(equity) / equity[:-1]
        if len(returns) > 1:
            sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
        else:
            sharpe = 0.0

        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_drawdown = -np.max(drawdown) if len(drawdown) > 0 else 0.0

        closed_trades = [t for t in trades if t[0] in ("SELL", "CLOSE")]
        winning_trades = [t for t in closed_trades if t[3] > 0]
        win_rate = len(winning_trades) / len(closed_trades) if closed_trades else 0.0

        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            num_trades=len(closed_trades),
            signals=signals,
        )
