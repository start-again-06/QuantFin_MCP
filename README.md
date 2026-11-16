# quant-mcp

[![CI](https://github.com/OWNER/quant-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/quant-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

A [Model Context Protocol](https://modelcontextprotocol.io) server with quantitative finance tools: option pricing,
fixed income, risk, portfolio optimisation, backtesting and position sizing. An MCP-capable assistant can call these
tools directly on data you provide.

It runs over **stdio** for local clients, or over **streamable HTTP** for hosted deployments (for example Vercel).

> **Not investment advice.** These are calculators. Outputs depend entirely on the inputs and assumptions you supply.

## Features

| Area | Tools |
| --- | --- |
| Option pricing | `black_scholes`, `american_option` (binomial tree with early exercise), `implied_volatility`, `monte_carlo_gbm` |
| Fixed income and time value | `bond_analytics` (YTM, duration, convexity, DV01), `npv_irr` |
| Risk | `value_at_risk` (historical, parametric, Cornish-Fisher), `max_drawdown`, `capm_regression`, `correlation_matrix` |
| Performance | `performance_metrics` (CAGR, Sharpe, Sortino, Calmar, skew, kurtosis), `returns_from_prices` |
| Portfolio construction | `min_variance_portfolio`, `max_sharpe_portfolio`, `risk_parity_portfolio`, `efficient_frontier`, `hrp_portfolio`, `portfolio_risk` |
| Backtesting | `backtest_portfolio` (rebalancing, transaction costs), `moving_average_crossover` (no look-ahead) |
| Position sizing | `kelly_fraction`, `kelly_continuous`, `position_size` |
| Market data | `price_history` via Yahoo Finance (no key) or Alpha Vantage (key required) |

The full parameter reference is in [docs/tools.md](docs/tools.md), generated from the live tool registry.

## Quick start

Requires Python 3.11 to 3.13.

```bash
git clone https://github.com/OWNER/quant-mcp.git
cd quant-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -m "not network"
```

### Run over stdio (local MCP clients)

```bash
quant-mcp            # or: python -m quant_mcp
```

Register it in an MCP client config, for example:

```json
{
  "mcpServers": {
    "quant": {
      "command": "/absolute/path/to/quant-mcp/.venv/bin/quant-mcp"
    }
  }
}
```

### Run over HTTP (hosted or containerised)

```bash
export QUANT_MCP_TRANSPORT=http
quant-mcp            # listens on QUANT_MCP_HOST:QUANT_MCP_PORT (default 127.0.0.1:8000)
curl http://127.0.0.1:8000/healthz
```

Endpoints: `GET /healthz` (open) and `POST /mcp`, which requires `Authorization: Bearer $QUANT_MCP_API_TOKEN`.
`/mcp` returns `503` until the token is set. See [docs/deployment.md](docs/deployment.md).

### Docker

```bash
docker build -t quant-mcp .
docker run --rm -p 8000:8000 quant-mcp
```

## Configuration

All configuration is through environment variables. See [.env.example](.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `QUANT_MCP_TRANSPORT` | `stdio` | `stdio` or `http` |
| `QUANT_MCP_API_TOKEN` | unset | Bearer token required on `/mcp` (at least 32 characters). Unset means `/mcp` returns `503`. |
| `QUANT_MCP_ALLOW_ANONYMOUS` | unset | Set to `1` to serve `/mcp` without a token. Only if the URL is protected elsewhere. |
| `QUANT_MCP_ALLOWED_HOSTS` | unset | Comma-separated Host allow-list. Setting it enables DNS-rebinding protection. |
| `QUANT_MCP_MAX_BODY_BYTES` | `1048576` | Maximum request body size |
| `QUANT_MCP_HOST` / `QUANT_MCP_PORT` | `127.0.0.1` / `8000` | HTTP bind address |
| `QUANT_MCP_LOG_LEVEL` | `WARNING` | Logs go to stderr. Tool inputs are never logged. |
| `QUANT_MCP_RATE_LIMIT_PER_MINUTE` | `60` | Per-client request limit on `/mcp`, per instance. `0` disables. |
| `QUANT_MCP_ENABLED_PROVIDERS` | `yahoo` | Market-data providers the server may call. Add `alphavantage` to enable it. |
| `ALPHAVANTAGE_API_KEY` | unset | Needed only when `alphavantage` is enabled |

## Conventions

- Rates are annual decimals: `0.05` means 5%.
- Returns are simple periodic returns: `0.01` means 1%.
- `theta` is per calendar day, `vega` per 1 volatility point, `rho` per 1% rate move.
- Bonds assume whole coupon periods and no accrued interest.
- Backtests act on the next period (no look-ahead). Costs are charged on traded notional.

## Documentation

- [Tool reference](docs/tools.md)
- [Deployment guide](docs/deployment.md): Vercel, Docker, and self-hosting
- [Client configuration](docs/client-config.md): stdio and HTTP with a bearer token
- [Architecture](docs/architecture.md)
- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md) and [security policy](SECURITY.md)

## Development

```bash
ruff check src tests app.py && ruff format --check src tests app.py
mypy
pytest -m "not network"
python scripts/generate_tool_docs.py --check
```

Live provider tests are opt-in: `QUANT_MCP_RUN_NETWORK_TESTS=1 pytest -m network`.

## Limits

- European options only in `black_scholes`. `american_option` uses a CRR tree with a continuous dividend yield.
- Backtests are research tools. They have no slippage model beyond a flat cost in basis points.
- Market data is not licensed or real-time. Check the terms of Yahoo Finance or Alpha Vantage before commercial use.

## License

MIT. See [LICENSE](LICENSE).
