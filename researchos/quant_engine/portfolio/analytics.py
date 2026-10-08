"""
Portfolio & Risk Analytics Engine — deterministic portfolio computation.

Research-only analytics:
    - Portfolio return / variance
    - Correlation & covariance matrices
    - Beta / Alpha / Treynor / Information Ratio
    - Sharpe / Sortino / Calmar / Omega
    - VaR / CVaR / Expected Shortfall
    - Kelly criterion, risk contribution, capital allocation
    - Drawdown attribution, exposure analytics

All functions are pure and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from researchos.quant_engine.portfolio.contracts import (
    AllocationResult,
    EfficientFrontierPoint,
    EfficientFrontierResult,
    Portfolio,
    PortfolioMetrics,
    RiskContribution,
)

# ──────────────────────────────────────────────
# Basic moments
# ──────────────────────────────────────────────


def mean(values: Sequence[float]) -> float:
    if len(values) == 0:
        raise ValueError("cannot compute mean of empty sequence")
    return sum(values) / len(values)


def variance(values: Sequence[float], ddof: int = 1) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = mean(values)
    return sum((v - m) ** 2 for v in values) / (n - ddof)


def std_dev(values: Sequence[float]) -> float:
    return math.sqrt(variance(values))


def covariance(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx = mean(x)
    my = mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) - 1)


def correlation(x: Sequence[float], y: Sequence[float]) -> float:
    sx = std_dev(x)
    sy = std_dev(y)
    if sx == 0 or sy == 0:
        return 0.0
    return covariance(x, y) / (sx * sy)


def correlation_matrix(returns: list[list[float]]) -> list[list[float]]:
    n = len(returns)
    if n == 0:
        return []
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            mat[i][j] = correlation(returns[i], returns[j])
    return mat


def covariance_matrix(returns: list[list[float]]) -> list[list[float]]:
    n = len(returns)
    if n == 0:
        return []
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            mat[i][j] = covariance(returns[i], returns[j])
    return mat


def portfolio_returns(portfolio: Portfolio) -> list[float]:
    """Period-wise portfolio returns from weighted asset returns."""
    portfolio.validate()
    if not portfolio.asset_returns:
        return []
    n_periods = len(portfolio.asset_returns[0])
    out = []
    for t in range(n_periods):
        r = 0.0
        for w, series in zip(portfolio.weights, portfolio.asset_returns):
            r += w * series[t]
        out.append(r)
    return out


def portfolio_variance(portfolio: Portfolio) -> float:
    """wᵀ Σ w using the asset return covariance matrix."""
    portfolio.validate()
    if not portfolio.asset_returns:
        return 0.0
    cov = covariance_matrix(portfolio.asset_returns)
    n = len(portfolio.weights)
    total = 0.0
    for i in range(n):
        for j in range(n):
            total += portfolio.weights[i] * portfolio.weights[j] * cov[i][j]
    return total


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Maximum drawdown (negative decimal) from an equity curve."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (value - peak) / peak if peak != 0 else 0.0
        if dd < max_dd:
            max_dd = dd
    return max_dd


def _annualise(period_return: float, periods_per_year: int = 252) -> float:
    return (1.0 + period_return) ** periods_per_year - 1.0


def _annualise_std(period_std: float, periods_per_year: int = 252) -> float:
    return period_std * math.sqrt(periods_per_year)


def equity_curve_from_returns(returns: Sequence[float], initial: float = 100.0) -> list[float]:
    eq = [initial]
    for r in returns:
        eq.append(eq[-1] * (1.0 + r))
    return eq


# ──────────────────────────────────────────────
# Downside measures
# ──────────────────────────────────────────────


def downside_deviation(returns: Sequence[float], target: float = 0.0) -> float:
    n = len(returns)
    if n == 0:
        return 0.0
    sq = sum((min(r - target, 0.0)) ** 2 for r in returns)
    return math.sqrt(sq / n)


def sortino_ratio(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    n = len(returns)
    if n == 0:
        return 0.0
    ann_ret = _annualise(mean(returns), periods_per_year)
    ann_rf = risk_free_rate
    ds = downside_deviation(returns) * math.sqrt(periods_per_year)
    if ds == 0:
        return 0.0
    return (ann_ret - ann_rf) / ds


def sharpe_ratio(
    returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    n = len(returns)
    if n == 0:
        return 0.0
    ann_ret = _annualise(mean(returns), periods_per_year)
    ann_std = _annualise_std(std_dev(returns), periods_per_year)
    if ann_std == 0:
        return 0.0
    return (ann_ret - risk_free_rate) / ann_std


def calmar_ratio(
    returns: Sequence[float],
    periods_per_year: int = 252,
) -> float:
    if len(returns) == 0:
        return 0.0
    eq = equity_curve_from_returns(returns)
    mdd = max_drawdown(eq)
    ann_ret = _annualise(mean(returns), periods_per_year)
    if mdd == 0:
        return 0.0
    return ann_ret / abs(mdd)


def omega_ratio(
    returns: Sequence[float],
    threshold: float = 0.0,
) -> float:
    """Omega ratio: gains above threshold / losses below threshold."""
    gains = sum(max(r - threshold, 0.0) for r in returns)
    losses = sum(max(threshold - r, 0.0) for r in returns)
    if losses == 0:
        return float("inf") if gains > 0 else 1.0
    return gains / losses


# ──────────────────────────────────────────────
# VaR / CVaR / Expected Shortfall
# ──────────────────────────────────────────────


def value_at_risk(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Value-at-Risk as a positive loss amount (historical method)."""
    if len(returns) == 0:
        return 0.0
    sorted_returns = sorted(returns)
    alpha = 1.0 - confidence
    idx = max(0, min(len(sorted_returns) - 1, int(alpha * len(sorted_returns))))
    return -sorted_returns[idx]


