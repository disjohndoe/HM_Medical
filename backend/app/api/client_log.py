"""POST /api/client-log — relay frontend errors into backend structured logs."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["client-log"])

logger = logging.getLogger("app.client_errors")

# --- In-memory rate limiter: 5 requests per IP per minute ---

_rate_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT = 5
_RATE_WINDOW = 60.0


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    timestamps = _rate_store[ip]
    # Prune old entries
    _rate_store[ip] = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(_rate_store[ip]) >= _RATE_LIMIT:
        return True
    _rate_store[ip].append(now)
    return False


class ClientLogPayload(BaseModel):
    message: str
    stack: str | None = None
    url: str | None = None
    userAgent: str | None = None  # noqa: N815 - JS-side wire format
    request_id: str | None = None


@router.post("/client-log", status_code=204)
async def client_log(payload: ClientLogPayload, request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(ip):
        return

    extra: dict = {
        "client_ip": ip,
        "client_url": payload.url,
        "user_agent": payload.userAgent,
    }
    if payload.request_id:
        extra["client_request_id"] = payload.request_id
    if payload.stack:
        extra["stack"] = payload.stack

    logger.warning(payload.message, extra=extra)
