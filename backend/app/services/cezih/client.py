from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.config import settings
from app.services.cezih.exceptions import (
    CezihConnectionError,
    CezihError,
    CezihFhirError,
    CezihTimeoutError,
)
from app.services.cezih.models import OperationOutcome
from app.services.cezih.oauth import get_oauth_token, invalidate_token

logger = logging.getLogger(__name__)

_FHIR_CONTENT_TYPE = "application/fhir+json"
_GATEWAY_PREFIX = "/services-router/gateway/"

# Services that live on the auxiliary port (9443 in test env).
# All other services use the primary port (8443 in test env).
_AUX_PORT_PREFIXES = (
    "terminology-services/",
    "mcsd/",
    "identifier-registry-services/",
    "notification-pull-service/",
    "notification-push-websocket/",
    "fhir/",
)


class CezihFhirClient:
    """Async HTTP client for CEZIH FHIR API calls.

    Handles: Bearer token injection, FHIR content types, retry with backoff,
    structured logging, and exception translation.
    """

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client
        self._base_url = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        self._aux_url = (settings.CEZIH_FHIR_AUX_URL or settings.CEZIH_FHIR_BASE_URL).rstrip("/")

    def _full_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        clean = path.lstrip("/")
        base = self._aux_url if any(clean.startswith(p) for p in _AUX_PORT_PREFIXES) else self._base_url
        return f"{base}{_GATEWAY_PREFIX}{path}"

    async def _attach_auth(self, headers: dict[str, str]) -> dict[str, str]:
        token = await get_oauth_token(client=self._client)
        headers["Authorization"] = f"Bearer {token}"
        return headers

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        timeout: int | None = None,
        _attempt: int = 0,
    ) -> dict:
        url = self._full_url(path)
        timeout = timeout or settings.CEZIH_TIMEOUT
        max_attempts = settings.CEZIH_RETRY_ATTEMPTS

        headers = {
            "Accept": _FHIR_CONTENT_TYPE,
            "Content-Type": _FHIR_CONTENT_TYPE,
        }
        headers = await self._attach_auth(headers)

        start = time.perf_counter()
        logger.info("CEZIH request: %s %s (attempt %d/%d)", method, url, _attempt + 1, max_attempts)

        try:
            response = await self._client.request(
                method, url, params=params, json=json_body, headers=headers, timeout=timeout,
            )
        except httpx.ConnectError as e:
            raise CezihConnectionError(f"Cannot connect to CEZIH at {url}. Is VPN connected?") from e
        except httpx.TimeoutException as e:
            raise CezihTimeoutError(f"CEZIH request timed out after {timeout}s: {method} {url}") from e

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("CEZIH response: %s %s -> %d (%.1fms)", method, url, response.status_code, duration_ms)

        # 401 — invalidate token and retry
        if response.status_code == 401 and _attempt < max_attempts - 1:
            logger.warning("CEZIH 401, invalidating token and retrying")
            invalidate_token()
            await asyncio.sleep(1.0 * (2 ** _attempt))
            return await self.request(
                method, path, params=params, json_body=json_body, timeout=timeout, _attempt=_attempt + 1,
            )

        # 5xx — retry with exponential backoff
        if response.status_code >= 500 and _attempt < max_attempts - 1:
            logger.warning("CEZIH %d, retrying (attempt %d/%d)", response.status_code, _attempt + 1, max_attempts)
            await asyncio.sleep(2.0 * (2 ** _attempt))
            return await self.request(
                method, path, params=params, json_body=json_body, timeout=timeout, _attempt=_attempt + 1,
            )

        # Parse response body
        try:
            body = response.json()
        except Exception:
            body = {}

        # Check for OperationOutcome errors (4xx and 5xx)
        if response.status_code >= 400:
            if body.get("resourceType") == "OperationOutcome":
                oo = OperationOutcome.model_validate(body)
                raise CezihFhirError(
                    f"FHIR error: {oo.first_error_message}",
                    status_code=response.status_code,
                    operation_outcome=body,
                )
            raise CezihFhirError(
                f"CEZIH HTTP {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )

        return body

    async def get(self, path: str, *, params: dict | None = None) -> dict:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json_body: dict | None = None) -> dict:
        return await self.request("POST", path, json_body=json_body)

    async def process_message(self, service_path: str, bundle: dict) -> dict:
        """POST a FHIR message Bundle via $process-message operation."""
        path = f"{service_path}/$process-message"
        return await self.post(path, json_body=bundle)

    async def health_check(self) -> bool:
        """Simple connectivity check."""
        try:
            await self.get("terminology-services/api/v1/CodeSystem", params={"_count": "1"})
            return True
        except CezihError:
            return False
