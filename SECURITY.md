# Security policy

## Supported versions

The latest minor release receives security fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Report privately through GitHub's
"Report a vulnerability" button on the repository's Security tab, or contact the maintainer directly.

Include the affected version, a description of the impact, and steps to reproduce. You will get an acknowledgement
within 5 working days.

## Deployment security

The HTTP endpoint requires a bearer token. Set `QUANT_MCP_API_TOKEN` (at least 32 characters) on every
deployment and send it as `Authorization: Bearer <token>`. Treat it like a password and rotate it if it leaks.

- Set a rate limit and spending budget in your hosting platform.
- Keep provider keys such as `ALPHAVANTAGE_API_KEY` unset unless the endpoint is protected by your own access control.
- Serve over HTTPS.

## Built-in protections

- Rate limit on `/mcp`: 60 requests per minute per client, per instance (`QUANT_MCP_RATE_LIMIT_PER_MINUTE`).
- Request bodies are capped at 1 MiB (`QUANT_MCP_MAX_BODY_BYTES`).
- `/mcp` requires a bearer token and fails closed (503) when none is configured. Comparison is constant-time.
- Tool inputs are validated for size, finiteness and bounds before computation.
- Tool inputs are not written to logs.
- Market-data providers are an allow-list. Only `yahoo` is enabled by default (`QUANT_MCP_ENABLED_PROVIDERS`).

## Known limits

- The token is one shared secret for the whole deployment. There are no per-user keys or revocation list.
- Anyone holding the token can run the calculators, so it is shared access, not user identity.
- The rate limit does not share state across serverless instances, so it is not a hard global quota.
- The rate limiter trusts the first address in `x-forwarded-for`. Behind a proxy that does not set this header
  correctly, clients can spoof their address to evade the limit.
