"""Smoke-test a running quant-mcp HTTP deployment.

Usage:
  python scripts/smoke_test.py https://your-project.vercel.app

Set QUANT_MCP_API_TOKEN to the deployment's bearer token; /mcp requires it.

Checks: /healthz, MCP initialize, tools/list, and one real calculation
(Black-Scholes). Standard library only. Exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ACCEPT = "application/json, text/event-stream"


def _post(base: str, body: dict) -> tuple[int, dict | None]:
    headers = {"Content-Type": "application/json", "Accept": ACCEPT}
    token = os.environ.get("QUANT_MCP_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{base}/mcp", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    base = sys.argv[1].rstrip("/")
    failures = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")

    with urllib.request.urlopen(f"{base}/healthz", timeout=30) as resp:
        health = json.loads(resp.read())
    check("healthz", health.get("status") == "ok", f"version {health.get('version')}")

    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "smoke-test", "version": "1"},
        },
    }
    status, body = _post(base, init)
    check("initialize", status == 200 and body is not None and "result" in body, f"HTTP {status}")

    status, body = _post(base, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = (body or {}).get("result", {}).get("tools", [])
    check("tools/list", status == 200 and len(tools) >= 20, f"{len(tools)} tools")

    call = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "black_scholes",
            "arguments": {"spot": 100, "strike": 100, "time_years": 1, "rate": 0.05, "volatility": 0.2},
        },
    }
    status, body = _post(base, call)
    text = ""
    if body and body.get("result", {}).get("content"):
        text = body["result"]["content"][0].get("text", "")
    check("black_scholes calculation (expect ~10.4506)", status == 200 and "10.45" in text)

    print("\nAll checks passed." if failures == 0 else f"\n{failures} check(s) failed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
