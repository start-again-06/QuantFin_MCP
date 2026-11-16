# MCP client configuration

Two transports are supported. Pick one per client.

## Local (stdio): no token

For a process on your own machine, the client launches the server directly. stdio has no HTTP endpoint, so
`QUANT_MCP_API_TOKEN` does not apply.

```json
{
  "mcpServers": {
    "quant": {
      "command": "/absolute/path/to/quant-mcp/.venv/bin/quant-mcp"
    }
  }
}
```

## Hosted (HTTP): bearer token required

Replace `YOUR-PROJECT.vercel.app` with your deployment URL, and keep the token out of the config file. Use an
environment variable when the client supports it.

Set the token in your shell first:

```bash
export QUANT_MCP_API_TOKEN="the-same-value-as-on-the-server"
```

**Claude Code**

```bash
claude mcp add --transport http quant https://YOUR-PROJECT.vercel.app/mcp \
  --header "Authorization: Bearer $QUANT_MCP_API_TOKEN"
```

**Generic JSON config** (for clients that accept remote servers with headers; the key names vary by client, so check
its documentation):

```json
{
  "mcpServers": {
    "quant": {
      "type": "http",
      "url": "https://YOUR-PROJECT.vercel.app/mcp",
      "headers": {
        "Authorization": "Bearer ${QUANT_MCP_API_TOKEN}"
      }
    }
  }
}
```

Some clients do not expand `${VAR}` in config files. In that case, paste the literal token, and do not commit the file.

## Checking the connection

```bash
curl https://YOUR-PROJECT.vercel.app/healthz
QUANT_MCP_API_TOKEN="$QUANT_MCP_API_TOKEN" python scripts/smoke_test.py https://YOUR-PROJECT.vercel.app
```

Responses from `/mcp`:

- `401` with `WWW-Authenticate: Bearer`: the header is missing, malformed, or the token is wrong.
- `503` with `auth_not_configured`: the server has no `QUANT_MCP_API_TOKEN` set.
- `429` with `Retry-After`: the per-client rate limit was hit.
