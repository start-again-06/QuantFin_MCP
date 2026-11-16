# Deployment

## Choosing a host

- **Vercel (recommended for hosted HTTP).** Vercel runs Python ASGI apps natively. This repo's `app.py` exports the `app`
  object that Vercel looks for. The default Python runtime is 3.12, and `.python-version` pins it.
- **Docker** on any container host (Fly.io, Render, Cloud Run, ECS, a VM). Use the included `Dockerfile`.
- **Netlify is not suitable.** Netlify Functions do not support Python, so this server cannot run there.

## Security model

The HTTP endpoint requires `Authorization: Bearer <QUANT_MCP_API_TOKEN>`. Anyone holding that token can run the calculators, and
the costs fall on you:

- **Compute.** Your function invocations and CPU time.
- **Market data.** Alpha Vantage is disabled by default, so callers cannot spend your API quota. Keep it disabled unless
  you add your own access control.

Built-in protections:

- **Rate limit.** `/mcp` allows 60 requests per minute per client by default. The limit is per instance, not a global
  quota, because serverless instances do not share memory.
- **Body cap.** Request bodies are limited to 1 MiB.
- **Input validation.** Tool inputs are checked for size, finiteness and bounds before any computation.
- **Logging.** Tool inputs are never logged.

Recommended for any public deployment:

1. Set a **platform-level rate limit and spending budget**. On Vercel, configure this in the project's firewall or usage
   settings. Check Vercel's current documentation for the exact menu names, since they change.
2. Keep `ALPHAVANTAGE_API_KEY` unset unless you have a protection in front of the endpoint.
3. Serve over HTTPS only. Vercel and most container platforms do this by default.

## Vercel

1. Push the repository to GitHub.
2. In Vercel, choose **Add New > Project** and import the repository. Leave the root directory at the repo root.
   Vercel detects `app.py` and `requirements.txt` automatically.
3. Under **Settings > Environment Variables**, add `QUANT_MCP_API_TOKEN` with a random value of at least 32 characters
   (for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Without it, `/mcp` returns `503`.
   Optionally add `ALPHAVANTAGE_API_KEY` if you have a protection in front of the endpoint. Do not set
   `QUANT_MCP_TRANSPORT`. It applies only to the standalone process.
4. Deploy. Then check it with the smoke test:

   ```bash
   QUANT_MCP_API_TOKEN=... python scripts/smoke_test.py https://YOUR-PROJECT.vercel.app
   ```

   Or with curl:

   ```bash
   curl https://YOUR-PROJECT.vercel.app/healthz
   curl -X POST https://YOUR-PROJECT.vercel.app/mcp \
     -H "Authorization: Bearer $QUANT_MCP_API_TOKEN" \
     -H "Accept: application/json, text/event-stream" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"check","version":"1"}}}'
   ```

5. Point your MCP client at `https://YOUR-PROJECT.vercel.app/mcp` with the header `Authorization: Bearer <token>`.
   Example client configs are in [docs/client-config.md](client-config.md).

### Things to verify on the first Vercel deploy

I could not deploy to Vercel from the development environment, so confirm these yourself:

- **Bundle size.** `numpy`, `scipy`, `pandas` and `yfinance` are large. If the build fails on size, remove `yfinance` and
  `pandas` from `requirements.txt`. The Alpha Vantage provider and every calculator still work without them.
- **Yahoo from cloud IPs.** Yahoo Finance sometimes blocks cloud provider addresses. If `price_history` fails on Vercel but
  works locally, the Alpha Vantage provider is the alternative, but it needs the enable setting described above.
- **Function timeout.** `vercel.json` sets `maxDuration` to 60 seconds. Large Monte Carlo runs or efficient frontiers can
  take longer. Lower the input sizes or raise the limit within your plan's allowance.
- **Cold starts.** The first request after idle time pays the import cost of scipy and numpy.

## Docker

```bash
docker build -t quant-mcp .
docker run -d --name quant-mcp -p 8000:8000 quant-mcp
```

The image runs as a non-root user and has a healthcheck on `/healthz`. Put a TLS-terminating reverse proxy (Caddy, nginx,
or your platform's load balancer) in front of port 8000.

## Self-hosting with uvicorn

```bash
pip install .
QUANT_MCP_TRANSPORT=http QUANT_MCP_HOST=0.0.0.0 QUANT_MCP_PORT=8000 quant-mcp
```

For more workers, run uvicorn directly: `uvicorn app:app --workers 4`. The server is stateless, so workers can be scaled
horizontally.
