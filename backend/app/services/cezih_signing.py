from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.services.cezih.exceptions import CezihSigningError

logger = logging.getLogger(__name__)

_DEFAULT_ALGORITHM = "SHA-256"

# Separate token cache for signing (uses certpubsso, not certsso2)
_signing_token_cache: str | None = None
_signing_token_acquired_at: float = 0.0
_signing_token_expires_in: int = 300
_signing_lock = asyncio.Lock()


def _compute_hash(data: bytes | str, *, algorithm: str = _DEFAULT_ALGORITHM) -> str:
    """Compute a hash of *data* and return it base64-encoded.

    Used to prepare the document hash for remote signing.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    if algorithm == "SHA-256":
        digest = hashlib.sha256(data).digest()
    elif algorithm == "SHA-384":
        digest = hashlib.sha384(data).digest()
    elif algorithm == "SHA-512":
        digest = hashlib.sha512(data).digest()
    else:
        raise CezihSigningError(f"Unsupported hash algorithm: {algorithm}")
    return base64.b64encode(digest).decode("ascii")


def _should_use_agent() -> bool:
    """Check if signing requests should be routed through the agent.

    Server has no VPN — ALL CEZIH requests (including signing) must
    go through the agent when it is connected.
    """
    from app.services.cezih.client import current_tenant_id
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        return False
    from app.services.agent_connection_manager import agent_manager
    return agent_manager.is_connected(tenant_id)


async def _request_via_agent(
    method: str, url: str, headers: dict[str, str],
    form_data: dict | None, json_body: dict | None, timeout: int,
    *, raw_body: str | None = None,
) -> dict:
    """Route HTTP request through the agent for CEZIH connectivity."""
    from app.services.agent_connection_manager import agent_manager
    from app.services.cezih.client import current_tenant_id

    tenant_id = current_tenant_id.get()
    if not tenant_id:
        raise CezihSigningError("No tenant context - cannot route through agent")

    # Prepare body
    if raw_body is not None:
        body = raw_body
        # Content-Type should be set by caller
    elif form_data:
        body = "&".join(f"{k}={v}" for k, v in form_data.items())
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_body:
        body = json.dumps(json_body)
        headers["Content-Type"] = "application/json"
    else:
        body = None

    logger.info("CEZIH signing request via agent: %s %s", method, url)
    if body:
        logger.info("CEZIH signing request body (%d chars): %s", len(body), body[:500])
    start = time.perf_counter()

    try:
        result = await agent_manager.proxy_http_request(
            tenant_id,
            method=method, url=url, headers=headers,
            body=body, timeout=float(timeout),
        )
    except RuntimeError as e:
        raise CezihSigningError(f"Agent proxy error: {e}") from e

    duration_ms = (time.perf_counter() - start) * 1000

    if "error" in result:
        raise CezihSigningError(f"Agent proxy error: {result['error']}")

    status_code = result.get("status_code", 0)
    logger.info("CEZIH signing response via agent: %s %s -> %d (%.1fms)", method, url, status_code, duration_ms)

    # Raise error for 4xx/5xx responses
    if status_code >= 400:
        body_text = result.get("body", "")
        logger.warning("CEZIH signing error body: %s", body_text[:3000])

        # Try to parse error message from CEZIH response
        try:
            error_body = json.loads(body_text) if body_text else {}
            error_msg = error_body.get("error", error_body.get("message", f"HTTP {status_code}"))
        except:
            error_msg = f"HTTP {status_code}"

        raise CezihSigningError(
            f"Agent request failed: {error_msg}",
            signing_service_error=body_text[:500],
        )

    body_text = result.get("body", "")
    if not body_text:
        return {"status_code": status_code}

    try:
        parsed = json.loads(body_text) if body_text else {}
        parsed["status_code"] = status_code  # Include status code in response
        return parsed
    except Exception as parse_err:
        logger.error("Failed to parse signing response as JSON: %s. Raw body (first 500 chars): %s", parse_err, body_text[:500])
        raise CezihSigningError(f"Failed to parse response: {parse_err}") from parse_err


async def _get_signing_token(client: httpx.AsyncClient) -> str:
    """Get an OAuth2 token for the signing service.

    Uses the public Keycloak (certpubsso.cezih.hr) which accepts
    client_credentials grant and is reachable without VPN.

    Falls back to the main CEZIH OAuth2 URL if signing-specific one
    is not configured.
    """
    global _signing_token_cache, _signing_token_acquired_at, _signing_token_expires_in

    import time as _time

    # Check cache (with 30s buffer)
    if _signing_token_cache and _signing_token_expires_in:
        if (_time.monotonic() - _signing_token_acquired_at) < (_signing_token_expires_in - 30):
            assert _signing_token_cache is not None
            return _signing_token_cache

    async with _signing_lock:
        if _signing_token_cache and _signing_token_expires_in:
            if (_time.monotonic() - _signing_token_acquired_at) < (_signing_token_expires_in - 30):
                assert _signing_token_cache is not None
                return _signing_token_cache

        oauth_url = settings.CEZIH_SIGNING_OAUTH2_URL
        if not oauth_url:
            oauth_url = settings.CEZIH_OAUTH2_URL
            if oauth_url:
                logger.warning(
                    "CEZIH_SIGNING_OAUTH2_URL not set, falling back to CEZIH_OAUTH2_URL (%s)",
                    oauth_url,
                )
        if not oauth_url or not settings.CEZIH_CLIENT_ID:
            raise CezihSigningError(
                "Signing OAuth2 URL and Client ID must be configured. "
                "Set CEZIH_SIGNING_OAUTH2_URL (or CEZIH_OAUTH2_URL) and CEZIH_CLIENT_ID.",
            )

        token_data = {
            "grant_type": "client_credentials",
            "client_id": settings.CEZIH_CLIENT_ID,
            "client_secret": settings.CEZIH_CLIENT_SECRET,
        }

        try:
            logger.info("CEZIH signing auth: fetching token from %s", oauth_url)

            # Route through agent if connected (server has no VPN)
            if _should_use_agent():
                body = await _request_via_agent(
                    method="POST",
                    url=oauth_url,
                    headers={},
                    form_data=token_data,
                    json_body=None,
                    timeout=settings.CEZIH_TIMEOUT,
                )
                # _request_via_agent raises CezihSigningError for 4xx/5xx
                if "error" in body:
                    raise CezihSigningError(
                        f"Signing OAuth2 token request failed: {body.get('error_description', body.get('error', 'Unknown error'))}",
                    )
            else:
                # Direct request (only works from local machine with VPN)
                response = await client.post(
                    oauth_url,
                    data=token_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=settings.CEZIH_TIMEOUT,
                )
                response.raise_for_status()
                body = response.json()
        except CezihSigningError:
            raise
        except httpx.ConnectError as e:
            raise CezihSigningError(
                f"Cannot connect to signing OAuth2 server at {oauth_url}",
            ) from e
        except httpx.TimeoutException as e:
            raise CezihSigningError(
                f"Signing OAuth2 token request timed out after {settings.CEZIH_TIMEOUT}s",
            ) from e
        except httpx.HTTPStatusError as e:
            raise CezihSigningError(
                f"Signing OAuth2 token request failed: HTTP {e.response.status_code} - {e.response.text[:200]}",
            ) from e
        except Exception as e:
            raise CezihSigningError(
                f"Signing OAuth2 token request failed: {e}",
            ) from e
        _signing_token_cache = body["access_token"]
        _signing_token_expires_in = body.get("expires_in", 300)
        _signing_token_acquired_at = _time.monotonic()

        logger.info("CEZIH signing auth: token acquired (expires_in=%ds)", _signing_token_expires_in)
        assert _signing_token_cache is not None
        return _signing_token_cache


def invalidate_signing_token() -> None:
    """Force signing token refresh on next request."""
    global _signing_token_cache, _signing_token_acquired_at, _signing_token_expires_in
    _signing_token_cache = None
    _signing_token_acquired_at = 0.0


async def sign_document(
    client: httpx.AsyncClient,
    document_bytes: bytes | str,
    *,
    document_id: str | None = None,
    signing_reason: str = "CEZIH clinical document",
) -> dict:
    """Create a placeholder JWS signature for the document.

    TEMPORARY: Bypasses extsigner API (unknown request format) to test
    whether the FHIR Bundle structure is accepted by CEZIH.
    CEZIH will reject the signature, but the error will tell us if the
    Bundle format itself is correct.

    TODO: Replace with real signing once extsigner API format is known,
    or implement local smart card signing in the agent.
    """
    if isinstance(document_bytes, str):
        document_bytes = document_bytes.encode("utf-8")

    doc_hash = _compute_hash(document_bytes)

    # Create a JWS-like placeholder matching the structure from
    # the Simplifier example: base64url(header) + base64url(payload) + dummy_sig
    import base64 as _b64

    # JWS header — RS256, placeholder kid
    jws_header = '{"kid":"placeholder-pending-extsigner","alg":"RS256"}'
    header_b64 = _b64.urlsafe_b64encode(jws_header.encode()).decode().rstrip("=")

    # JWS payload — the Bundle JSON (without signature field)
    payload_b64 = _b64.urlsafe_b64encode(document_bytes).decode().rstrip("=")

    # Dummy signature bytes (not cryptographically valid)
    dummy_sig = _b64.urlsafe_b64encode(b"PLACEHOLDER_SIGNATURE_FOR_BUNDLE_FORMAT_TEST").decode().rstrip("=")

    # JWS Compact Serialization: header.payload.signature
    jws = f"{header_b64}.{payload_b64}.{dummy_sig}"

    logger.warning(
        "CEZIH signing: using PLACEHOLDER signature (extsigner API format unknown). "
        "Bundle hash=%.16s, JWS length=%d. CEZIH will reject this — testing Bundle format only.",
        doc_hash, len(jws),
    )

    return {
        "success": True,
        "signature": jws,
        "signing_algorithm": _DEFAULT_ALGORITHM,
        "signed_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
        "raw_response": {"placeholder": True},
    }


async def sign_health_check(client: httpx.AsyncClient) -> dict:
    """Check whether the remote signing endpoint is reachable and auth works."""
    signing_url = settings.CEZIH_SIGNING_URL
    if not signing_url:
        return {"reachable": False, "reason": "CEZIH_SIGNING_URL not configured"}

    url = f"{signing_url.rstrip('/')}/services-router/gateway/extsigner/api/sign"

    # 1. Check DNS/connectivity
    try:
        response = await client.get(url, timeout=10, follow_redirects=False)
    except httpx.ConnectError:
        return {
            "reachable": True, "auth_works": False,
            "reason": "Connected but needs VPN/session auth",
        }
    except httpx.TimeoutException:
        return {"reachable": False, "reason": "Connection timed out"}
    except Exception as e:
        return {"reachable": False, "reason": str(e)}

    # 2. Check auth flow (public endpoint returns 302 to login)
    if response.status_code in (301, 302, 303, 307):
        return {
            "reachable": True,
            "auth_works": False,
            "reason": "Endpoint requires browser-based session auth (authorization code flow). "
                     "Direct API access needs VPN-protected endpoint (certws2).",
            "status_code": response.status_code,
        }

    # 3. Check for errors vs success
    if response.status_code >= 400:
        return {
            "reachable": True,
            "auth_works": False,
            "reason": f"HTTP {response.status_code}",
            "status_code": response.status_code,
        }

    return {"reachable": True, "auth_works": True, "reason": None, "status_code": response.status_code}
