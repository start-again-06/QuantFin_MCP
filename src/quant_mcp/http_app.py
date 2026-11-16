"""ASGI application for HTTP deployment (Vercel, containers, or uvicorn directly).

Routes:
  GET  /healthz   liveness probe (open)
  GET  /          service description (open)
  POST /mcp       MCP streamable-HTTP endpoint (requires a bearer token)

Protections:
  * /mcp requires "Authorization: Bearer <QUANT_MCP_API_TOKEN>". If the token is unset
    the endpoint fails closed (503). Set QUANT_MCP_ALLOW_ANONYMOUS=1 only if you
    protect the URL some other way.
  * Request bodies are capped (default 1 MiB) to bound CPU and memory per call.
  * /mcp is rate limited per client (default 60 requests per minute, per instance).
    Set QUANT_MCP_RATE_LIMIT_PER_MINUTE=0 to disable.
  * Market-data providers that spend paid quota are off unless the operator enables
    them (see quant_mcp.market_data).

The token is a shared secret for the whole deployment. Use platform-level rate limits
and budgets for a hard cap.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from quant_mcp.server import mcp

logger = logging.getLogger(__name__)

HEALTH_PATH = "/healthz"
ROOT_PATH = "/"
DEFAULT_MAX_BODY_BYTES = 1_048_576
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
MIN_TOKEN_LENGTH = 32
OPEN_PATHS = frozenset({HEALTH_PATH, ROOT_PATH})


class BodyTooLargeError(Exception):
    pass


async def _json(send: Send, status: int, body: dict, extra: list[tuple[bytes, bytes]] | None = None) -> None:
    payload = json.dumps(body).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())]
    headers += extra or []
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


class BodyLimitMiddleware:
    """Rejects request bodies above max_body bytes, by declared length or as they stream in."""

    def __init__(self, app: ASGIApp, max_body: int) -> None:
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body:
            await _json(send, 413, {"error": "payload_too_large", "max_bytes": self.max_body})
            return

        received = 0

        async def limited_receive() -> Any:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body:
                    raise BodyTooLargeError()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLargeError:
            await _json(send, 413, {"error": "payload_too_large", "max_bytes": self.max_body})


class BearerAuthMiddleware:
    """Requires "Authorization: Bearer <token>" on every path except OPEN_PATHS.

    Fails closed: if no token is configured and anonymous access is not explicitly
    allowed, protected paths return 503 rather than running unauthenticated.
    """

    def __init__(self, app: ASGIApp, token: str | None, allow_anonymous: bool = False) -> None:
        self.app = app
        self.token = token.encode("utf-8") if token else None
        self.allow_anonymous = allow_anonymous

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS or self.allow_anonymous:
            await self.app(scope, receive, send)
            return

        if self.token is None:
            await _json(send, 503, {"error": "auth_not_configured"})
            return

        header = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
        scheme, _, presented = header.strip().partition(" ")
        ok = scheme.lower() == "bearer" and hmac.compare_digest(presented.strip().encode("utf-8"), self.token)
        if not ok:
            await _json(
                send,
                401,
                {"error": "unauthorized"},
                extra=[(b"www-authenticate", b'Bearer realm="quant-mcp"')],
            )
            return
        await self.app(scope, receive, send)


class RateLimitMiddleware:
    """Best-effort per-client sliding-window limit on /mcp.

    State lives in this process only. On serverless hosts with many instances the
    effective limit is per instance, so this blunts bursts but is not a hard global
    quota. Use the platform's rate limiting for a hard limit.
    """

    def __init__(self, app: ASGIApp, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.per_minute = per_minute
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = 0.0

    def _client_key(self, scope: Scope) -> str:
        headers = dict(scope.get("headers") or [])
        forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or now - v[-1] > 60]:
            del self._hits[key]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == HEALTH_PATH or self.per_minute <= 0:
            await self.app(scope, receive, send)
            return

        now = self.clock()
        self._sweep(now)
        hits = self._hits[self._client_key(scope)]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            retry = max(1, int(60 - (now - hits[0])) + 1)
            await _json(
                send,
                429,
                {"error": "rate_limited", "retry_after_seconds": retry},
                extra=[(b"retry-after", str(retry).encode())],
            )
            return
        hits.append(now)
        await self.app(scope, receive, send)


async def healthz(request: Any) -> JSONResponse:
    from quant_mcp import __version__

    return JSONResponse({"status": "ok", "version": __version__})


async def index(request: Any) -> JSONResponse:
    from quant_mcp import __version__

    return JSONResponse(
        {
            "service": "quant-mcp",
            "version": __version__,
            "endpoints": {"health": HEALTH_PATH, "mcp": "/mcp"},
            "note": "This is an MCP endpoint. Connect an MCP client to /mcp.",
        }
    )


@lru_cache(maxsize=1)
def _mcp_asgi_app() -> Starlette:
    """The SDK keeps one session manager per FastMCP instance that can only start once,
    so the MCP app is built once per process and reused."""
    app = mcp.streamable_http_app()
    app.router.routes.append(Route(HEALTH_PATH, healthz, methods=["GET"]))
    app.router.routes.append(Route("/", index, methods=["GET"]))
    return app


def create_app() -> ASGIApp:
    """Build the production ASGI app. Reads configuration from the environment.

    The rate limiter sits outermost so that unauthenticated guessing is limited too.
    """
    max_body = int(os.environ.get("QUANT_MCP_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES))
    per_minute = int(os.environ.get("QUANT_MCP_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE))

    token = os.environ.get("QUANT_MCP_API_TOKEN", "").strip() or None
    if token is not None and len(token) < MIN_TOKEN_LENGTH:
        raise ValueError(f"QUANT_MCP_API_TOKEN must be at least {MIN_TOKEN_LENGTH} characters")
    allow_anonymous = os.environ.get("QUANT_MCP_ALLOW_ANONYMOUS", "").strip().lower() in {"1", "true", "yes"}
    if allow_anonymous:
        logger.warning("QUANT_MCP_ALLOW_ANONYMOUS is set: /mcp is reachable without a token")
    elif token is None:
        logger.warning("QUANT_MCP_API_TOKEN is not set: /mcp will return 503 until it is configured")

    limited = BodyLimitMiddleware(_mcp_asgi_app(), max_body=max_body)
    authed = BearerAuthMiddleware(limited, token=token, allow_anonymous=allow_anonymous)
    return RateLimitMiddleware(authed, per_minute=per_minute)
