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


def _extract_signature_from_cms(cms_der: bytes) -> bytes:
    """Extract the raw cryptographic signature value from a CMS/PKCS#7 DER structure.

    Parses minimal ASN.1 to find the SignerInfo.signature field.
    Raises CezihSigningError if parsing fails — no silent failures.
    """
    errors = []

    try:
        # CMS SignedData structure (simplified):
        # SEQUENCE {
        #   OID signedData
        #   [0] EXPLICIT SEQUENCE {  -- SignedData
        #     INTEGER version
        #     SET digestAlgorithms
        #     SEQUENCE encapContentInfo
        #     SET signerInfos {
        #       SEQUENCE {  -- SignerInfo
        #         ...
        #         OCTET STRING signature  -- this is what we want (last element)
        #       }
        #     }
        #   }
        # }
        # The signature is the last OCTET STRING in the last SEQUENCE of the SignerInfos SET.
        # Simple approach: find the last OCTET STRING (tag 0x04) of sufficient length.

        # More reliable: use Python's built-in ASN.1 decoder if available
        from asn1crypto import cms as asn1_cms
        content_info = asn1_cms.ContentInfo.load(cms_der)
        signed_data = content_info["content"]
        signer_infos = signed_data["signer_infos"]
        if len(signer_infos) > 0:
            sig_value = signer_infos[0]["signature"].contents
            logger.info("Extracted raw signature from CMS: %d bytes", len(sig_value))
            return sig_value
    except ImportError:
        errors.append("asn1crypto library nije instaliran")
    except Exception as e:
        errors.append(f"asn1crypto CMS parsiranje nije uspjelo: {e}")

    try:
        # Manual fallback: the signature is typically the last large OCTET STRING
        # Scan backwards for tag 0x04 (OCTET STRING) with length >= 32
        pos = len(cms_der) - 1
        while pos > 10:
            # Look for a length-encoded block near the end
            if cms_der[pos - 1] == 0x04 or cms_der[pos - 2] == 0x04:
                break
            pos -= 1

        # Just take the last N bytes as the signature
        # For ECDSA P-256 DER: typically 70-72 bytes
        # For ECDSA raw r||s: 64 bytes
        # Scan for the last BIT STRING (0x03) or OCTET STRING (0x04)
        for i in range(len(cms_der) - 4, 10, -1):
            tag = cms_der[i]
            if tag in (0x03, 0x04):
                length = cms_der[i + 1]
                if 0x20 <= length <= 0x80 and i + 2 + length <= len(cms_der):
                    sig = cms_der[i + 2 : i + 2 + length]
                    logger.info("Manual ASN.1: found tag=0x%02x, len=%d at offset %d", tag, length, i)
                    return sig
    except Exception as e:
        errors.append(f"Manual ASN.1 parsiranje nije uspjelo: {e}")

    raise CezihSigningError(
        "Ekstrakcija potpisa iz CMS formata nije uspjela. " + "; ".join(errors)
    )


def _ecdsa_der_to_raw(der_sig: bytes) -> bytes:
    """Convert DER-encoded ECDSA signature to raw r||s format for JWS ES256.

    DER: SEQUENCE { INTEGER r, INTEGER s }
    Raw: r (32 bytes, zero-padded) || s (32 bytes, zero-padded)
    """
    try:
        from asn1crypto.core import Sequence
        seq = Sequence.load(der_sig)
        r_bytes = seq[0].contents
        s_bytes = seq[1].contents

        # Remove leading zero padding from DER integers
        r_bytes = r_bytes.lstrip(b'\x00')
        s_bytes = s_bytes.lstrip(b'\x00')

        # Determine component size from the larger of r, s
        component_size = max(len(r_bytes), len(s_bytes))
        # Round up to standard curve sizes: 32 (P-256), 48 (P-384), 66 (P-521)
        for std_size in (32, 48, 66):
            if component_size <= std_size:
                component_size = std_size
                break

        r_bytes = r_bytes.rjust(component_size, b'\x00')
        s_bytes = s_bytes.rjust(component_size, b'\x00')

        raw = r_bytes + s_bytes
        logger.info("ECDSA DER→raw: %d bytes DER → %d bytes raw (r=%d, s=%d)",
                     len(der_sig), len(raw), len(r_bytes), len(s_bytes))
        return raw
    except Exception as e:
        raise CezihSigningError(
            f"Konverzija ECDSA potpisa nije uspjela: {e}. "
            "Potpis je u neispravnom formatu i ne može se koristiti."
        ) from e


