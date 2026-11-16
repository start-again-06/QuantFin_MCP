# Architecture

```
src/quant_mcp/
  calculations.py    pure numerics: pricing, bonds, risk, performance, sizing, Monte Carlo
  optimization.py    min-variance, max-Sharpe, risk parity, efficient frontier, HRP (SciPy SLSQP / linkage)
  backtest.py        portfolio backtest with rebalancing and costs; MA-crossover strategy
  market_data.py     price history providers: yfinance (default) and Alpha Vantage
  validation.py      input checks shared by all tools (length, finiteness, bounds, asset count)
  server.py          FastMCP tool registry, logging wrapper, stdio and HTTP entry point
  http_app.py        ASGI app: body-size cap, per-client rate limit, /healthz, streamable HTTP MCP
app.py               Vercel entrypoint that exports `app`
```

## Design decisions

- **Pure calculation core.** `calculations.py`, `optimization.py` and `backtest.py` do no I/O and depend only on
  NumPy and SciPy. They are easy to test and reuse.
- **One validation layer.** Every tool validates inputs before doing work. Validation errors become MCP tool errors
  with a clear message, and never a NaN or a stack trace.
- **Stateless HTTP.** `stateless_http=True` and `json_response=True` let each request run on any instance, which suits
  serverless hosts.
- **Bearer-token auth on `/mcp`.** `QUANT_MCP_API_TOKEN` is checked with a constant-time comparison. The endpoint fails
  closed when no token is configured. Rate limits, body caps, a provider allow-list and platform budgets remain in place.
- **Logging hygiene.** Logs record tool name, duration and outcome. Inputs are never logged, because they can be
  proprietary return series.
- **stdout is reserved for the stdio protocol.** All logging goes to stderr.

## Testing

- `tests/test_calculations.py`: known textbook values, put-call parity, round trips, and a naive reference tree for
  American options.
- `tests/test_optimization.py`: constraints, optimality versus equal weight, HRP and risk-parity properties.
- `tests/test_backtest.py`: hand-computed drift, cost effects, and a look-ahead property test.
- `tests/test_http_app.py`: token accept, reject and fail-closed states, body cap, and an integration test against the real MCP app.
- `tests/test_server.py`: tool registry completeness, error translation, log hygiene, and an end-to-end stdio run.
- Live provider tests are marked `network` and skipped by default.
