import asyncio
from unittest import mock

import pytest
from starlette.testclient import TestClient

from quant_mcp.http_app import BearerAuthMiddleware, BodyLimitMiddleware

TOKEN = "t" * 40
AUTH = {"Authorization": f"Bearer {TOKEN}"}

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
ACCEPT = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def _ok_app(scope, receive, send):
    while True:
        msg = await receive()
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _call(mw, body=b"{}", headers=None, path="/mcp"):
    """Drive an ASGI app directly and return the status code."""
    status = {}
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": "POST", "path": path, "headers": hdrs, "query_string": b""}
    sent = iter([{"type": "http.request", "body": body, "more_body": False}])

    async def receive():
        try:
            return next(sent)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]

    asyncio.run(mw(scope, receive, send))
    return status["code"]


def test_body_cap_by_streamed_size():
    mw = BodyLimitMiddleware(_ok_app, max_body=100)
    assert _call(mw, body=b"x" * 500) == 413
    assert _call(mw, body=b"x" * 50) == 200


def test_body_cap_by_declared_length():
    mw = BodyLimitMiddleware(_ok_app, max_body=100)
    assert _call(mw, headers={"Content-Length": "5000"}) == 413


def test_auth_accepts_correct_bearer_token():
    mw = BearerAuthMiddleware(_ok_app, token=TOKEN)
    assert _call(mw, headers=AUTH) == 200


def test_auth_rejects_missing_wrong_or_malformed_token():
    mw = BearerAuthMiddleware(_ok_app, token=TOKEN)
    assert _call(mw) == 401
    assert _call(mw, headers={"Authorization": "Bearer wrong"}) == 401
    assert _call(mw, headers={"Authorization": TOKEN}) == 401  # no scheme
    assert _call(mw, headers={"Authorization": f"Basic {TOKEN}"}) == 401


def test_auth_leaves_health_and_root_open():
    mw = BearerAuthMiddleware(_ok_app, token=TOKEN)
    assert _call(mw, path="/healthz") == 200
    assert _call(mw, path="/") == 200


def test_auth_fails_closed_without_configured_token():
    mw = BearerAuthMiddleware(_ok_app, token=None)
    assert _call(mw, headers=AUTH) == 503


def test_auth_anonymous_opt_in_skips_check():
    mw = BearerAuthMiddleware(_ok_app, token=None, allow_anonymous=True)
    assert _call(mw) == 200


@pytest.fixture(scope="module")
def live_client():
    """One real app per process: the SDK's session manager can only start once."""
    from quant_mcp import http_app

    with mock.patch.dict("os.environ", {"QUANT_MCP_API_TOKEN": TOKEN}, clear=False):
        app = http_app.create_app()
    with TestClient(app, base_url="http://localhost") as client:
        yield client


def test_integration_health(live_client):
    r = live_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_integration_mcp_rejects_missing_token(live_client):
    r = live_client.post("/mcp", json=INIT, headers=ACCEPT)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_integration_initialize_and_list_tools_with_token(live_client):
    r = live_client.post("/mcp", json=INIT, headers={**ACCEPT, **AUTH})
    assert r.status_code == 200
    listed = live_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        headers={**ACCEPT, **AUTH},
    )
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert {"black_scholes", "hrp_portfolio", "backtest_portfolio", "price_history"} <= names


def test_integration_root_describes_service(live_client):
    r = live_client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "quant-mcp"
    assert body["endpoints"]["mcp"] == "/mcp"
