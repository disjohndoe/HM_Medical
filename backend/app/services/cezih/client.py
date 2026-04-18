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

# Context variables set by the dispatcher before calling service functions.
# - current_tenant_id: lets CezihFhirClient route 8443 calls through the agent.
# - current_user_id: lets message_builder resolve per-user signing preference.
# - current_db_session: lets message_builder look up the user without threading
#   db through every helper signature.
current_tenant_id: contextvars.ContextVar = contextvars.ContextVar("current_tenant_id", default=None)
current_user_id: contextvars.ContextVar = contextvars.ContextVar("current_user_id", default=None)
current_db_session: contextvars.ContextVar = contextvars.ContextVar("current_db_session", default=None)

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

    Routes ALL requests through the local agent (production server has no
    direct connectivity to CEZIH). Picks VPN or public hostnames based on
    the user's signing method:
    - smartcard → certws2.cezih.hr (VPN, mTLS)
    - extsigner → certpubws.cezih.hr (public, no VPN needed)
    """

    def __init__(self, http_client: httpx.AsyncClient, tenant_id=None) -> None:
        self._client = http_client
        self._tenant_id = tenant_id or current_tenant_id.get()
        self._signing_method: str | None = None

        # VPN URLs (smartcard path)
        self._vpn_base_url = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        if settings.CEZIH_FHIR_AUX_URL:
            self._vpn_aux_url = settings.CEZIH_FHIR_AUX_URL.rstrip("/")
        elif settings.CEZIH_FHIR_BASE_URL:
            logger.warning(
                "CEZIH_FHIR_AUX_URL not set, auxiliary services will use CEZIH_FHIR_BASE_URL (%s)",
                settings.CEZIH_FHIR_BASE_URL,
            )
            self._vpn_aux_url = settings.CEZIH_FHIR_BASE_URL.rstrip("/")
        else:
            raise CezihError("Ni CEZIH_FHIR_AUX_URL ni CEZIH_FHIR_BASE_URL nisu konfigurirani.")

        # Public URLs (extsigner path — no VPN needed)
        self._pub_base_url = (settings.CEZIH_FHIR_PUB_BASE_URL or self._vpn_base_url).rstrip("/")
        self._pub_aux_url = (settings.CEZIH_FHIR_PUB_AUX_URL or self._vpn_aux_url).rstrip("/")

    async def _get_signing_method(self) -> str:
        if self._signing_method is not None:
            return self._signing_method
        user_id = current_user_id.get()
        db = current_db_session.get()
        if user_id and db:
            from sqlalchemy import select
            from app.models.user import User
            try:
                method = await db.scalar(
                    select(User.cezih_signing_method).where(User.id == user_id)
                )
                self._signing_method = method or settings.CEZIH_SIGNING_METHOD
            except Exception:
                logger.warning("Could not resolve signing method from DB, using default")
                self._signing_method = settings.CEZIH_SIGNING_METHOD
        else:
            self._signing_method = settings.CEZIH_SIGNING_METHOD
        logger.info("CEZIH client using signing method: %s", self._signing_method)
        return self._signing_method

    def _is_extsigner(self, signing_method: str) -> bool:
        return signing_method == "extsigner"

    def _is_aux_service(self, path: str) -> bool:
        clean = path.lstrip("/")
        return any(clean.startswith(p) for p in _AUX_PORT_PREFIXES)

    def _full_url(self, path: str, signing_method: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        clean = path.lstrip("/")
        is_aux = self._is_aux_service(path)
        if self._is_extsigner(signing_method):
            base = self._pub_aux_url if is_aux else self._pub_base_url
        else:
            base = self._vpn_aux_url if is_aux else self._vpn_base_url
        return f"{base}{_GATEWAY_PREFIX}{clean}"

    def _get_oauth2_url(self, signing_method: str) -> str:
        if self._is_extsigner(signing_method) and settings.CEZIH_SIGNING_OAUTH2_URL:
            return settings.CEZIH_SIGNING_OAUTH2_URL
        return settings.CEZIH_OAUTH2_URL

    async def _attach_auth(self, headers: dict[str, str], *, oauth2_url: str) -> dict[str, str]:
        token = await get_oauth_token(
            client=self._client, tenant_id=self._tenant_id, oauth2_url=oauth2_url,
        )
        headers["Authorization"] = f"Bearer {token}"
        return headers

    def _should_use_agent(self, path: str) -> bool:
        """Check if this request should be routed through the agent.

        Server has no direct connectivity to CEZIH — ALL requests must
        go through the agent when it is connected.
        """
        if not self._tenant_id:
            return False
        from app.services.agent_connection_manager import agent_manager
        return agent_manager.is_connected(self._tenant_id)

    async def _request_via_agent(
        self, method: str, url: str, headers: dict[str, str],
        params: dict | None, json_body: dict | list | None, timeout: int,
    ) -> dict | bytes:
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
        body_bytes = result.get("body_bytes")  # Agent sends binary as base64
        logger.info("CEZIH response body length: %d chars", len(body_text))

        # Binary response: agent sets body_bytes (base64) and leaves body empty
        if body_bytes and status_code < 400:
            import base64
            decoded = base64.b64decode(body_bytes)
            size = len(decoded)
            is_pdf = decoded.startswith(b"%PDF")
            preview = decoded[:200] if size > 0 else b""
            logger.info(
                "CEZIH binary response: %d bytes, is_pdf=%s, preview=%r",
                size, is_pdf, preview,
            )
            return decoded

        try:
            body = _json.loads(body_text) if body_text else {}
        except Exception as json_err:
            if status_code < 400:
                logger.warning(
                    "CEZIH agent response is not valid JSON (status=%d, len=%d): %s",
                    status_code, len(body_text), str(json_err)[:200],
                )
                return body_text.encode("utf-8") if body_text else b""
            logger.warning(
                "CEZIH agent error response not parseable as JSON (status=%d): %.500s",
                status_code, body_text,
            )
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
                oo_dict = _extract_operation_outcome(body)
                if oo_dict:
                    oo_model = OperationOutcome.model_validate(oo_dict)
                    raise CezihFhirError(
                        f"FHIR error: {oo_model.first_error_message}",
                        status_code=status_code,
                        operation_outcome=oo_dict,
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
        json_body: dict | list | None = None,
        timeout: int | None = None,
        accept: str | None = None,
        content_type: str | None = None,
        _attempt: int = 0,
    ) -> dict | bytes:
        signing_method = await self._get_signing_method()
        url = self._full_url(path, signing_method)
        oauth2_url = self._get_oauth2_url(signing_method)
        timeout = timeout or settings.CEZIH_TIMEOUT
        max_attempts = settings.CEZIH_RETRY_ATTEMPTS

        headers = {
            "Accept": accept or _FHIR_CONTENT_TYPE,
            "Content-Type": content_type or _FHIR_CONTENT_TYPE,
        }
        headers = await self._attach_auth(headers, oauth2_url=oauth2_url)

        # Route through agent (production server has no direct CEZIH connectivity)
        if self._should_use_agent(path):
            result = await self._request_via_agent(method, url, headers, params, json_body, timeout)
            # Binary responses (bytes) are expected for ITI-68 document retrieval when accept="*/*"
            if isinstance(result, bytes):
                if accept == "*/*":
                    return result  # Return bytes for document downloads
                raise CezihError("Neočekivani binarni odgovor od agenta (koristiti accept='*/*' za dokumente).")
            return result

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
            invalidate_token(oauth2_url)
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

    async def get(self, path: str, *, params: dict | None = None, timeout: int | None = None, accept: str | None = None) -> dict | bytes:
        return await self.request("GET", path, params=params, timeout=timeout, accept=accept)

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
