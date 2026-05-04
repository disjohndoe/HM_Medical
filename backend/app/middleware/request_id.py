"""Pure ASGI middleware that assigns a correlation ID to every request."""

from __future__ import annotations

import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx


class RequestIdMiddleware:
    """Generate (or accept forwarded) X-Request-ID and store in ContextVar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Accept forwarded ID from upstream proxy, or generate new
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-request-id", b"").decode("utf-8", errors="ignore").strip()
        rid = forwarded if forwarded else uuid.uuid4().hex[:16]

        token = request_id_ctx.set(rid)
        try:
            async def send_with_header(message: Message) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-request-id", rid.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_header)
        finally:
            request_id_ctx.reset(token)
