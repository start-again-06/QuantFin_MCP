# Tool reference

Generated from the server's tool registry by `scripts/generate_tool_docs.py`. Do not edit by hand.

24 tools.

## `american_option`

Price an American option on a Cox-Ross-Rubinstein binomial tree.

Returns price, delta, gamma, vega (per vol point), theta (per day), and the
early-exercise premium over the European Black-Scholes price.


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `spot` | number | yes | - |
| `strike` | number | yes | - |
| `time_years` | number | yes | - |
| `rate` | number | yes | - |
| `volatility` | number | yes | - |
| `option_type` | string | no | "put" |
| `dividend_yield` | number | no | 0.0 |
| `steps` | integer | no | 500 |

## `backtest_portfolio`

Backtest fixed target weights with periodic rebalancing and transaction costs.

rebalance_every: periods between rebalances (21 ~ monthly on daily data), or null for buy-and-hold.


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `target_weights` | object | yes | - |
| `rebalance_every` | integer | null | no | 21 |
| `cost_bps` | number | no | 5.0 |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `black_scholes`

Price a European option with Black-Scholes-Merton and return Greeks.

theta is per calendar day; vega is per 1 vol point; rho is per 1% rate move.


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `spot` | number | yes | - |
| `strike` | number | yes | - |
| `time_years` | number | yes | - |
| `rate` | number | yes | - |
| `volatility` | number | yes | - |
| `option_type` | string | no | "call" |
| `dividend_yield` | number | no | 0.0 |

## `bond_analytics`

Bond price, yield, Macaulay/modified duration, convexity and DV01.

Provide exactly one of `ytm` (annual) or `price`. Assumes whole coupon periods
and no accrued interest.


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `face_value` | number | yes | - |
| `coupon_rate` | number | yes | - |
| `years_to_maturity` | number | yes | - |
| `frequency` | integer | no | 2 |
| `ytm` | number | null | no | null |
| `price` | number | null | no | null |

## `capm_regression`

CAPM regression of an asset on the market: beta, annualised alpha, R², t-stat.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `asset_returns` | array | yes | - |
| `market_returns` | array | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `correlation_matrix`

Pairwise correlation of several return series given as {asset: [returns...]}.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |

## `efficient_frontier`

Mean-variance efficient frontier with weights at each target return.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `points` | integer | no | 20 |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |
| `long_only` | boolean | no | true |
| `max_weight` | number | no | 1.0 |

## `hrp_portfolio`

Hierarchical Risk Parity weights (Lopez de Prado). Stable without matrix inversion.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `implied_volatility`

Back out the Black-Scholes implied volatility from an observed European option price.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `market_price` | number | yes | - |
| `spot` | number | yes | - |
| `strike` | number | yes | - |
| `time_years` | number | yes | - |
| `rate` | number | yes | - |
| `option_type` | string | no | "call" |
| `dividend_yield` | number | no | 0.0 |

## `kelly_continuous`

Continuous Kelly leverage f = mu / variance, inputs in the same period units.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `mean_excess_return` | number | yes | - |
| `variance` | number | yes | - |

## `kelly_fraction`

Kelly bet fraction for a binary bet. payoff_ratio = profit per unit staked if you win.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `win_probability` | number | yes | - |
| `payoff_ratio` | number | yes | - |

## `max_drawdown`

Maximum peak-to-trough drawdown of the compounded return series.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | array | yes | - |

## `max_sharpe_portfolio`

Tangency (maximum Sharpe ratio) portfolio. Estimates are noisy; prefer HRP or min-variance.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |
| `long_only` | boolean | no | true |
| `max_weight` | number | no | 1.0 |

## `min_variance_portfolio`

Global minimum-variance portfolio from historical return series.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `periods_per_year` | integer | no | 252 |
| `long_only` | boolean | no | true |
| `max_weight` | number | no | 1.0 |
| `risk_free_annual` | number | no | 0.0 |

## `monte_carlo_gbm`

Simulate terminal prices under geometric Brownian motion.

Returns terminal-price percentiles and P(end < start). If strike is given,
also prices a European option by Monte Carlo (discounted at `drift`).


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `spot` | number | yes | - |
| `drift` | number | yes | - |
| `volatility` | number | yes | - |
| `time_years` | number | yes | - |
| `paths` | integer | no | 10000 |
| `seed` | integer | null | no | 42 |
| `strike` | number | null | no | null |
| `option_type` | string | no | "call" |

## `moving_average_crossover`

Long/flat moving-average crossover backtest on a price series, versus buy-and-hold.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `prices` | array | yes | - |
| `fast` | integer | no | 20 |
| `slow` | integer | no | 100 |
| `cost_bps` | number | no | 5.0 |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `npv_irr`

NPV at a discount rate and IRR for cashflows at t = 0, 1, 2, ... (periods).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `cashflows` | array | yes | - |
| `discount_rate` | number | null | no | null |

## `performance_metrics`

CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, skew and kurtosis.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | array | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `portfolio_risk`

Portfolio expected return, volatility, Sharpe and each asset's share of risk.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `weights` | object | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `position_size`

Share count so that a stop-out loses at most risk_fraction of the account (e.g. 0.01).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `account_value` | number | yes | - |
| `risk_fraction` | number | yes | - |
| `entry_price` | number | yes | - |
| `stop_price` | number | yes | - |

## `price_history`

Historical closing prices for a ticker.

provider 'yahoo' (default): Yahoo Finance via yfinance, no key, needs internet access.
provider 'alphavantage': needs ALPHAVANTAGE_API_KEY and must be enabled by the operator
(QUANT_MCP_ENABLED_PROVIDERS); daily only.


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `ticker` | string | yes | - |
| `period` | string | no | "1y" |
| `interval` | string | no | "1d" |
| `adjusted` | boolean | no | true |
| `provider` | string | no | "yahoo" |

## `returns_from_prices`

Convert a price series into simple periodic returns.

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `prices` | array | yes | - |

## `risk_parity_portfolio`

Equal risk contribution portfolio (long-only, fully invested).

| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | object | yes | - |
| `periods_per_year` | integer | no | 252 |
| `risk_free_annual` | number | no | 0.0 |

## `value_at_risk`

Value at Risk and Expected Shortfall from periodic returns.

method: 'historical', 'parametric' (normal) or 'cornish_fisher' (skew/kurtosis-adjusted).


| Parameter | Type | Required | Default |
| --- | --- | --- | --- |
| `returns` | array | yes | - |
| `confidence` | number | no | 0.95 |
| `horizon_days` | integer | no | 1 |
| `method` | string | no | "historical" |
