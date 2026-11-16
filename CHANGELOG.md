# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security
- Bearer-token authentication on `/mcp` via `QUANT_MCP_API_TOKEN` (minimum 32 characters). `/mcp` fails closed with `503`
  when no token is set. `QUANT_MCP_ALLOW_ANONYMOUS=1` is an explicit opt-out. `/healthz` and `/` stay open.
- `QUANT_MCP_RATE_LIMIT_PER_MINUTE`: per-client rate limit on `/mcp` (default 60/minute, per instance). Returns `429` with `Retry-After`.
- `QUANT_MCP_ENABLED_PROVIDERS`: market-data providers are an allow-list. Only `yahoo` is enabled by default, so Alpha Vantage quota cannot be spent unless the operator enables it.

## [1.0.0]

### Added
- Packaged `quant-mcp` distribution with a console script and `python -m quant_mcp` entry point.
- 24 MCP tools across pricing, fixed income, risk, performance, portfolio construction, backtesting, sizing and market data.
- American options on a binomial tree, with Greeks and early-exercise premium.
- Portfolio optimisation: minimum variance, maximum Sharpe, risk parity, efficient frontier, Hierarchical Risk Parity.
- Backtesting: multi-asset rebalancing with transaction costs, and a moving-average crossover with no look-ahead.
- Streamable HTTP transport with a body-size cap, per-client rate limit, and `/healthz`.
- Vercel entrypoint (`app.py`), `vercel.json`, Dockerfile with non-root user and healthcheck.
- Market data via Yahoo Finance (default) and Alpha Vantage (keyed).
- CI: lint, format, type check, tests on Python 3.11 to 3.13, package build, and Docker build.
- Documentation: README, deployment guide, architecture notes, generated tool reference, contributing and security policies.

### Security
- Tool inputs are validated and are never written to logs.
