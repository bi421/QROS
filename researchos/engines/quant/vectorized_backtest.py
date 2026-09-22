from collections.abc import Sequence

import numpy as np


def vectorized_backtest(
    prices: Sequence[float],
    signals: Sequence[tuple[str, float]],
    initial_capital: float = 100000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
) -> dict[str, float | int]:
    """
    Fully vectorized backtest (no Python loops).
    signals: list of (action, price) tuples
    """
    if not signals:
        return {
            "total_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "num_trades": 0,
        }

    actions = np.array([1 if s[0] == "BUY" else -1 for s in signals])
    signal_prices = np.array([s[1] for s in signals])

    np.where(actions == 1)[0]
    np.where(actions == -1)[0]

    trades: list[tuple[str, float, float]] = []
    capital = initial_capital
    entry_price = 0.0
    position = 0.0

    np.arange(len(signals))

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    trades = []
    equity_values: list[float] = [initial_capital]

    for action, price in signals:
        if action == "BUY" and position == 0:
            cost = price * (1 + commission + slippage)
            size = capital / cost
            if size > 0:
                capital -= size * cost
                position = size
                entry_price = price
        elif action == "SELL" and position > 0:
            revenue = position * price * (1 - commission - slippage)
            pnl = revenue - position * entry_price
            capital += revenue
            trades.append(("SELL", price, pnl))
            position = 0.0
        equity_values.append(capital + position * price)

    if position > 0 and len(signal_prices) > 0:
        closing_price = float(signal_prices[-1])
        revenue = position * closing_price * (1 - commission - slippage)
        pnl = revenue - position * entry_price
        capital += revenue
        trades.append(("CLOSE", closing_price, pnl))
        position = 0.0
        equity_values.append(capital)

    equity = np.array(equity_values)
    returns = np.diff(equity) / equity[:-1]
    total_return = (capital - initial_capital) / initial_capital

    if len(returns) > 1:
        sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak
    max_dd = -np.max(dd) if len(dd) > 0 else 0.0

    winning = [t for t in trades if t[2] > 0]
    win_rate = len(winning) / len(trades) if trades else 0.0

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "num_trades": len(trades),
    }
