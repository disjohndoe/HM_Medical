"""CEZIH digital signing — JWS Bundle.signature construction.

Two methods, both producing Bundle.signature.data = base64(JWS_compact):
  - smartcard: Local Agent signs via NCrypt + AKD card (JCS canonical payload)
  - extsigner: CEZIH signs remotely via Certilia cloud cert (user approves on phone)

Per-user preference via User.cezih_signing_method; no fallbacks.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.services.cezih.builders.common import _now_iso, org_ref, patient_ref, practitioner_ref
from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

# Moved verbatim from message_builder.py:
SIGNATURE_TYPE_SYSTEM = "urn:iso-astm:E1762-95:2013"
SIGNATURE_TYPE_CODE = "1.2.840.10065.1.12.1.1"  # Author's signature


def _debug_dump_jws(source: str, jws_b64: str) -> None:
    """Dump decoded JWS (header JSON + full b64url payload + full b64url sig).

    Emits at INFO level, only when ``settings.CEZIH_SIGNING_DEBUG`` is true.
    One value per log line so grep can pull them out of docker logs cleanly.

    ``jws_b64`` is the *outer* base64 wrapping the JWS compact form (our "double
    base64"). Both smartcard and extsigner produce this shape.
    """
    import base64 as _base64

    from app.config import settings

    if not settings.CEZIH_SIGNING_DEBUG:
        return
    try:
        jws_raw = _base64.b64decode(jws_b64).decode("ascii")
        parts = jws_raw.split(".")
        if len(parts) != 3:
            logger.info(
                "%s JWS DUMP: unexpected part count (%d), raw=%s",
                source, len(parts), jws_raw[:500],
            )
            return
        header_raw = _base64.urlsafe_b64decode(parts[0] + "==")
        header_json = json.loads(header_raw)
        # Detached JWS has empty middle segment — don't attempt to decode it.
        payload_raw = _base64.urlsafe_b64decode(parts[1] + "==") if parts[1] else b""
        # Re-serialise header with sorted keys so order differences become
        # visible even if the caller used different dict key ordering.
        header_sorted = json.dumps(header_json, sort_keys=True, ensure_ascii=False)
        logger.info("%s JWS DUMP header_json_sorted=%s", source, header_sorted)
        logger.info("%s JWS DUMP header_b64url=%s", source, parts[0])
        logger.info("%s JWS DUMP payload_b64url_len=%d", source, len(parts[1]))
        if parts[1]:
            logger.info("%s JWS DUMP payload_b64url=%s", source, parts[1])
            logger.info("%s JWS DUMP payload_decoded_len=%d", source, len(payload_raw))
            try:
                payload_json = json.loads(payload_raw)
                logger.info(
                    "%s JWS DUMP payload_json_sorted=%s",
                    source, json.dumps(payload_json, sort_keys=True, ensure_ascii=False),
                )
            except Exception:
                logger.info("%s JWS DUMP payload_utf8=%s", source, payload_raw.decode("utf-8", errors="replace"))
        else:
            logger.info("%s JWS DUMP payload=<detached/empty>", source)
        logger.info("%s JWS DUMP sig_b64url=%s", source, parts[2])
    except Exception as _err:
        logger.warning("%s JWS DUMP failed to decode: %s", source, _err)


async def _resolve_signing_method() -> str:
    """Resolve the active signing method for the current request from the user's
    `cezih_signing_method` column.

    Raises CezihError if:
    - No user is logged in
    - Database is not available
    - DB lookup fails
    - User has no signing method configured
    """
    from sqlalchemy import select

    from app.models.user import User
    from app.services.cezih.client import current_db_session, current_user_id

    user_id = current_user_id.get()
    db = current_db_session.get()

    if not user_id:
        logger.error("Signing method resolution failed: no user in context")
        raise CezihError("Nema prijavljenog korisnika za potpisivanje.")

    if db is None:
        logger.error("Signing method resolution failed: no database session")
        raise CezihError("Baza podataka nije dostupna.")

    try:
        method = await db.scalar(
            select(User.cezih_signing_method).where(User.id == user_id)
        )
    except Exception as e:
        logger.error("DB lookup failed for signing method (user_id=%s): %s", user_id, e)
        raise CezihError(
            "Potpis nije konfiguriran. Kontaktirajte administratora ili "
            "odaberite način potpisa u Postavke."
        ) from e

    if not method:
        logger.error("User has no signing method configured (user_id=%s)", user_id)
        raise CezihError(
            "Korisnik nema konfiguriran način potpisa. "
            "Odaberite 'AKD kartica' ili 'Certilia mobilni' u Postavke."
        )

    logger.info("Resolved signing method for user_id=%s: %s", user_id, method)
    return method


async def add_signature(
    bundle: dict[str, Any],
    practitioner_id: str,
    sign_fn: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Add a digital signature to the Bundle per CEZIH JWS format.

    Two signing methods (per-user pref, falls back to CEZIH_SIGNING_METHOD env):
    - "smartcard": Agent signs locally via NCrypt + AKD smart card
    - "extsigner": CEZIH signs remotely via Certilia (user approves on phone)

    For smartcard:
      signature.data = base64(JWS_compact) — double base64 for HAPI compatibility.

    For extsigner:
      Send full bundle to extsigner API → CEZIH signs with Certilia cloud cert.
      Response contains the signed document (signature already embedded by CEZIH).
    """
    signing_method = await _resolve_signing_method()
    logger.info("CEZIH signing method resolved: %s", signing_method)

    if signing_method == "extsigner":
        return await _add_signature_extsigner(bundle, practitioner_id)

    # Default: smartcard signing via agent
    return await _add_signature_smartcard(bundle, practitioner_id, sign_fn)


async def _add_signature_extsigner(
    bundle: dict[str, Any],
    practitioner_id: str,
) -> dict[str, Any]:
    """Sign bundle via CEZIH extsigner (Certilia remote signing on phone).

    Sends the bundle to extsigner API. CEZIH signs it with user's Certilia
    cloud cert and returns the signed document. We need to extract the
    signature from the response and set it on our bundle, OR use the
    returned signed bundle directly.
    """
    from app.services.cezih_signing import sign_bundle_via_extsigner

    # ITI-65 transaction bundles are not signed via extsigner.
    # Extsigner only accepts FHIR_MESSAGE documentType — it rejects transaction
    # bundles with HPDF_GENERAL_ERROR/A250/INVALID_JSON_PAYLOAD. CEZIH ITI-65
    # ingest does not cryptographically verify Bundle.signature either, so we
    # return the bundle unsigned. Card path adds a local JWS signature; for
    # mobile we simply skip signing entirely.
    if bundle.get("type") == "transaction":
        logger.info(
            "ITI-65 transaction bundle detected — skipping extsigner (unsigned send)",
        )
        return bundle

    # Add signature placeholder (extsigner may need it in the structure)
    bundle["signature"] = {
        "type": [
            {
                "system": SIGNATURE_TYPE_SYSTEM,
                "code": SIGNATURE_TYPE_CODE,
            },
        ],
        "when": _now_iso(),
        "who": patient_ref(practitioner_id),
        "data": "",
    }

    # Serialize to compact JSON
    bundle_json_bytes = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # Extract message ID from bundle for correlation
    message_id = bundle.get("id", None)

    result = await sign_bundle_via_extsigner(bundle_json_bytes, message_id=message_id)

    response = result.get("response", {})

    # Try to extract signed document from retrieval response
    # API returns "signedDocuments" (getSignedDocuments) or "documents" (sign)
    documents = response.get("signedDocuments") or response.get("documents")

    # Case 1: documents is a list with signed bundles
    if isinstance(documents, list) and documents:
        doc = documents[0]
        if isinstance(doc, dict) and doc.get("base64Document"):
            import base64 as _base64
            signed_bundle_bytes = _base64.b64decode(doc["base64Document"])
            signed_bundle = json.loads(signed_bundle_bytes)
            logger.info("Extsigner returned signed bundle — using CEZIH-signed document")

            # ── DEBUG: decode and log extsigner's JWS signature for comparison ──
            try:
                _sig_data = signed_bundle.get("signature", {}).get("data", "")
                if _sig_data:
                    _jws_raw = _base64.b64decode(_sig_data).decode("ascii")
                    _parts = _jws_raw.split(".")
                    if len(_parts) == 3:
                        _header_raw = _base64.urlsafe_b64decode(_parts[0] + "==")
                        _header_json = json.loads(_header_raw)
                        logger.info(
                            "EXTSIGNER JWS DECODED: alg=%s kid=%s jwk_keys=%s x5c_count=%d "
                            "header_b64url=%d chars payload_b64url=%d chars sig_b64url=%d chars",
                            _header_json.get("alg"), _header_json.get("kid", "?")[:16],
                            list(_header_json.get("jwk", {}).keys()) if "jwk" in _header_json else "none",
                            len(_header_json.get("x5c", [])),
                            len(_parts[0]), len(_parts[1]), len(_parts[2]),
                        )
                    elif len(_parts) == 2:
                        logger.info("EXTSIGNER JWS: appears to be 2-part (detached?) len=%d", len(_jws_raw))
                    else:
                        logger.info("EXTSIGNER JWS: unexpected format (dot_count=%d, total=%d chars)",
                                    _jws_raw.count("."), len(_jws_raw))
                    _debug_dump_jws("EXTSIGNER", _sig_data)
            except Exception as _dbg_err:
                logger.warning("Extsigner JWS decode debug failed: %s", _dbg_err)

            return signed_bundle
        if isinstance(doc, dict) and doc.get("signature"):
            bundle["signature"]["data"] = doc["signature"]
            logger.info("Extsigner returned signature in document object")
            return bundle

    # Case 2: signature at top level
    signature_data = response.get("signature", response.get("signatureData", ""))
    if signature_data:
        bundle["signature"]["data"] = signature_data
        logger.info("Extsigner returned signature value — applied to bundle")
        return bundle

    # Case 3: log the full response for debugging and raise
    logger.warning(
        "Extsigner response format unknown — raw: %s",
        json.dumps(response, ensure_ascii=False)[:2000],
    )
    from app.services.cezih.exceptions import CezihSigningError
    raise CezihSigningError(
        "Certilia potpisivanje nije vratilo očekivani odgovor. "
        "Provjerite da je Certilia aplikacija aktivna na mobitelu i pokušajte ponovno."
    )


async def _add_signature_smartcard(
    bundle: dict[str, Any],
    practitioner_id: str,
    sign_fn: Any = None,
) -> dict[str, Any]:
    """Sign bundle via agent's smart card (NCrypt JWS signing).

    Per CEZIH spec section 3.4 ("Digitalni potpis", normative — see
    docs/CEZIH/findings/cezih-official-signature-format.md), the JWS payload
    MUST be the JCS-canonicalized Bundle JSON (RFC 8785) with
    `Bundle.signature.data` EXCLUDED.

    Mistakes that previously caused ERR_DS_1002:
    - Including `signature.data: ""` in the canonical payload (verifier strips
      it → hash mismatch).
    - Plain `json.dumps(separators=(",",":"))` is compact but NOT JCS — keys
      are not sorted recursively per RFC 8785. CEZIH re-canonicalizes when
      verifying, so any key order divergence breaks the signature.
    """
    import base64 as _base64

    from app.config import settings as _settings
    from app.services.agent_connection_manager import agent_manager
    from app.services.cezih.client import current_tenant_id

    # Build signature element — match extsigner format exactly:
    # compact JSON with data="" (same bytes that extsigner sends to CEZIH).
    sig_elem = {
        "type": [
            {
                "system": SIGNATURE_TYPE_SYSTEM,
                "code": SIGNATURE_TYPE_CODE,
            },
        ],
        "when": _now_iso(),
        "who": patient_ref(practitioner_id),
        "data": "",
    }
    bundle["signature"] = sig_elem

    # JCS-canonicalize per RFC 8785. CEZIH verifier strips signature.data
    # then re-canonicalizes the Bundle — our signing input must match.
    import jcs as _jcs
    bundle_json_bytes = _jcs.canonicalize(bundle)
    logger.info("JCS canonical payload: %d bytes (signature.data excluded)", len(bundle_json_bytes))

    # ── DEBUG: dump pre-sign payload so we can compare what we *sent* to the
    #    agent vs what extsigner received as input. If payloads differ the JWS
    #    will differ regardless of crypto.
    if _settings.CEZIH_SIGNING_DEBUG:
        try:
            _pre_json = json.loads(bundle_json_bytes)
            logger.info(
                "SMARTCARD PRE-SIGN payload_json_sorted=%s",
                json.dumps(_pre_json, sort_keys=True, ensure_ascii=False),
            )
        except Exception:
            logger.info("SMARTCARD PRE-SIGN payload_bytes=%s",
                        bundle_json_bytes.decode("utf-8", errors="replace"))
        logger.info(
            "SMARTCARD PRE-SIGN payload_b64url=%s",
            _base64.urlsafe_b64encode(bundle_json_bytes).decode().rstrip("="),
        )

    if sign_fn:
        # Test hook — custom sign function
        result = await sign_fn(bundle_json_bytes)
        jws_base64 = result.get("jws_base64", "")
    else:
        if _settings.CEZIH_SMARTCARD_DUMMY_SIG:
            # ── DEBUG: inject structurally valid but crypto-meaningless JWS ──
            # Tests whether CEZIH verifies signature crypto or just checks structure.
            # Uses proper base64url encoding to match real JWS format.
            # CEZIH_SMARTCARD_DUMMY_ALG selects algorithm: "RS256" or "ES384"
            import hashlib as _hashlib

            b64url = _base64.urlsafe_b64encode
            dummy_alg = getattr(_settings, "CEZIH_SMARTCARD_DUMMY_ALG", "RS256") or "RS256"

            if dummy_alg == "ES384":
                # P-384 signature: r||s, 48+48 = 96 bytes
                fake_sig = _hashlib.sha384(bundle_json_bytes).digest() * 2
                dummy_jose = {"alg": "ES384", "kid": "dummy-es384-test"}
            else:
                # RSA-2048 signature: 256 bytes
                fake_sig = _hashlib.sha256(bundle_json_bytes).digest() * 8
                dummy_jose = {"alg": "RS256", "kid": "dummy-rs256-test"}

            header_b64url = b64url(json.dumps(dummy_jose, separators=(",", ":")).encode()).decode().rstrip("=")
            payload_b64url = b64url(bundle_json_bytes).decode().rstrip("=")
            sig_b64url = b64url(fake_sig).decode().rstrip("=")
            dummy_jws = f"{header_b64url}.{payload_b64url}.{sig_b64url}"
            jws_base64 = _base64.b64encode(dummy_jws.encode()).decode()
            logger.warning(
                "DUMMY SIGNATURE INJECTED alg=%s — CEZIH_SMARTCARD_DUMMY_SIG=true. "
                "NOT crypto-valid. header_b64url=%d chars payload_b64url=%d chars sig_b64url=%d chars",
                dummy_alg, len(header_b64url), len(payload_b64url), len(sig_b64url),
            )
        else:
            # Production: use agent's JWS signing (builds JOSE header with x5c + signs)
            tenant_id = current_tenant_id.get()
            data_b64 = _base64.b64encode(bundle_json_bytes).decode("ascii")

            result = await agent_manager.sign_jws(
                tenant_id,
                data_base64=data_b64,
                timeout=300.0,
            )

            if "error" in result:
                from app.services.cezih.exceptions import CezihSigningError
                logger.warning("Smartcard agent signing error: %s", result['error'])
                raise CezihSigningError(
                    f"Potpisivanje pametnom karticom nije uspjelo: {result['error']}"
                )

            jws_base64 = result.get("jws_base64", "")
            if not jws_base64:
                from app.services.cezih.exceptions import CezihSigningError
                raise CezihSigningError("Kartica nije vratila potpis. Umetnite karticu i pokušajte ponovno.")

            logger.info("JWS signature: kid=%s, alg=%s, data=%d chars",
                         result.get("kid", "?"), result.get("algorithm", "?"), len(jws_base64))

            # ── DEBUG: decode and log full JWS structure for comparison ──
            try:
                _jws_raw = _base64.b64decode(jws_base64).decode("ascii")
                _parts = _jws_raw.split(".")
                if len(_parts) == 3:
                    _header_raw = _base64.urlsafe_b64decode(_parts[0] + "==")
                    _header_json = json.loads(_header_raw)
                    logger.info(
                        "SMARTCARD JWS DECODED: alg=%s kid=%s jwk_keys=%s x5c_count=%d "
                        "header_b64url=%d chars payload_b64url=%d chars sig_b64url=%d chars",
                        _header_json.get("alg"), _header_json.get("kid", "?")[:16],
                        list(_header_json.get("jwk", {}).keys()) if "jwk" in _header_json else "none",
                        len(_header_json.get("x5c", [])),
                        len(_parts[0]), len(_parts[1]), len(_parts[2]),
                    )
                _debug_dump_jws("SMARTCARD", jws_base64)
            except Exception as _dbg_err:
                logger.warning("JWS decode debug failed: %s", _dbg_err)

    # Inject the JWS into signature.data AFTER signing. The bundle sent to
    # CEZIH carries signature.data; the verifier strips it before re-canonicalizing.
    # Agent returns base64(JWS_compact) — "double base64" for FHIR base64Binary.
    bundle["signature"]["data"] = jws_base64

    return bundle


__all__ = [
    "SIGNATURE_TYPE_CODE",
    "SIGNATURE_TYPE_SYSTEM",
    "_add_signature_extsigner",
    "_add_signature_smartcard",
    "_debug_dump_jws",
    "_resolve_signing_method",
    "add_signature",
]