def conditional_var(returns: Sequence[float], confidence: float = 0.95) -> float:
    """Conditional VaR / Expected Shortfall (historical method)."""
    if len(returns) == 0:
        return 0.0
    var = value_at_risk(returns, confidence)
    tail = [r for r in returns if r <= -var]
    if len(tail) == 0:
        return var
    return -mean(tail)


def expected_shortfall(returns: Sequence[float], confidence: float = 0.95) -> float:
    return conditional_var(returns, confidence)


# ──────────────────────────────────────────────
# Factor measures
# ──────────────────────────────────────────────


def beta(asset_returns: Sequence[float], market_returns: Sequence[float]) -> float:
    var_m = variance(market_returns)
    if var_m == 0:
        return 0.0
    return covariance(asset_returns, market_returns) / var_m


def alpha(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    b = beta(asset_returns, market_returns)
    asset_ann = _annualise(mean(asset_returns), periods_per_year)
    market_ann = _annualise(mean(market_returns), periods_per_year)
    return asset_ann - (risk_free_rate + b * (market_ann - risk_free_rate))


def treynor_ratio(
    asset_returns: Sequence[float],
    market_returns: Sequence[float],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    b = beta(asset_returns, market_returns)
    if b == 0:
        return 0.0
    ann = _annualise(mean(asset_returns), periods_per_year)
    return (ann - risk_free_rate) / b


def information_ratio(
    asset_returns: Sequence[float],
    benchmark_returns: Sequence[float],
    periods_per_year: int = 252,
) -> float:
    if len(asset_returns) != len(benchmark_returns):
        return 0.0
    active = [a - b for a, b in zip(asset_returns, benchmark_returns)]
    tracking_error = std_dev(active)
    if tracking_error == 0:
        return 0.0
    return _annualise(mean(active), periods_per_year) / tracking_error


# ──────────────────────────────────────────────
# Kelly criterion & allocation
# ──────────────────────────────────────────────


def kelly_fraction(win_probability: float, win_loss_ratio: float) -> float:
    """Kelly fraction f* = p - (1-p)/b."""
    if not (0.0 <= win_probability <= 1.0):
        raise ValueError("win_probability must be in [0, 1]")
    if win_loss_ratio <= 0:
        raise ValueError("win_loss_ratio must be positive")
    p = win_probability
    q = 1.0 - p
    return max(0.0, p - q / win_loss_ratio)


def risk_contributions(portfolio: Portfolio) -> list[RiskContribution]:
    """Euler risk contributions from covariance."""
    portfolio.validate()
    if not portfolio.asset_returns:
        return []
    n = portfolio.num_assets
    cov = covariance_matrix(portfolio.asset_returns)
    w = list(portfolio.weights)

    port_var = 0.0
    for i in range(n):
        for j in range(n):
            port_var += w[i] * w[j] * cov[i][j]
    port_vol = math.sqrt(max(port_var, 0.0))
    if port_vol == 0:
        return [RiskContribution(asset_index=i, weight=w[i]) for i in range(n)]

    out = []
    for i in range(n):
        marginal = sum(w[j] * cov[i][j] for j in range(n)) / port_vol
        contribution = w[i] * marginal
        out.append(
            RiskContribution(
                asset_index=i,
                weight=w[i],
                marginal_contribution=marginal,
                contribution=contribution,
                percent_contribution=contribution / port_vol if port_vol != 0 else 0.0,
            )
        )
    return out


def allocate_capital(
    portfolio: Portfolio,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> AllocationResult:
    """Risk-budget-weighted capital allocation (research-only sizing)."""
    portfolio.validate()
    rc = risk_contributions(portfolio)
    if not rc:
        return AllocationResult(total_capital=portfolio.initial_capital)

    total_pct = sum(r.percent_contribution for r in rc)
    if total_pct == 0:
        frac = [1.0 / len(rc)] * len(rc)
    else:
        # Inverse-risk weighting for diversification.
        inv = [1.0 / max(r.percent_contribution, 1e-9) for r in rc]
        total_inv = sum(inv)
        frac = [v / total_inv for v in inv]

    capital = [portfolio.initial_capital * f for f in frac]

    returns = portfolio_returns(portfolio)
    wins = [r for r in returns if r > 0.0]
    losses = [r for r in returns if r < 0.0]
    if wins and losses:
        p = len(wins) / len(returns)
        average_win = mean(wins)
        average_loss = abs(mean(losses))
        b = average_win / average_loss if average_loss > 0.0 else 0.0
        kelly = kelly_fraction(p, b) if b > 0.0 else 0.0
    else:
        # Kelly sizing is undefined without both winning and losing outcomes.
        kelly = 0.0

    return AllocationResult(
        capital_per_asset=capital,
        risk_budget_per_asset=[r.percent_contribution for r in rc],
        kelly_fraction=kelly,
        total_capital=portfolio.initial_capital,
    )


# ──────────────────────────────────────────────
# Drawdown attribution & exposure
# ──────────────────────────────────────────────


def drawdown_attribution(asset_returns: list[list[float]]) -> dict[str, list[float]]:
    """Per-asset running drawdown series."""
    out = {}
    for i, series in enumerate(asset_returns):
        eq = equity_curve_from_returns(series)
        peak = eq[0]
        dds = []
        for v in eq:
            if v > peak:
                peak = v
            dds.append((v - peak) / peak if peak != 0 else 0.0)
        out[f"asset_{i}"] = dds
    return out


def exposure_analytics(portfolio: Portfolio) -> dict[str, float]:
    """Gross/net exposure from weights."""
    portfolio.validate()
    gross = sum(abs(w) for w in portfolio.weights)
    net = sum(portfolio.weights)
    long_exposure = sum(w for w in portfolio.weights if w > 0)
    short_exposure = sum(w for w in portfolio.weights if w < 0)
    leverage = gross
    return {
        "gross_exposure": gross,
        "net_exposure": net,
        "long_exposure": long_exposure,
        "short_exposure": short_exposure,
        "leverage": leverage,
    }


# ──────────────────────────────────────────────
# Top-level portfolio metrics
# ──────────────────────────────────────────────


def compute_portfolio_metrics(
    portfolio: Portfolio,
    benchmark_returns: Sequence[float] | None = None,
    periods_per_year: int = 252,
) -> PortfolioMetrics:
    """Compute the full set of portfolio metrics."""
    portfolio.validate()
    returns = portfolio_returns(portfolio)
    if len(returns) == 0:
        return PortfolioMetrics()

    ann_ret = _annualise(mean(returns), periods_per_year)
    ann_vol = _annualise_std(std_dev(returns), periods_per_year)
    sr = sharpe_ratio(returns, portfolio.risk_free_rate, periods_per_year)
    sor = sortino_ratio(returns, portfolio.risk_free_rate, periods_per_year)
    cal = calmar_ratio(returns, periods_per_year)
    mdd = max_drawdown(equity_curve_from_returns(returns))
    var95 = value_at_risk(returns, 0.95)
    cvar95 = conditional_var(returns, 0.95)
    om = omega_ratio(returns, 0.0)

    b = 0.0
    a = 0.0
    tr = 0.0
    ir = 0.0
    if benchmark_returns is not None and len(benchmark_returns) == len(returns):
        b = beta(returns, benchmark_returns)
        a = alpha(returns, benchmark_returns, portfolio.risk_free_rate, periods_per_year)
        tr = treynor_ratio(returns, benchmark_returns, portfolio.risk_free_rate, periods_per_year)
        ir = information_ratio(returns, benchmark_returns, periods_per_year)

    return PortfolioMetrics(
        annualised_return=ann_ret,
        annualised_volatility=ann_vol,
        sharpe_ratio=sr,
        sortino_ratio=sor,
        calmar_ratio=cal,
        max_drawdown=mdd,
        beta=b,
        alpha=a,
        treynor_ratio=tr,
        information_ratio=ir,
        value_at_risk_95=var95,
        conditional_var_95=cvar95,
        omega_ratio=om,
    )


# ──────────────────────────────────────────────
# Efficient Frontier analytics
# ──────────────────────────────────────────────


def _mat_inv(a: list[list[float]]) -> list[list[float]]:
    """Matrix inversion via Gauss-Jordan elimination."""
    n = len(a)
    if n == 0 or any(len(row) != n for row in a):
        raise ValueError("matrix must be non-empty and square")
    aug = [a[i][:] + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda r: abs(aug[r][i]))
        aug[i], aug[pivot] = aug[pivot], aug[i]
        pv = aug[i][i]
        if abs(pv) < 1e-12:
            raise ValueError("matrix is singular or numerically ill-conditioned")
        for j in range(2 * n):
            aug[i][j] /= pv
        for r in range(n):
            if r != i:
                factor = aug[r][i]
                for j in range(2 * n):
                    aug[r][j] -= factor * aug[i][j]
    return [row[n:] for row in aug]


def _project_simplex(w: list[float]) -> list[float]:
    """Project vector onto probability simplex (sum(w) = 1, w_i >= 0)."""
    n = len(w)
    sorted_w = sorted(w, reverse=True)
    cumulative = 0.0
    rho = -1
    for i in range(n):
        cumulative += sorted_w[i]
        if sorted_w[i] + (1.0 - cumulative) / (i + 1) > 0:
            rho = i
    theta = (1.0 - sum(sorted_w[: rho + 1])) / (rho + 1)
    return [max(0.0, v + theta) for v in w]


def minimum_variance_portfolio(
    asset_returns: list[list[float]],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    allow_short: bool = False,
) -> EfficientFrontierPoint:
    """
    Calculate the Minimum Variance Portfolio weights, expected return, and volatility.
    """
    n_assets = len(asset_returns)
    if n_assets == 0:
        return EfficientFrontierPoint(weights=[])

    cov = covariance_matrix(asset_returns)
    ann_returns = [_annualise(mean(r), periods_per_year) for r in asset_returns]

    if allow_short:
        cov_inv = _mat_inv(cov)
        ones = [1.0] * n_assets
        inv_ones = [sum(cov_inv[i][j] * ones[j] for j in range(n_assets)) for i in range(n_assets)]
        denom = sum(inv_ones)
        weights = [v / denom if denom != 0 else 1.0 / n_assets for v in inv_ones]
    else:
        weights = [1.0 / n_assets] * n_assets
        lr = 0.01
        for _ in range(500):
            grad = [2.0 * sum(cov[i][j] * weights[j] for j in range(n_assets)) for i in range(n_assets)]
            weights = [weights[i] - lr * grad[i] for i in range(n_assets)]
            weights = _project_simplex(weights)

    p_var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n_assets) for j in range(n_assets))
    p_vol = math.sqrt(max(0.0, p_var)) * math.sqrt(periods_per_year)
    p_ret = sum(w * r for w, r in zip(weights, ann_returns))
    sr = (p_ret - risk_free_rate) / p_vol if p_vol > 0 else 0.0

    return EfficientFrontierPoint(
        weights=weights,
        expected_return=p_ret,
        volatility=p_vol,
        sharpe_ratio=sr,
    )


def maximum_sharpe_portfolio(
    asset_returns: list[list[float]],
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    allow_short: bool = False,
) -> EfficientFrontierPoint:
    """
    Calculate the Maximum Sharpe Ratio Portfolio weights, expected return, and volatility.
    """
    n_assets = len(asset_returns)
    if n_assets == 0:
        return EfficientFrontierPoint(weights=[])

    cov = covariance_matrix(asset_returns)
    ann_returns = [_annualise(mean(r), periods_per_year) for r in asset_returns]
    excess_returns = [r - risk_free_rate for r in ann_returns]

    if allow_short:
        cov_inv = _mat_inv(cov)
        unscaled = [sum(cov_inv[i][j] * excess_returns[j] for j in range(n_assets)) for i in range(n_assets)]
        denom = sum(unscaled)
        weights = [v / denom if denom != 0 else 1.0 / n_assets for v in unscaled]
    else:
        weights = [1.0 / n_assets] * n_assets
        best_weights = list(weights)
        best_sr = -float("inf")

        for _ in range(500):
            p_var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n_assets) for j in range(n_assets))
            p_vol = math.sqrt(max(1e-12, p_var)) * math.sqrt(periods_per_year)
            p_ret = sum(w * r for w, r in zip(weights, ann_returns))
            sr = (p_ret - risk_free_rate) / p_vol if p_vol > 0 else 0.0

            if sr > best_sr:
                best_sr = sr
                best_weights = list(weights)

            eps = 1e-5
            grad = []
            for i in range(n_assets):
                w_plus = list(weights)
                w_plus[i] += eps
                w_plus = _project_simplex(w_plus)
                var_p = sum(w_plus[a] * w_plus[b] * cov[a][b] for a in range(n_assets) for b in range(n_assets))
                vol_p = math.sqrt(max(1e-12, var_p)) * math.sqrt(periods_per_year)
                ret_p = sum(w * r for w, r in zip(w_plus, ann_returns))
                sr_p = (ret_p - risk_free_rate) / vol_p if vol_p > 0 else 0.0
                grad.append((sr_p - sr) / eps)

            weights = [weights[i] + 0.05 * grad[i] for i in range(n_assets)]
            weights = _project_simplex(weights)

        weights = best_weights

    p_var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n_assets) for j in range(n_assets))
    p_vol = math.sqrt(max(0.0, p_var)) * math.sqrt(periods_per_year)
    p_ret = sum(w * r for w, r in zip(weights, ann_returns))
    sr = (p_ret - risk_free_rate) / p_vol if p_vol > 0 else 0.0

    return EfficientFrontierPoint(
        weights=weights,
        expected_return=p_ret,
        volatility=p_vol,
        sharpe_ratio=sr,
    )


