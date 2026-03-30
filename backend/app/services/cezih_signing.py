from __future__ import annotations

import asyncio
import base64
import hashlib
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

        oauth_url = settings.CEZIH_SIGNING_OAUTH2_URL or settings.CEZIH_OAUTH2_URL
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
            response = await client.post(
                oauth_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=settings.CEZIH_TIMEOUT,
            )
            response.raise_for_status()
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

        body = response.json()
        global _signing_token_cache, _signing_token_expires_in, _signing_token_acquired_at
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
    """Sign a document via the CEZIH remote signing service.

    Sends a pre-computed document hash to the signing endpoint and
    returns the PKCS#7 / CMS signature.

    Architecture note (discovered 2026-03-27):
    - Public endpoint (certpubws.cezih.hr): Uses Apache mod_auth_openidc with
      browser-based session auth (authorization code flow). NOT suitable for
      direct API calls.
    - VPN-protected endpoint (certws2.cezih.hr): Accessible via VPN, accepts
      Bearer tokens from client_credentials grant. This is the primary path.
    - Public Keycloak (certpubsso.cezih.hr): Separate from VPN Keycloak
      (certsso2.cezih.hr). Accepts client_credentials with test credentials.

    The signing endpoint may also be available at the FHIR base URL through VPN:
    certws2.cezih.hr/services-router/gateway/extsigner/api/sign

    Returns dict with keys: success, signature, signing_algorithm,
    signed_at, document_id, raw_response.
    Raises CezihSigningError on failure.
    """
    signing_url = settings.CEZIH_SIGNING_URL
    if not signing_url:
        raise CezihSigningError(
            "CEZIH_SIGNING_URL not configured. Set it in .env for real signing.",
        )

    if isinstance(document_bytes, str):
        document_bytes = document_bytes.encode("utf-8")

    doc_hash = _compute_hash(document_bytes)
    url = f"{signing_url.rstrip('/')}/services-router/gateway/extsigner/api/sign"

    payload = {
        "hash": doc_hash,
        "hashAlgorithm": _DEFAULT_ALGORITHM,
    }
    if document_id:
        payload["documentId"] = document_id
    if signing_reason:
        payload["reason"] = signing_reason

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        token = await _get_signing_token(client)
        headers["Authorization"] = f"Bearer {token}"
    except CezihSigningError:
        raise
    except Exception as exc:
        logger.warning("CEZIH signing: could not obtain OAuth token — %s", exc)

    start = time.perf_counter()
    logger.info("CEZIH signing request: POST %s (hash=%.16s...)", url, doc_hash)

    try:
        response = await client.post(
            url,
            json=payload,
            headers=headers,
            timeout=settings.CEZIH_TIMEOUT,
        )
    except httpx.ConnectError as e:
        raise CezihSigningError(
            f"Cannot reach signing service at {url}. Is VPN connected for certws2?",
            signing_service_error=str(e),
        ) from e
    except httpx.TimeoutException as e:
        raise CezihSigningError(
            f"Signing request timed out after {settings.CEZIH_TIMEOUT}s",
            signing_service_error=str(e),
        ) from e

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "CEZIH signing response: %d (%.1fms)",
        response.status_code,
        duration_ms,
    )

    # Handle redirect (public endpoint returns 302 to login page)
    if response.status_code in (301, 302, 303, 307):
        location = response.headers.get("location", "")
        if "certpubsso" in location or "certsso2" in location:
            raise CezihSigningError(
                "Signing endpoint redirected to login page. "
                "The public endpoint (certpubws) requires browser-based auth. "
                "Use the VPN-protected endpoint (certws2) for API-based signing, "
                "or contact HZZO for the correct signing API access method.",
                signing_service_error=f"HTTP {response.status_code} redirect to {location[:100]}",
            )
        raise CezihSigningError(
            f"Signing endpoint returned unexpected redirect: HTTP {response.status_code} to {location[:100]}",
            signing_service_error=f"HTTP {response.status_code}",
        )

    try:
        body = response.json()
    except Exception:
        body = {}

    if response.status_code >= 400:
        error_detail = body.get("error") or body.get("message") or response.text[:500]
        raise CezihSigningError(
            f"Signing service returned HTTP {response.status_code}: {error_detail}",
            signing_service_error=error_detail,
        )

    # Extract signature from response — format TBD (adjust after real API test)
    signature = body.get("signature") or body.get("signedHash") or body.get("signatures", "")

    return {
        "success": True,
        "signature": signature,
        "signing_algorithm": _DEFAULT_ALGORITHM,
        "signed_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
        "raw_response": body,
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
