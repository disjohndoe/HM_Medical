from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

import httpx

from app.config import settings
from app.services.cezih.exceptions import CezihAuthError
from app.services.cezih.models import OAuth2TokenResponse

logger = logging.getLogger(__name__)

_FAILURE_COOLDOWN = 60.0


@dataclass
class _TokenSlot:
    token: OAuth2TokenResponse | None = None
    acquired_at: float = 0.0
    last_failure_at: float = 0.0

    def is_valid(self) -> bool:
        if self.token is None:
            return False
        buffer = 30
        return (time.monotonic() - self.acquired_at) < (self.token.expires_in - buffer)

    def is_cooling_down(self) -> bool:
        return bool(self.last_failure_at and (time.monotonic() - self.last_failure_at) < _FAILURE_COOLDOWN)


_slots: dict[str, _TokenSlot] = {}
_lock = asyncio.Lock()


def _slot(url: str) -> _TokenSlot:
    if url not in _slots:
        _slots[url] = _TokenSlot()
    return _slots[url]


async def get_oauth_token(
    *,
    client: httpx.AsyncClient,
    tenant_id: UUID | None = None,
    oauth2_url: str | None = None,
) -> str:
    url = oauth2_url or settings.CEZIH_OAUTH2_URL
    s = _slot(url)

    if s.is_valid():
        return s.token.access_token  # type: ignore[union-attr]

    if s.is_cooling_down():
        raise CezihAuthError("CEZIH OAuth2 recently failed, waiting before retry")

    async with _lock:
        s = _slot(url)
        if s.is_valid():
            return s.token.access_token  # type: ignore[union-attr]
        if s.is_cooling_down():
            raise CezihAuthError("CEZIH OAuth2 recently failed, waiting before retry")
        return await _fetch_new_token(client, tenant_id=tenant_id, oauth2_url=url)


async def _fetch_via_agent(tenant_id: UUID, oauth2_url: str) -> str:
    from app.services.agent_connection_manager import agent_manager

    s = _slot(oauth2_url)

    token_data = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.CEZIH_CLIENT_ID,
            "client_secret": settings.CEZIH_CLIENT_SECRET,
        }
    )

    logger.info("CEZIH OAuth2: fetching token via agent from %s", oauth2_url)
    try:
        result = await agent_manager.proxy_http_request(
            tenant_id,
            method="POST",
            url=oauth2_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=token_data,
            timeout=15.0,
        )
    except RuntimeError as e:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"OAuth2 via agent failed: {e}") from e

    if "error" in result:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"OAuth2 via agent error: {result['error']}")

    status_code = result.get("status_code", 0)
    body_text = result.get("body", "")

    if status_code >= 400:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"OAuth2 via agent HTTP {status_code}: {body_text[:200]}")

    try:
        token_response = OAuth2TokenResponse.model_validate_json(body_text)
    except Exception as e:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"OAuth2 via agent: invalid token response: {body_text[:200]}") from e

    s.token = token_response
    s.acquired_at = time.monotonic()
    s.last_failure_at = 0.0

    logger.info("CEZIH OAuth2: token acquired via agent (expires_in=%ds)", token_response.expires_in)
    return token_response.access_token


async def _fetch_new_token(
    client: httpx.AsyncClient,
    *,
    tenant_id: UUID | None = None,
    oauth2_url: str,
) -> str:
    s = _slot(oauth2_url)

    if not oauth2_url or not settings.CEZIH_CLIENT_ID:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError("CEZIH OAuth2 URL and Client ID must be configured")

    if tenant_id:
        from app.services.agent_connection_manager import agent_manager

        if agent_manager.is_connected(tenant_id):
            return await _fetch_via_agent(tenant_id, oauth2_url)

    token_data = {
        "grant_type": "client_credentials",
        "client_id": settings.CEZIH_CLIENT_ID,
        "client_secret": settings.CEZIH_CLIENT_SECRET,
    }

    try:
        logger.info("CEZIH OAuth2: fetching token from %s", oauth2_url)
        response = await client.post(
            oauth2_url,
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=settings.CEZIH_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.ConnectError as e:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"Cannot connect to OAuth2 server at {oauth2_url}. Is VPN connected?") from e
    except httpx.TimeoutException as e:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(f"OAuth2 token request timed out after {settings.CEZIH_TIMEOUT}s") from e
    except httpx.HTTPStatusError as e:
        s.last_failure_at = time.monotonic()
        raise CezihAuthError(
            f"OAuth2 token request failed: HTTP {e.response.status_code} - {e.response.text[:200]}"
        ) from e

    token_response = OAuth2TokenResponse.model_validate_json(response.text)
    s.token = token_response
    s.acquired_at = time.monotonic()
    s.last_failure_at = 0.0

    logger.info("CEZIH OAuth2: token acquired (expires_in=%ds)", token_response.expires_in)
    return token_response.access_token


def invalidate_token(oauth2_url: str | None = None) -> None:
    """Force token refresh on next request (e.g. after 401 response)."""
    if oauth2_url:
        s = _slot(oauth2_url)
        s.token = None
        s.acquired_at = 0.0
        s.last_failure_at = 0.0
    else:
        for s in _slots.values():
            s.token = None
            s.acquired_at = 0.0
            s.last_failure_at = 0.0
