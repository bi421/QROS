"""
Backtest engine for strategies.
"""

from dataclasses import dataclass
from typing import Any, Protocol, Sequence\n\n\nclass _BacktestSignal(Protocol):\n    price: float\n    action: str\n\n\nclass _BacktestStrategy(Protocol):\n    def generate_signals(self, prices: Sequence[float]) -> list[_BacktestSignal]: ...

import numpy as np


@dataclass
class BacktestResult:
    total_return: float  # Нийт өгөөж (жишээ нь 0.33 → 33%)
    sharpe_ratio: float  # Sharpe харьцаа
    max_drawdown: float  # Хамгийн их уналт (жишээ нь -0.25 → -25%)
    win_rate: float  # Ялалтын хувь (0-1)
    num_trades: int  # Нийт хаагдсан арилжааны тоо
    signals: list[_BacktestSignal]  # Дохионууд


class BacktestEngine:
    def __init__(self, initial_capital: float = 100000.0, commission: float = 0.001, slippage: float = 0.0005):
        """
        :param initial_capital: Эхний хөрөнгө
        :param commission: Нэг арилжааны шимтгэл (хувь, 0.001 = 0.1%)
        :param slippage: Нэг арилжааны гулсалт (хувь, 0.0005 = 0.05%)
        """
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if commission < 0 or slippage < 0:
            raise ValueError("commission and slippage must be non-negative")
        if commission + slippage >= 1:
            raise ValueError("commission + slippage must be less than 1")
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

    def run(self, prices: list[float], strategy: _BacktestStrategy) -> BacktestResult:
        """
        Бэктест ажиллуулах.
        :param prices: Үнийн жагсаалт (жишээ нь өдрийн хаалтын үнэ)
        :param strategy: Стратегийн обьект, `.generate_signals(prices)` методтой
        """
        if not prices:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0, [])
        if any(not np.isfinite(price) or price <= 0 for price in prices):
            raise ValueError("prices must contain only finite positive values")

        signals = strategy.generate_signals(prices)
        if not signals:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0, signals)

        capital = self.initial_capital
        position = 0.0
        entry_price = 0.0
        trades: list[tuple[str, float, Any, float, float, float]] = []  # (action, price, timestamp, size, net_value, pnl)
        equity_curve = [capital]

        for signal in signals:
            price = float(signal.price)
            if not np.isfinite(price) or price <= 0:
                raise ValueError("signal prices must be finite and positive")
            timestamp = getattr(signal, "timestamp", None)

            if signal.action == "BUY" and position == 0:
                cost_per_unit = price * (1 + self.commission + self.slippage)
                size = capital / cost_per_unit
                if size > 0:
                    cost_total = size * cost_per_unit
                    capital -= cost_total
                    position = size
                    entry_price = price
                    trades.append(("BUY", price, timestamp, size, cost_total, 0.0))

            elif signal.action == "SELL" and position > 0:
                revenue_per_unit = price * (1 - self.commission - self.slippage)
                revenue_total = position * revenue_per_unit
                entry_cost_total = position * entry_price * (1 + self.commission + self.slippage)
                pnl = revenue_total - entry_cost_total
                capital += revenue_total
                trades.append(("SELL", price, timestamp, position, revenue_total, pnl))
                position = 0.0
                entry_price = 0.0
            elif signal.action not in {"BUY", "SELL"}:
                raise ValueError(f"unsupported signal action: {signal.action!r}")

            current_equity = capital + position * price
            equity_curve.append(current_equity)

        if position > 0:
            closing_price = float(prices[-1])
            revenue_per_unit = closing_price * (1 - self.commission - self.slippage)
            revenue_total = position * revenue_per_unit
            entry_cost_total = position * entry_price * (1 + self.commission + self.slippage)
            pnl = revenue_total - entry_cost_total
            capital += revenue_total
            trades.append(("CLOSE", closing_price, None, position, revenue_total, pnl))
            position = 0.0
            entry_price = 0.0
            equity_curve.append(capital)

        final_value = capital
        total_return = (final_value - self.initial_capital) / self.initial_capital

        equity = np.asarray(equity_curve, dtype=float)
        returns = np.diff(equity) / equity[:-1]
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            sharpe = 0.0

        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_drawdown = -np.max(drawdown) if len(drawdown) > 0 else 0.0

        closed_trades = [t for t in trades if t[0] in ("SELL", "CLOSE")]
        winning_trades = [t for t in closed_trades if t[5] > 0]
        win_rate = len(winning_trades) / len(closed_trades) if closed_trades else 0.0

        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            num_trades=len(closed_trades),
            signals=signals,
        )
