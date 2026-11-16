"""Quant MCP server: pricing, risk, portfolio construction, backtesting and sizing tools.

Transport is stdio. Logs go to stderr only, because stdout carries the protocol.
Set QUANT_MCP_LOG_LEVEL (DEBUG, INFO, WARNING, ERROR) to change verbosity.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from quant_mcp import __version__, market_data
from quant_mcp import backtest as bt
from quant_mcp import calculations as calc
from quant_mcp import optimization as opt
from quant_mcp.validation import ValidationError

log = logging.getLogger("quant_mcp")


def _transport_security() -> TransportSecuritySettings:
    """DNS-rebinding protection settings.

    The SDK's rebinding check is aimed at browsers talking to a local server and
    only supports exact hosts and ':*' port wildcards. Serverless hosts such as
    Vercel send arbitrary hostnames, so the check is off by default. Set QUANT_MCP_ALLOWED_HOSTS to a
    comma-separated list, e.g. "quant.example.com,quant.example.com:443", to enable it.
    """
    raw = os.environ.get("QUANT_MCP_ALLOWED_HOSTS", "").strip()
    if not raw:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts = [h.strip() for h in raw.split(",") if h.strip()]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"https://{h}" for h in hosts],
    )


mcp = FastMCP(
    "quant",
    instructions=(
        "Quantitative finance calculators. Rates are annual decimals (0.05 = 5%). "
        "Returns are simple periodic returns (0.01 = 1%). Calculators compute on the data "
        "you supply; price_history fetches prices from an external provider."
    ),
    # Stateless + JSON responses let each HTTP request run on any serverless instance.
    stateless_http=True,
    json_response=True,
    transport_security=_transport_security(),
)


def _configure_logging() -> None:
    level_name = os.environ.get("QUANT_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Register a tool with logging and uniform error translation.

    Inputs are never logged (they may contain proprietary return series).
    Only the tool name, duration and outcome are recorded.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except ValidationError as exc:
            log.info("tool=%s status=invalid_input", fn.__name__)
            raise ValueError(str(exc)) from None
        except Exception:
            log.exception("tool=%s status=error", fn.__name__)
            raise
        log.info("tool=%s status=ok duration_ms=%.1f", fn.__name__, (time.perf_counter() - start) * 1000)
        return result

    return wrapper


def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    return mcp.tool()(_tool(fn))


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


@tool
def black_scholes(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
) -> dict:
    """Price a European option with Black-Scholes-Merton and return Greeks.

    theta is per calendar day; vega is per 1 vol point; rho is per 1% rate move.
    """
    return calc.black_scholes(spot, strike, time_years, rate, volatility, option_type, dividend_yield)


@tool
def american_option(
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    volatility: float,
    option_type: str = "put",
    dividend_yield: float = 0.0,
    steps: int = 500,
) -> dict:
    """Price an American option on a Cox-Ross-Rubinstein binomial tree.

    Returns price, delta, gamma, vega (per vol point), theta (per day), and the
    early-exercise premium over the European Black-Scholes price.
    """
    return calc.american_binomial(
        spot, strike, time_years, rate, volatility, option_type, dividend_yield, steps
    )


@tool
def implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    option_type: str = "call",
    dividend_yield: float = 0.0,
) -> dict:
    """Back out the Black-Scholes implied volatility from an observed European option price."""
    iv = calc.implied_volatility(market_price, spot, strike, time_years, rate, option_type, dividend_yield)
    return {"implied_volatility": iv}


@tool
def monte_carlo_gbm(
    spot: float,
    drift: float,
    volatility: float,
    time_years: float,
    paths: int = 10000,
    seed: int | None = 42,
    strike: float | None = None,
    option_type: str = "call",
) -> dict:
    """Simulate terminal prices under geometric Brownian motion.

    Returns terminal-price percentiles and P(end < start). If strike is given,
    also prices a European option by Monte Carlo (discounted at `drift`).
    """
    return calc.monte_carlo_gbm(
        spot,
        drift,
        volatility,
        time_years,
        paths=paths,
        seed=seed,
        strike=strike,
        option_type=option_type,
    )


# ---------------------------------------------------------------------------
# Fixed income and time value
# ---------------------------------------------------------------------------


@tool
def bond_analytics(
    face_value: float,
    coupon_rate: float,
    years_to_maturity: float,
    frequency: int = 2,
    ytm: float | None = None,
    price: float | None = None,
) -> dict:
    """Bond price, yield, Macaulay/modified duration, convexity and DV01.

    Provide exactly one of `ytm` (annual) or `price`. Assumes whole coupon periods
    and no accrued interest.
    """
    return calc.bond_analytics(face_value, coupon_rate, years_to_maturity, frequency, ytm, price)


@tool
def npv_irr(cashflows: list[float], discount_rate: float | None = None) -> dict:
    """NPV at a discount rate and IRR for cashflows at t = 0, 1, 2, ... (periods)."""
    return calc.npv_irr(cashflows, discount_rate)


# ---------------------------------------------------------------------------
# Risk and performance
# ---------------------------------------------------------------------------


@tool
def value_at_risk(
    returns: list[float],
    confidence: float = 0.95,
    horizon_days: int = 1,
    method: str = "historical",
) -> dict:
    """Value at Risk and Expected Shortfall from periodic returns.

    method: 'historical', 'parametric' (normal) or 'cornish_fisher' (skew/kurtosis-adjusted).
    """
    return calc.value_at_risk(returns, confidence, horizon_days, method)


@tool
def performance_metrics(
    returns: list[float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, skew and kurtosis."""
    return calc.performance_metrics(returns, periods_per_year, risk_free_annual)