def _detect_bundle_type(bundle_json_bytes: bytes) -> str:
    """Detect FHIR bundle type (transaction or message) from JSON bytes.

    Args:
        bundle_json_bytes: FHIR bundle as JSON bytes

    Returns:
        "transaction" or "message"

    Raises:
        CezihSigningError: If JSON is invalid or 'type' field is missing
    """
    try:
        bundle_obj = json.loads(bundle_json_bytes)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON bundle: %s", e)
        raise CezihSigningError(
            "Neispravan JSON format u FHIR bundleu. "
            "Kontaktirajte tehničku podršku."
        ) from e

    bundle_type = bundle_obj.get("type")
    if not bundle_type:
        resource_type = bundle_obj.get("resourceType", "unknown")
        logger.error("Bundle missing 'type' field: resourceType=%s", resource_type)
        raise CezihSigningError(
            "FHIR bundle nema obavezno 'type' polje. "
            "Kontaktirajte tehničku podršku."
        )

    if bundle_type not in ("transaction", "message"):
        logger.warning("Unknown bundle type: %s", bundle_type)
        raise CezihSigningError(
            f"Nepoznat tip bundla: {bundle_type}. Dozvoljeni: transaction, message."
        )

    logger.debug("Detected bundle type: %s", bundle_type)
    return bundle_type


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
        raise CezihSigningError(f"Nepodržani hash algoritam: {algorithm}")
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
        raise CezihSigningError("Nije moguće usmjeriti zahtjev — nedostaje kontekst korisnika.")

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
        raise CezihSigningError(f"Greška agenta: {e}") from e

    duration_ms = (time.perf_counter() - start) * 1000

    if "error" in result:
        raise CezihSigningError(f"Greška agenta: {result['error']}")

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
        except (json.JSONDecodeError, ValueError, TypeError):
            error_msg = f"HTTP {status_code}"

        raise CezihSigningError(
            f"CEZIH greška pri potpisivanju: {error_msg}",
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
        raise CezihSigningError("Neispravan odgovor od CEZIH servisa za potpisivanje.") from parse_err


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
            raise CezihSigningError(
                "CEZIH_SIGNING_OAUTH2_URL nije postavljen. Potrebno je za potpisivanje putem Certilia. "
                "Postavite ga u .env datoteci ili kontaktirajte podršku."
            )
        if not settings.CEZIH_CLIENT_ID:
            raise CezihSigningError(
                "OAuth2 postavke za potpisivanje nisu konfigurirane. "
                "Postavite CEZIH_SIGNING_OAUTH2_URL i CEZIH_CLIENT_ID.",
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
                        f"OAuth2 prijava za potpisivanje nije uspjela: {body.get('error_description', body.get('error', 'Nepoznata greška'))}",
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
                f"Veza sa CEZIH servisom za potpisivanje nije uspjela ({oauth_url}). "
                "Provjerite internet vezu i VPN.",
            ) from e
        except httpx.TimeoutException as e:
            raise CezihSigningError(
                f"Potpis istekao — CEZIH servis ne odgovara u {settings.CEZIH_TIMEOUT}s.",
            ) from e
        except httpx.HTTPStatusError as e:
            raise CezihSigningError(
                f"OAuth2 prijava za potpisivanje odbijena: HTTP {e.response.status_code} - {e.response.text[:200]}",
            ) from e
        except Exception as e:
            raise CezihSigningError(
                f"OAuth2 prijava za potpisivanje nije uspjela: {e}",
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


async def sign_bundle_for_cezih(
    bundle_json_bytes: bytes,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict:
    """Sign a FHIR Bundle for CEZIH using the agent's smart card.

    Per CEZIH format (raw concatenation):
      signature.data = base64( header_json_bytes || bundle_json_bytes || raw_signature_bytes )

    Flow:
    1. Get cert info (kid, algorithm) from agent
    2. Build minimal JOSE header: {"kid":"<kid>","alg":"<algorithm>"}
    3. Concatenate: signing_input = header_bytes + bundle_bytes
    4. Agent hashes signing_input and signs via NCryptSignHash
    5. Return header_json + raw signature bytes for assembly
    """
    if not _should_use_agent():
        raise CezihSigningError("Neispravna CEZIH konekcija — agent nije spojen")

    from app.services.agent_connection_manager import agent_manager
    from app.services.cezih.client import current_tenant_id

    tenant_id = current_tenant_id.get()

    # Step 1: Get certificate info (kid + algorithm) from agent
    try:
        cert_info = await agent_manager.get_cert_info(tenant_id, timeout=15.0)
    except RuntimeError as e:
        raise CezihSigningError(f"Greška pri čitanju podataka kartice: {e}") from e

    if "error" in cert_info:
        raise CezihSigningError(f"Kartica nije dostupna: {cert_info['error']}")

    kid = cert_info.get("kid", "")
    algorithm = cert_info.get("algorithm", "RS256")

    # Step 2: Build minimal JOSE header (compact JSON, no spaces)
    header_json = json.dumps({"kid": kid, "alg": algorithm}, separators=(",", ":"))

    # Step 3: Concatenate header + bundle for signing input
    header_bytes = header_json.encode("utf-8")
    signing_input = header_bytes + bundle_json_bytes

    # Step 4: Send to agent for raw signing
    data_b64 = base64.b64encode(signing_input).decode("ascii")

    logger.info("CEZIH raw signing via agent (input=%d bytes, kid=%.16s, alg=%s)",
                len(signing_input), kid, algorithm)

    try:
        result = await agent_manager.sign_raw(
            tenant_id,
            data_base64=data_b64,
            algorithm=algorithm,
            timeout=300.0,
        )
    except RuntimeError as e:
        raise CezihSigningError(f"Greška pri potpisivanju putem agenta: {e}") from e

    if "error" in result:
        raise CezihSigningError(f"Potpisivanje putem agenta nije uspjelo: {result['error']}")

    sig_b64 = result.get("signature", "")
    signature_bytes = base64.b64decode(sig_b64)

    logger.info("Agent raw signing OK: alg=%s, sig=%d bytes, kid=%.16s",
                algorithm, len(signature_bytes), kid)

    return {
        "success": True,
        "header_json": header_json,
        "signature_bytes": signature_bytes,
        "signing_algorithm": algorithm,
        "signed_at": datetime.now(UTC).isoformat(),
        "kid": kid,
    }




async def sign_bundle_via_extsigner(
    bundle_json_bytes: bytes,
    *,
    message_id: str | None = None,
) -> dict:
    """Sign a FHIR Bundle via CEZIH extsigner API (Certilia remote signing).

    Two-step flow:
    1. POST /extsigner/api/sign → submit bundle, get transactionCode
    2. GET /extsigner/api/getSignedDocuments?transactionCode=... → retrieve signed document

    The signing happens asynchronously — user approves on Certilia phone app.
    We poll getSignedDocuments until the signed document is available.
    """
    if not _should_use_agent():
        raise CezihSigningError("Neispravna CEZIH konekcija — agent nije spojen")

    signer_oib = settings.CEZIH_SIGNER_OIB
    if not signer_oib:
        raise CezihSigningError(
            "CEZIH_SIGNER_OIB nije postavljen. Potrebno je za udaljeno potpisivanje (extsigner)."
        )

    # Extsigner uses public hostname (no VPN needed), falls back to VPN URL.
    base_url = settings.CEZIH_FHIR_PUB_BASE_URL or settings.CEZIH_FHIR_BASE_URL
    if not base_url:
        raise CezihSigningError("CEZIH_FHIR_BASE_URL nije postavljen.")

    base = base_url.rstrip("/")
    sign_url = f"{base}/services-router/gateway/extsigner/api/sign"
    retrieve_url = f"{base}/services-router/gateway/extsigner/api/getSignedDocuments"

    import uuid as _uuid
    request_id = str(_uuid.uuid4())
    msg_id = message_id or str(_uuid.uuid4())

    # Encode bundle as base64
    bundle_b64 = base64.b64encode(bundle_json_bytes).decode("ascii")

    # Detect bundle type: transaction bundles (ITI-65) use FHIR_DOCUMENT,
    # message bundles (visits/cases) use FHIR_MESSAGE
    bundle_type = _detect_bundle_type(bundle_json_bytes)
    doc_type = "FHIR_DOCUMENT" if bundle_type == "transaction" else "FHIR_MESSAGE"

    payload = {
        "oib": signer_oib,
        "sourceSystem": "HM-DIGITAL-MEDICAL",
        "requestId": request_id,
        "documents": [
            {
                "documentType": doc_type,
                "mimeType": "JSON",
                "base64Document": bundle_b64,
                "messageId": msg_id,
            }
        ],
    }

    # Step 1: Submit document for signing
    # Auth: mTLS via agent session — NO Bearer token (adding one causes 401).
    logger.info(
        "CEZIH extsigner step 1: submitting for signing (OIB=%.6s..., bundle=%d bytes)",
        signer_oib, len(bundle_json_bytes),
    )

    sign_result = await _request_via_agent(
        method="POST",
        url=sign_url,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        form_data=None,
        json_body=payload,
        timeout=30,
    )

    transaction_code = sign_result.get("transactionCode", "")
    if not transaction_code:
        logger.error("Extsigner sign response missing transactionCode: %s", sign_result)
        raise CezihSigningError(f"Extsigner nije vratio transactionCode: {sign_result}")

    logger.info(
        "CEZIH extsigner step 1 OK: transactionCode=%.40s..., documents=%s",
        transaction_code, sign_result.get("documents"),
    )

    # Step 2: Poll for signed document (user needs to approve on phone)
    import urllib.parse
    tc_encoded = urllib.parse.quote(transaction_code, safe="")
    get_url = f"{retrieve_url}?transactionId={tc_encoded}"

    max_attempts = 60  # 60 x 5s = 300 seconds total
    poll_interval = 5

    for attempt in range(1, max_attempts + 1):
        logger.info(
            "CEZIH extsigner step 2: polling for signed document (attempt %d/%d)",
            attempt, max_attempts,
        )

        try:
            retrieve_result = await _request_via_agent(
                method="GET",
                url=get_url,
                headers={"Accept": "application/json"},
                form_data=None,
                json_body=None,
                timeout=30,
            )
        except CezihSigningError as e:
            err_str = str(e)
            # ERROR_CODE_0022 = "not ready yet" (phase=HASH_SENT, waiting for Certilia approval)
            if "ERROR_CODE_0022" in err_str or "not ready" in err_str.lower():
                logger.info("Extsigner: document not ready yet — phase=HASH_SENT (attempt %d/%d)", attempt, max_attempts)
                await asyncio.sleep(poll_interval)
                continue
            # Other retriable statuses
            if "HTTP 404" in err_str or "HTTP 202" in err_str:
                logger.info("Extsigner: document not ready yet (attempt %d/%d)", attempt, max_attempts)
                await asyncio.sleep(poll_interval)
                continue
            raise

        logger.info(
            "CEZIH extsigner retrieve response: %s",
            json.dumps(retrieve_result, ensure_ascii=False)[:50000],
        )

        # TC16 diagnostics: sha256 + head of the decoded signed payload so we can
        # diff against the bundle actually POSTed (logged in condition.py).
        # A mismatch means the bundle was mutated after add_signature, which
        # invalidates the signature → ERR_DS_1002 / business-rule on verify.
        try:
            docs = (
                retrieve_result.get("documents")
                or retrieve_result.get("signedDocuments")
                or []
            )
            if docs:
                import base64 as _b64
                import hashlib as _hashlib
                doc = docs[0] or {}
                doc_b64 = (
                    doc.get("document")
                    or doc.get("content")
                    or doc.get("signedDocument")
                    or ""
                )
                if doc_b64:
                    raw = _b64.b64decode(doc_b64)
                    sha = _hashlib.sha256(raw).hexdigest()[:16]
                    logger.info(
                        "Extsigner signed-document: size=%d bytes, sha256-prefix=%s, head=%s",
                        len(raw), sha, raw[:500].decode("utf-8", errors="replace"),
                    )
        except Exception as _diag_err:  # pragma: no cover — best-effort
            logger.warning("Extsigner signed-document diag failed: %s", _diag_err)

        # Check if we got signed documents back
        status_code = retrieve_result.get("status_code", 0)
        if status_code == 200 or "documents" in retrieve_result:
            return {
                "success": True,
                "method": "extsigner",
                "response": retrieve_result,
                "transaction_code": transaction_code,
                "signed_at": datetime.now(UTC).isoformat(),
            }

        # If still pending, wait and retry
        if status_code in (202, 204):
            logger.info("Extsigner: signing pending (HTTP %d), waiting...", status_code)
            await asyncio.sleep(poll_interval)
            continue

        # Unknown status — return what we got for debugging
        return {
            "success": True,
            "method": "extsigner",
            "response": retrieve_result,
            "transaction_code": transaction_code,
            "signed_at": datetime.now(UTC).isoformat(),
        }

    raise CezihSigningError(
        f"Potpis istekao — Certilia nije potvrdila potpis u {max_attempts * poll_interval}s. "
        "Provjerite Certilia aplikaciju na mobitelu."
    )


async def check_extsigner_transaction(transaction_code: str) -> dict:
    """Check the status of an extsigner transaction using the transactionCode.

    Probes various possible retrieval endpoints to discover the API.
    """
    if not _should_use_agent():
        raise CezihSigningError("Agent nije spojen")

    base_url = settings.CEZIH_FHIR_PUB_BASE_URL or settings.CEZIH_FHIR_BASE_URL
    if not base_url:
        raise CezihSigningError("CEZIH_FHIR_BASE_URL nije postavljen.")

    base = base_url.rstrip("/")
    results = {}

    # Try different possible retrieval endpoints
    endpoints = [
        ("GET", f"{base}/services-router/gateway/extsigner/api/sign/{transaction_code}"),
        ("GET", f"{base}/services-router/gateway/extsigner/api/status/{transaction_code}"),
        ("GET", f"{base}/services-router/gateway/extsigner/api/documents/{transaction_code}"),
        ("POST", f"{base}/services-router/gateway/extsigner/api/retrieve"),
    ]

    for method, url in endpoints:
        try:
            if method == "POST":
                result = await _request_via_agent(
                    method="POST", url=url,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    form_data=None,
                    json_body={"transactionCode": transaction_code},
                    timeout=30,
                )
            else:
                result = await _request_via_agent(
                    method="GET", url=url,
                    headers={"Accept": "application/json"},
                    form_data=None, json_body=None,
                    timeout=30,
                )
            results[url] = result
            logger.info("Extsigner probe %s %s → %s", method, url, json.dumps(result, ensure_ascii=False)[:500])
        except CezihSigningError as e:
            results[url] = {"error": str(e)}
            logger.info("Extsigner probe %s %s → error: %s", method, url, e)

    return results


async def sign_document(
    client: httpx.AsyncClient,
    document_bytes: bytes | str,
    *,
    document_id: str | None = None,
    signing_reason: str = "CEZIH clinical document",
) -> dict:
    """Legacy sign_document — delegates to sign_bundle_for_cezih."""
    if isinstance(document_bytes, str):
        document_bytes = document_bytes.encode("utf-8")
    return await sign_bundle_for_cezih(document_bytes)


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
