import asyncio
import os
from unittest import mock

import pytest

from quant_mcp import market_data
from quant_mcp.http_app import RateLimitMiddleware


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _status(mw, ip="1.2.3.4", path="/mcp", headers=None):
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": hdrs,
        "client": (ip, 1234),
        "query_string": b"",
    }
    out = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            out["status"] = message["status"]
            out["headers"] = dict(message["headers"])

    asyncio.run(mw(scope, receive, send))
    return out


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_rate_limit_blocks_after_limit_and_reports_retry_after():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=3, clock=clock)
    assert [_status(mw)["status"] for _ in range(3)] == [200, 200, 200]
    blocked = _status(mw)
    assert blocked["status"] == 429
    assert int(blocked["headers"][b"retry-after"]) >= 1


def test_rate_limit_recovers_after_window():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=2, clock=clock)
    _status(mw)
    _status(mw)
    assert _status(mw)["status"] == 429
    clock.t += 61
    assert _status(mw)["status"] == 200


def test_rate_limit_is_per_client():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=1, clock=clock)
    assert _status(mw, ip="10.0.0.1")["status"] == 200
    assert _status(mw, ip="10.0.0.1")["status"] == 429
    assert _status(mw, ip="10.0.0.2")["status"] == 200


def test_rate_limit_uses_first_forwarded_address():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=1, clock=clock)
    h = {"x-forwarded-for": "203.0.113.5, 10.1.1.1"}
    assert _status(mw, ip="10.1.1.1", headers=h)["status"] == 200
    assert _status(mw, ip="10.1.1.2", headers=h)["status"] == 429


def test_health_endpoint_is_never_limited():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=1, clock=clock)
    for _ in range(5):
        assert _status(mw, path="/healthz")["status"] == 200


def test_zero_disables_rate_limit():
    clock = FakeClock()
    mw = RateLimitMiddleware(_ok, per_minute=0, clock=clock)
    for _ in range(20):
        assert _status(mw)["status"] == 200


def test_alphavantage_disabled_by_default():
    with mock.patch.dict(os.environ, {"ALPHAVANTAGE_API_KEY": "K"}, clear=False):
        os.environ.pop("QUANT_MCP_ENABLED_PROVIDERS", None)
        assert market_data.enabled_providers() == {"yahoo"}
        with pytest.raises(ValueError, match="not enabled"):
            market_data.price_history("IBM", provider="alphavantage")


def test_enabling_alphavantage_explicitly(monkeypatch):
    monkeypatch.setenv("QUANT_MCP_ENABLED_PROVIDERS", "yahoo,alphavantage")
    assert market_data.enabled_providers() == {"yahoo", "alphavantage"}


def test_unknown_providers_in_config_are_ignored(monkeypatch):
    monkeypatch.setenv("QUANT_MCP_ENABLED_PROVIDERS", "bloomberg,alphavantage")
    assert market_data.enabled_providers() == {"alphavantage"}
