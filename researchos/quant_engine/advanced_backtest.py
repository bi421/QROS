"""
Advanced Backtest Engine with Risk Management (Stop Loss, Take Profit, Max Hold).
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class AdvancedBacktestResult:
    total_return: float
    annualised_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    num_trades: int
    avg_win: float
    avg_loss: float
    max_consecutive_losses: int
    total_commission: float
    total_slippage: float
    signals: list


class AdvancedBacktestEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        stop_loss: float = 0.15,  # 15% алдагдалд зогсоох
        take_profit: float = 0.30,  # 30% ашигт авах
        max_hold_days: int = 30,  # Хамгийн их 30 хоног барих
    ) -> None:
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_hold_days = max_hold_days

    def run(self, prices: list[float], strategy: Any) -> AdvancedBacktestResult:
        signals = strategy.generate_signals(prices)
        if not signals:
            return AdvancedBacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, [])

        capital = self.initial_capital
        position = 0.0
        buy_price = 0.0
        entry_day = 0
        peak_capital = capital
        max_drawdown = 0.0
        total_commission = 0.0
        total_slippage = 0.0

        wins, losses = [], []
        max_consec_losses = 0
        current_consec = 0
        num_trades = 0

        # Дохиог өдрөөр нь index-дэх dictionary болгох
        signal_map = {sig.day_index: sig for sig in signals}

        for day in range(35, len(prices)):
            current_price = prices[day]

            # 1. Хэрэв байршилтай бол гарах нөхцөл шалгах
            if position > 0:
                force_sell = False
                sell_reason = ""

                # Stop Loss
                if current_price <= buy_price * (1 - self.stop_loss):
                    force_sell = True
                    sell_reason = "Stop Loss"
                # Take Profit
                elif current_price >= buy_price * (1 + self.take_profit):
                    force_sell = True
                    sell_reason = "Take Profit"
                # Max Hold Days
                elif (day - entry_day) >= self.max_hold_days:
                    force_sell = True
                    sell_reason = "Max Hold Days"
                # Стратегийн SELL дохио
                elif day in signal_map and signal_map[day].action == "SELL":
                    force_sell = True
                    sell_reason = "Strategy SELL Signal"  # noqa: F841

                if force_sell:
                    # Гүйлгээ хаах
                    revenue = position * current_price * (1 - self.commission - self.slippage)
                    sell_comm = current_price * self.commission * position
                    sell_slip = current_price * self.slippage * position
                    total_commission += sell_comm
                    total_slippage += sell_slip

                    cost_basis = position * buy_price * (1 + self.commission + self.slippage)
                    trade_profit_pct = (revenue - cost_basis) / cost_basis

                    if trade_profit_pct > 0:
                        wins.append(trade_profit_pct)
                        current_consec = 0
                    else:
                        losses.append(abs(trade_profit_pct))
                        current_consec += 1
                        max_consec_losses = max(max_consec_losses, current_consec)

                    capital = revenue
                    position = 0.0
                    num_trades += 1

            # 2. Хэрэв байршилгүй бол стратегийн BUY дохио шалгах
            elif position == 0 and day in signal_map and signal_map[day].action == "BUY":
                cost_per_share = current_price * (1 + self.commission + self.slippage)
                if capital >= cost_per_share:
                    position = capital / cost_per_share
                    buy_price = current_price
                    entry_day = day
                    capital = 0.0
                    total_commission += current_price * self.commission * position
                    total_slippage += current_price * self.slippage * position

            # 3. Max Drawdown тооцох
            current_value = capital if position == 0 else position * current_price
            if current_value > peak_capital:
                peak_capital = current_value
            drawdown = (peak_capital - current_value) / peak_capital if peak_capital > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Эцсийн тооцоо
        final_value = capital if position == 0 else position * prices[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital

        years = len(prices) / 252
        annualised_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else 0.0

        daily_returns = [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
        if daily_returns:
            avg_ret = sum(daily_returns) / len(daily_returns)
            std_ret = (sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe_ratio = (avg_ret / std_ret) * (252**0.5) if std_ret > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        win_rate = len(wins) / (len(wins) + len(losses)) if (len(wins) + len(losses)) > 0 else 0.0
        profit_factor = sum(wins) / sum(losses) if sum(losses) > 0 else (float("inf") if wins else 0.0)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        return AdvancedBacktestResult(
            total_return=total_return,
            annualised_return=annualised_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            num_trades=num_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_consecutive_losses=max_consec_losses,
            total_commission=total_commission,
            total_slippage=total_slippage,
            signals=signals,
        )
