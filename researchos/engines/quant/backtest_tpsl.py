import numpy as np


def vectorized_backtest_with_tpsl(
    prices: list[float],
    signals: list[tuple[str, float]],
    initial_capital: float = 100000.0,
    commission: float = 0.001,
    slippage: float = 0.0005,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.04,
    trailing_stop: bool = True,
) -> dict[str, object]:
    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    trades: list[tuple[str, float, float, float]] = []
    equity_curve: list[float] = [capital]

    sl_price: float | None = None
    tp_price: float | None = None
    trailing_high: float | None = None

    for action, price in signals:
        if action == "BUY" and position == 0:
            cost = price * (1 + commission + slippage)
            size = capital / cost
            if size > 0:
                capital -= size * cost
                position = size
                entry_price = price
                sl_price = price * (1 - stop_loss_pct)
                tp_price = price * (1 + take_profit_pct)
                trailing_high = price
                trades.append(("BUY", price, size, 0.0))

        elif action == "SELL" and position > 0:
            revenue = position * price * (1 - commission - slippage)
            pnl = revenue - position * entry_price
            capital += revenue
            trades.append(("SELL", price, position, pnl))
            position = 0.0
            entry_price = 0.0
            sl_price = tp_price = trailing_high = None

        if position > 0:
            if trailing_stop and price > trailing_high:
                trailing_high = price
                sl_price = trailing_high * (1 - stop_loss_pct)

            if sl_price is not None and price <= sl_price:
                revenue = position * price * (1 - commission - slippage)
                pnl = revenue - position * entry_price
                capital += revenue
                trades.append(("SL", price, position, pnl))
                position = 0.0
                entry_price = 0.0
                sl_price = tp_price = trailing_high = None

            elif tp_price is not None and price >= tp_price:
                revenue = position * price * (1 - commission - slippage)
                pnl = revenue - position * entry_price
                capital += revenue
                trades.append(("TP", price, position, pnl))
                position = 0.0
                entry_price = 0.0
                sl_price = tp_price = trailing_high = None

        equity = capital + position * price
        equity_curve.append(equity)

    if position > 0 and prices:
        closing_price = prices[-1]
        revenue = position * closing_price * (1 - commission - slippage)
        pnl = revenue - position * entry_price
        capital += revenue
        trades.append(("CLOSE", closing_price, position, pnl))
        equity_curve.append(capital)

    equity = np.array(equity_curve)
    returns = np.diff(equity) / equity[:-1]
    total_return = (capital - initial_capital) / initial_capital

    if len(returns) > 1:
        sharpe = np.mean(returns) / (np.std(returns) + 1e-8) * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_drawdown = -np.max(drawdown) if len(drawdown) > 0 else 0.0

    closed_trades = [t for t in trades if t[0] in ("SELL", "SL", "TP", "CLOSE")]
    wins = [t for t in closed_trades if t[3] > 0]
    win_rate = len(wins) / len(closed_trades) if closed_trades else 0.0

    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "num_trades": len(closed_trades),
        "trades": trades,
        "equity_curve": equity_curve,  # fixed: already a list
    }
