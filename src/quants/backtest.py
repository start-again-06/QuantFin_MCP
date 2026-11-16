"""Simple, transparent backtesting with transaction costs.

These backtests are vectorised-enough for research use and deliberately simple:
daily signals act on the next period (no look-ahead), costs are charged on
traded value, and there is no slippage model beyond the flat cost in basis points.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from quant_mcp.calculations import performance_metrics
from quant_mcp.validation import (
    ValidationError,
    aligned_matrix,
    check_positive_int,
    check_series,
)

MAX_COST_BPS = 1000.0


def _check_cost(cost_bps: float) -> float:
    if not 0 <= cost_bps <= MAX_COST_BPS:
        raise ValidationError(f"cost_bps must be between 0 and {MAX_COST_BPS:g}.")
    return float(cost_bps)


def backtest_portfolio(
    returns: Mapping[str, Sequence[float]],
    target_weights: Mapping[str, float],
    rebalance_every: int | None = 21,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Backtest a fixed-target-weight portfolio.

    rebalance_every: rebalance back to target every N periods (None = buy and hold).
    cost_bps: one-way cost charged on traded value at each rebalance (and at start).
    Weights are normalised to sum to 1; negative weights are shorts.
    """
    names, mat = aligned_matrix(returns, min_length=3)
    if set(target_weights) != set(names):
        raise ValidationError("target_weights must have exactly the same keys as returns.")
    w_target = np.array([float(target_weights[n]) for n in names])
    if abs(w_target.sum()) < 1e-12:
        raise ValidationError("target_weights sum to zero.")
    w_target = w_target / w_target.sum()
    if rebalance_every is not None:
        check_positive_int(rebalance_every, "rebalance_every", maximum=10_000)
    cost = _check_cost(cost_bps) / 10_000.0
    check_positive_int(periods_per_year, "periods_per_year", maximum=366)

    T = mat.shape[1]
    w = w_target.copy()
    turnover_total = 0.0
    cost_total = 0.0
    port_returns = np.empty(T)
    weight_history_last = w.copy()

    # Initial purchase from cash costs the traded notional once.
    initial_turnover = float(np.abs(w_target).sum())
    initial_cost = initial_turnover * cost
    cost_total += initial_cost
    turnover_total += initial_turnover

    for t in range(T):
        r = mat[:, t]
        gross = float(np.sum(w * (1.0 + r)))
        if gross <= 0:
            raise ValidationError("Portfolio value fell to zero or below; cannot continue the backtest.")
        drifted = w * (1.0 + r) / gross
        period_return = gross - 1.0
        if t == 0:
            period_return -= initial_cost
        w = drifted
        if rebalance_every is not None and (t + 1) % rebalance_every == 0 and t + 1 < T:
            traded_notional = float(np.abs(w_target - w).sum())  # buys + sells
            trade_cost = traded_notional * cost
            period_return -= trade_cost
            cost_total += trade_cost
            turnover_total += traded_notional / 2.0  # one-way turnover
            w = w_target.copy()
        port_returns[t] = period_return
        weight_history_last = w

    metrics = performance_metrics(port_returns.tolist(), periods_per_year, risk_free_annual)
    return {
        "method": "backtest_portfolio",
        "assets": names,
        "rebalance_every_periods": rebalance_every,
        "cost_bps": cost_bps,
        "net_returns": port_returns.tolist(),
        "metrics": metrics,
        "total_turnover": turnover_total,
        "total_costs_return": cost_total,
        "final_weights": dict(zip(names, [float(x) for x in weight_history_last], strict=False)),
    }


def moving_average_crossover(
    prices: Sequence[float],
    fast: int = 20,
    slow: int = 100,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Long when the fast simple moving average is above the slow one, else flat.

    The position decided at the close of day t is held over day t+1, so the
    strategy never uses the return it is trading on.
    """
    p = check_series(prices, "prices", min_length=10)
    if np.any(p <= 0):
        raise ValidationError("prices must be strictly positive.")
    check_positive_int(fast, "fast", maximum=10_000)
    check_positive_int(slow, "slow", maximum=10_000)
    if fast >= slow:
        raise ValidationError("fast must be shorter than slow.")
    if slow > p.size:
        raise ValidationError("slow window is longer than the price history.")
    cost = _check_cost(cost_bps) / 10_000.0
    check_positive_int(periods_per_year, "periods_per_year", maximum=366)

    def sma(x: np.ndarray, n: int) -> np.ndarray:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out = np.full(x.size, np.nan)
        out[n - 1 :] = (c[n:] - c[:-n]) / n
        return out

    fast_ma = sma(p, fast)
    slow_ma = sma(p, slow)
    signal = (fast_ma > slow_ma).astype(float)  # decided at close of each day
    signal[np.isnan(slow_ma)] = 0.0

    asset_r = p[1:] / p[:-1] - 1.0
    position = signal[:-1]  # position held over the next day
    trades = np.abs(np.diff(np.concatenate(([0.0], position))))
    strat_r = position * asset_r - trades * cost

    metrics = performance_metrics(strat_r.tolist(), periods_per_year, risk_free_annual)
    buy_hold = performance_metrics(asset_r.tolist(), periods_per_year, risk_free_annual)
    return {
        "method": "moving_average_crossover",
        "fast": fast,
        "slow": slow,
        "cost_bps": cost_bps,
        "strategy_metrics": metrics,
        "buy_and_hold_metrics": buy_hold,
        "trades": int(np.sum(trades > 0)),
        "time_in_market": float(position.mean()),
        "net_returns": strat_r.tolist(),
    }