def efficient_frontier(
    asset_returns: list[list[float]],
    num_portfolios: int = 20,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
    allow_short: bool = False,
) -> EfficientFrontierResult:
    """
    Generate the Efficient Frontier curve, Minimum Variance portfolio, and Max Sharpe portfolio.
    """
    n_assets = len(asset_returns)
    if n_assets == 0:
        return EfficientFrontierResult()

    cov = covariance_matrix(asset_returns)
    ann_returns = [_annualise(mean(r), periods_per_year) for r in asset_returns]

    min_var_p = minimum_variance_portfolio(asset_returns, risk_free_rate, periods_per_year, allow_short)
    max_sharpe_p = maximum_sharpe_portfolio(asset_returns, risk_free_rate, periods_per_year, allow_short)

    min_ret = min(ann_returns)
    max_ret = max(ann_returns)
    if min_ret == max_ret:
        target_returns = [min_ret]
    else:
        step = (max_ret - min_ret) / max(1, num_portfolios - 1)
        target_returns = [min_ret + i * step for i in range(num_portfolios)]

    frontier_points: list[EfficientFrontierPoint] = []

    for target_r in target_returns:
        weights = [1.0 / n_assets] * n_assets
        lr = 0.01
        for _ in range(300):
            p_ret = sum(w * r for w, r in zip(weights, ann_returns))
            ret_err = p_ret - target_r
            grad = [2.0 * sum(cov[i][j] * weights[j] for j in range(n_assets)) + 5.0 * ret_err * ann_returns[i] for i in range(n_assets)]
            weights = [weights[i] - lr * grad[i] for i in range(n_assets)]
            if not allow_short:
                weights = _project_simplex(weights)

        p_var = sum(weights[i] * weights[j] * cov[i][j] for i in range(n_assets) for j in range(n_assets))
        p_vol = math.sqrt(max(0.0, p_var)) * math.sqrt(periods_per_year)
        p_ret = sum(w * r for w, r in zip(weights, ann_returns))
        sr = (p_ret - risk_free_rate) / p_vol if p_vol > 0 else 0.0

        frontier_points.append(
            EfficientFrontierPoint(
                weights=weights,
                expected_return=p_ret,
                volatility=p_vol,
                sharpe_ratio=sr,
            )
        )

    return EfficientFrontierResult(
        frontier_points=frontier_points,
        min_variance_portfolio=min_var_p,
        max_sharpe_portfolio=max_sharpe_p,
        covariance_matrix=cov,
        expected_returns=ann_returns,
    )
