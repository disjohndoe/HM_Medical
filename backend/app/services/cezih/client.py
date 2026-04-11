from __future__ import annotations

import asyncio
import contextvars
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

# Context variable set by the dispatcher before calling service functions.
# Allows CezihFhirClient to route 8443 calls through the agent.
current_tenant_id: contextvars.ContextVar = contextvars.ContextVar("current_tenant_id", default=None)

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


def _extract_operation_outcome(bundle: dict) -> dict | None:
    """Extract OperationOutcome from a CEZIH response Bundle."""
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "OperationOutcome":
            return resource
    return None


class CezihFhirClient:
    """Async HTTP client for CEZIH FHIR API calls.

    Handles: Bearer token injection, FHIR content types, retry with backoff,
    structured logging, and exception translation.

    For port-8443 requests (clinical services requiring mTLS), routes through
    the local agent's native TLS stack if an agent is connected. Port-9443
    requests (reference services) go directly via httpx.
    """

    def __init__(self, http_client: httpx.AsyncClient, tenant_id=None) -> None:
        self._client = http_client
        self._tenant_id = tenant_id or current_tenant_id.get()
        self._base_url = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        if settings.CEZIH_FHIR_AUX_URL:
            self._aux_url = settings.CEZIH_FHIR_AUX_URL.rstrip("/")
        elif settings.CEZIH_FHIR_BASE_URL:
            logger.warning(
                "CEZIH_FHIR_AUX_URL not set, auxiliary services will use CEZIH_FHIR_BASE_URL (%s)",
                settings.CEZIH_FHIR_BASE_URL,
            )
            self._aux_url = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        else:
            raise CezihError("Ni CEZIH_FHIR_AUX_URL ni CEZIH_FHIR_BASE_URL nisu konfigurirani.")

    def _is_aux_service(self, path: str) -> bool:
        clean = path.lstrip("/")
        return any(clean.startswith(p) for p in _AUX_PORT_PREFIXES)

    def _full_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        clean = path.lstrip("/")
        base = self._aux_url if self._is_aux_service(path) else self._base_url
        return f"{base}{_GATEWAY_PREFIX}{clean}"

    async def _attach_auth(self, headers: dict[str, str]) -> dict[str, str]:
        token = await get_oauth_token(client=self._client, tenant_id=self._tenant_id)
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _should_use_agent(self, path: str) -> bool:
        """Check if this request should be routed through the agent.

        Server has no VPN — ALL CEZIH requests (both 8443 and 9443) must
        go through the agent when it is connected.
        """
        if not self._tenant_id:
            return False
        from app.services.agent_connection_manager import agent_manager
        return agent_manager.is_connected(self._tenant_id)

    async def _request_via_agent(
        self, method: str, url: str, headers: dict[str, str],
        params: dict | None, json_body: dict | None, timeout: int,
    ) -> dict:
        """Route request through the agent's native TLS for mTLS client cert."""
        import json as _json
        from app.services.agent_connection_manager import agent_manager

        # Append query params to URL
        if params:
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params, doseq=True)}"

        body_str = _json.dumps(json_body) if json_body else None

        logger.info("CEZIH request via agent: %s %s", method, url)
        if body_str:
            logger.info("CEZIH request body (%d chars): %s", len(body_str), body_str[:5000])
        start = time.perf_counter()

        try:
            result = await agent_manager.proxy_http_request(
                self._tenant_id,
                method=method, url=url, headers=headers,
                body=body_str, timeout=float(timeout),
            )
        except RuntimeError as e:
            raise CezihConnectionError(str(e)) from e

        duration_ms = (time.perf_counter() - start) * 1000

        if "error" in result:
            raise CezihConnectionError(f"Agent proxy error: {result['error']}")

        status_code = result.get("status_code", 0)
        logger.info("CEZIH response via agent: %s %s -> %d (%.1fms)", method, url, status_code, duration_ms)
        if status_code >= 400:
            logger.warning("CEZIH agent proxy error body: %s", result.get("body", "")[:3000])

        body_text = result.get("body", "")
        logger.info("CEZIH response body length: %d chars", len(body_text))
        try:
            body = _json.loads(body_text) if body_text else {}
        except Exception as parse_err:
            logger.error("Failed to parse agent proxy response as JSON: %s. Raw body (first 500 chars): %s", parse_err, body_text[:500])
            body = {}

        if status_code >= 400:
            if body.get("resourceType") == "OperationOutcome":
                oo = OperationOutcome.model_validate(body)
                raise CezihFhirError(
                    f"FHIR error: {oo.first_error_message}",
                    status_code=status_code,
                    operation_outcome=body,
                )
            # CEZIH returns response Bundles with nested OperationOutcome
            if body.get("resourceType") == "Bundle":
                oo = _extract_operation_outcome(body)
                if oo:
                    oo_model = OperationOutcome.model_validate(oo)
                    raise CezihFhirError(
                        f"FHIR error: {oo_model.first_error_message}",
                        status_code=status_code,
                        operation_outcome=oo,
                    )
            # Build a concise error — don't dump entire FHIR bundles into user-facing messages
            error_detail = ""
            if body.get("error"):
                error_detail = str(body["error"])[:500]
            elif body.get("resourceType") == "Bundle":
                error_detail = "CEZIH odbio zahtjev (nema OperationOutcome u odgovoru)"
            else:
                error_detail = body_text[:500]
            raise CezihFhirError(
                f"CEZIH HTTP {status_code}: {error_detail}",
                status_code=status_code,
            )

        return body

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

        # Route 8443 calls through agent if connected (for mTLS client cert)
        if self._should_use_agent(path):
            return await self._request_via_agent(method, url, headers, params, json_body, timeout)

        logger.info("CEZIH request: %s %s (attempt %d/%d)", method, url, _attempt + 1, max_attempts)
        if json_body:
            import json as _json_for_log
            logger.info("CEZIH request body (%d chars): %s", len(_json_for_log.dumps(json_body)), _json_for_log.dumps(json_body, ensure_ascii=False)[:5000])
        start = time.perf_counter()

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

    async def get(self, path: str, *, params: dict | None = None, timeout: int | None = None) -> dict:
        return await self.request("GET", path, params=params, timeout=timeout)

    async def post(self, path: str, *, json_body: dict | None = None) -> dict:
        return await self.request("POST", path, json_body=json_body)

    async def process_message(self, service_path: str, bundle: dict) -> dict:
        """POST a FHIR message Bundle via $process-message operation.

        Uses lenient error handling: CEZIH may return non-2xx status for
        successful $process-message calls that include informational
        OperationOutcome issues. We parse the response Bundle ourselves
        instead of relying on the generic status-code-based error handler.
        """
        path = f"{service_path}/$process-message"
        try:
            return await self.post(path, json_body=bundle)
        except CezihFhirError as e:
            # If the response is a Bundle with entries, it might be a valid
            # $process-message response despite the HTTP error status.
            # Return it for parse_message_response to evaluate.
            oo = e.operation_outcome or {}
            if oo.get("resourceType") == "Bundle" and oo.get("entry"):
                logger.info("process_message: returning error Bundle for parsing (status=%s)", e.status_code)
                return oo
            raise

    async def health_check(self) -> bool:
        """Quick connectivity check with short timeout."""
        try:
            await self.request("GET", "terminology-services/api/v1/CodeSystem", params={"_count": "1"}, timeout=5)
            return True
        except CezihError:
            return False