@tool
def max_drawdown(returns: list[float]) -> dict:
    """Maximum peak-to-trough drawdown of the compounded return series."""
    return calc.max_drawdown(returns)


@tool
def returns_from_prices(prices: list[float]) -> dict:
    """Convert a price series into simple periodic returns."""
    return {"returns": calc.returns_from_prices(prices)}


@tool
def correlation_matrix(returns: Mapping[str, list[float]]) -> dict:
    """Pairwise correlation of several return series given as {asset: [returns...]}."""
    return calc.correlation_matrix(returns)


@tool
def capm_regression(
    asset_returns: list[float],
    market_returns: list[float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """CAPM regression of an asset on the market: beta, annualised alpha, R², t-stat."""
    return calc.capm_regression(asset_returns, market_returns, periods_per_year, risk_free_annual)


# ---------------------------------------------------------------------------
# Portfolio construction
# ---------------------------------------------------------------------------


@tool
def portfolio_risk(
    returns: Mapping[str, list[float]],
    weights: Mapping[str, float],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Portfolio expected return, volatility, Sharpe and each asset's share of risk."""
    return calc.portfolio_risk(returns, weights, periods_per_year, risk_free_annual)


@tool
def min_variance_portfolio(
    returns: Mapping[str, list[float]],
    periods_per_year: int = 252,
    long_only: bool = True,
    max_weight: float = 1.0,
    risk_free_annual: float = 0.0,
) -> dict:
    """Global minimum-variance portfolio from historical return series."""
    return opt.min_variance(returns, periods_per_year, long_only, max_weight, risk_free_annual)


@tool
def max_sharpe_portfolio(
    returns: Mapping[str, list[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
    long_only: bool = True,
    max_weight: float = 1.0,
) -> dict:
    """Tangency (maximum Sharpe ratio) portfolio. Estimates are noisy; prefer HRP or min-variance."""
    return opt.max_sharpe(returns, periods_per_year, risk_free_annual, long_only, max_weight)


@tool
def risk_parity_portfolio(
    returns: Mapping[str, list[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Equal risk contribution portfolio (long-only, fully invested)."""
    return opt.risk_parity(returns, periods_per_year, risk_free_annual)


@tool
def efficient_frontier(
    returns: Mapping[str, list[float]],
    points: int = 20,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
    long_only: bool = True,
    max_weight: float = 1.0,
) -> dict:
    """Mean-variance efficient frontier with weights at each target return."""
    return opt.efficient_frontier(returns, points, periods_per_year, risk_free_annual, long_only, max_weight)


@tool
def hrp_portfolio(
    returns: Mapping[str, list[float]],
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Hierarchical Risk Parity weights (Lopez de Prado). Stable without matrix inversion."""
    return opt.hrp(returns, periods_per_year, risk_free_annual)


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------


@tool
def backtest_portfolio(
    returns: Mapping[str, list[float]],
    target_weights: Mapping[str, float],
    rebalance_every: int | None = 21,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Backtest fixed target weights with periodic rebalancing and transaction costs.

    rebalance_every: periods between rebalances (21 ~ monthly on daily data), or null for buy-and-hold.
    """
    return bt.backtest_portfolio(
        returns, target_weights, rebalance_every, cost_bps, periods_per_year, risk_free_annual
    )


@tool
def moving_average_crossover(
    prices: list[float],
    fast: int = 20,
    slow: int = 100,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
    risk_free_annual: float = 0.0,
) -> dict:
    """Long/flat moving-average crossover backtest on a price series, versus buy-and-hold."""
    return bt.moving_average_crossover(prices, fast, slow, cost_bps, periods_per_year, risk_free_annual)


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------


@tool
def kelly_fraction(win_probability: float, payoff_ratio: float) -> dict:
    """Kelly bet fraction for a binary bet. payoff_ratio = profit per unit staked if you win."""
    return calc.kelly_fraction(win_probability, payoff_ratio)


@tool
def kelly_continuous(mean_excess_return: float, variance: float) -> dict:
    """Continuous Kelly leverage f = mu / variance, inputs in the same period units."""
    return calc.kelly_continuous(mean_excess_return, variance)


@tool
def position_size(
    account_value: float,
    risk_fraction: float,
    entry_price: float,
    stop_price: float,
) -> dict:
    """Share count so that a stop-out loses at most risk_fraction of the account (e.g. 0.01)."""
    return calc.position_size(account_value, risk_fraction, entry_price, stop_price)


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------


@tool
def price_history(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    adjusted: bool = True,
    provider: str = "yahoo",
) -> dict:
    """Historical closing prices for a ticker.

    provider 'yahoo' (default): Yahoo Finance via yfinance, no key, needs internet access.
    provider 'alphavantage': needs ALPHAVANTAGE_API_KEY and must be enabled by the operator
    (QUANT_MCP_ENABLED_PROVIDERS); daily only.
    """
    return market_data.price_history(ticker, period, interval, adjusted, provider)


def main() -> None:
    """Run over stdio (default) or streamable HTTP (QUANT_MCP_TRANSPORT=http)."""
    _configure_logging()
    transport = os.environ.get("QUANT_MCP_TRANSPORT", "stdio").lower()
    log.info("starting quant-mcp %s transport=%s", __version__, transport)
    if transport == "stdio":
        mcp.run()
    elif transport == "http":
        import uvicorn

        from quant_mcp.http_app import create_app

        host = os.environ.get("QUANT_MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("QUANT_MCP_PORT", "8000"))
        uvicorn.run(create_app(), host=host, port=port, log_level="info", proxy_headers=True)
    else:
        raise SystemExit("QUANT_MCP_TRANSPORT must be 'stdio' or 'http'.")


if __name__ == "__main__":
    main()
