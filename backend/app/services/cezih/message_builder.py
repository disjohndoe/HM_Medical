# ruff: noqa: N815 — FHIR spec requires camelCase field names
"""FHIR message Bundle builder for CEZIH $process-message operations.

Builds Bundle type="message" with MessageHeader + resource + digital signature.
Used for Case Management (codes 2.x).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

# --- Constants: CEZIH FHIR identifier systems ---

MESSAGE_TYPE_SYSTEM = "http://ent.hr/fhir/CodeSystem/ehe-message-types"
SIGNATURE_TYPE_SYSTEM = "urn:iso-astm:E1762-95:2013"
SIGNATURE_TYPE_CODE = "1.2.840.10065.1.12.1.1"  # Author's signature

ID_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"
ID_ORG = "http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije"
ID_PRACTITIONER = "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika"
ID_CASE_GLOBAL = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja"
ID_CASE_REF = "http://fhir.cezih.hr/specifikacije/identifikatori/slucaj"  # Used in Encounter.diagnosis
ID_CASE_LOCAL = "http://fhir.cezih.hr/specifikacije/identifikatori/lokalni-identifikator-slucaja"
ID_ENCOUNTER = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-posjete"

CS_ICD10_HR = "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"
CS_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/CodeSystem/annotation-type"
CS_CONDITION_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CS_CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"

EXT_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-annotation-type"
EXT_TROSKOVI_SUDJELovanje = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-troskovi-sudjelovanje"
CS_SUDJELOVANJE_U_TROSKOVIMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/sudjelovanje-u-troskovima"
CS_SIFRA_OSLOBODJENJA = "http://fhir.cezih.hr/specifikacije/CodeSystem/sifra-oslobodjenja-od-sudjelovanja-u-troskovima"


# --- Helper: Logical references (identifier-based, no literal URL) ---


def patient_ref(mbo: str) -> dict[str, Any]:
    return {"type": "Patient", "identifier": {"system": ID_MBO, "value": mbo}}


def org_ref(org_code: str) -> dict[str, Any]:
    return {"type": "Organization", "identifier": {"system": ID_ORG, "value": org_code}}


def practitioner_ref(hzjz_id: str) -> dict[str, Any]:
    return {"type": "Practitioner", "identifier": {"system": ID_PRACTITIONER, "value": hzjz_id}}


_TZ_ZAGREB = ZoneInfo("Europe/Zagreb")


def _now_iso() -> str:
    return datetime.now(_TZ_ZAGREB).isoformat()


# --- Message Bundle Builder ---


async def build_message_bundle(
    event_code: str,
    resource: dict[str, Any],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    source_oid: str | None = None,
    profile_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='message' with MessageHeader and resource.

    Does NOT add signature — call add_signature() separately for real mode.
    profile_urls: optional {"bundle": url, "header": url, "resource": url} for meta.profile.
    """
    if not sender_org_code:
        raise CezihError(
            "Šifra zdravstvene ustanove (org_code) nije konfigurirana za ovog zakupca. "
            "Postavite je u Postavke > Organizacija."
        )
    if not source_oid:
        raise CezihError(
            "OID informacijskog sustava nije konfiguriran za ovog zakupca. "
            "Postavite ga u Postavke > Organizacija."
        )

    resource_uuid = str(uuid.uuid4())
    header_uuid = str(uuid.uuid4())

    message_header: dict[str, Any] = {
        "resourceType": "MessageHeader",
        "eventCoding": {
            "system": MESSAGE_TYPE_SYSTEM,
            "code": event_code,
        },
    }

    # Field order matches official CEZIH example: sender, author, source, focus
    if sender_org_code:
        message_header["sender"] = org_ref(sender_org_code)

    if author_practitioner_id:
        message_header["author"] = practitioner_ref(author_practitioner_id)

    message_header["source"] = {"endpoint": f"urn:oid:{source_oid}" if source_oid else "urn:oid:0.0.0.0"}
    message_header["focus"] = [{"reference": f"urn:uuid:{resource_uuid}"}]

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "message",
        "timestamp": _now_iso(),
        "entry": [
            {
                "fullUrl": f"urn:uuid:{header_uuid}",
                "resource": message_header,
            },
            {
                "fullUrl": f"urn:uuid:{resource_uuid}",
                "resource": resource,
            },
        ],
    }

    # Inject meta.profile if profile URLs are provided
    if profile_urls:
        if profile_urls.get("bundle"):
            bundle["meta"] = {"profile": [profile_urls["bundle"]]}
        if profile_urls.get("header"):
            message_header["meta"] = {"profile": [profile_urls["header"]]}
        if profile_urls.get("resource"):
            resource["meta"] = {"profile": [profile_urls["resource"]]}

    return bundle


def build_iti65_transaction_bundle(
    entries: list[dict[str, Any]],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    bundle_profile: str | None = None,
    submission_set_profile: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='transaction' for IHE MHD ITI-65 document submission.

    IHE MHD ITI-65 requires type="transaction" (NOT type="message").
    Each entry must have a `request` with method and url.
    Optionally includes a SubmissionSet (List) as the first entry.
    """
    # Build SubmissionSet (List) — required by IHE MHD ITI-65
    # HRMinimalSubmissionSet requires 2 identifiers: uniqueId + entryUUID
    submission_set_uuid = str(uuid.uuid4())
    unique_id = str(uuid.uuid4())
    submission_set: dict[str, Any] = {
        "resourceType": "List",
        "meta": {
            "profile": [submission_set_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalSubmissionSet"],
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{unique_id}",
            },
            {
                "use": "usual",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{submission_set_uuid}",
            },
        ],
        "status": "current",
        "mode": "working",
        "code": {
            "coding": [{
                "system": "https://profiles.ihe.net/ITI/MHD/CodeSystem/MHDlistTypes",
                "code": "submissionset",
            }]
        },
        "date": _now_iso(),
    }
    # Copy subject from the first DocumentReference (mustSupport on SubmissionSet)
    if entries and entries[0].get("subject"):
        submission_set["subject"] = entries[0]["subject"]
    # List.source only accepts Practitioner/Patient/Device — NOT Organization
    if author_practitioner_id:
        submission_set["source"] = practitioner_ref(author_practitioner_id)
    # Extensions: sourceId (required, min:1) + ihe-authorOrg
    extensions: list[dict[str, Any]] = [
        {
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-sourceId",
            "valueIdentifier": {
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:oid:{sender_org_code}" if sender_org_code else "urn:oid:2.16.840.1.113883.2.7",
            },
        },
    ]
    if sender_org_code:
        extensions.append({
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-authorOrg",
            "valueReference": org_ref(sender_org_code),
        })
    submission_set["extension"] = extensions

    # Pre-assign UUIDs to entries without _uuid to ensure consistency
    for e in entries:
        if "_uuid" not in e:
            e["_uuid"] = str(uuid.uuid4())

    # SubmissionSet entry references only DocumentReference entries (NOT Binary)
    doc_ref_entries = [e for e in entries if e.get("resourceType") == "DocumentReference"]
    doc_ref_uuids = [e["_uuid"] for e in doc_ref_entries]
    all_uuids = [e["_uuid"] for e in entries]
    submission_set["entry"] = [
        {"item": {"reference": f"urn:uuid:{u}"}} for u in doc_ref_uuids
    ]

    bundle_entries: list[dict[str, Any]] = [
        {
            "fullUrl": f"urn:uuid:{submission_set_uuid}",
            "resource": submission_set,
            "request": {"method": "POST", "url": "List"},
        }
    ]

    for i, entry_resource in enumerate(entries):
        entry_uuid = all_uuids[i]
        # Remove internal _uuid marker if present
        resource = {k: v for k, v in entry_resource.items() if k != "_uuid"}
        resource_type = resource.get("resourceType", "DocumentReference")
        resource_id = resource.get("id")

        # Use PUT for existing resources (cancel/update), POST for new ones
        if resource_id:
            request_entry = {"method": "PUT", "url": f"{resource_type}/{resource_id}"}
            full_url = f"urn:uuid:{entry_uuid}"
        else:
            request_entry = {"method": "POST", "url": resource_type}
            full_url = f"urn:uuid:{entry_uuid}"

        bundle_entries.append({
            "fullUrl": full_url,
            "resource": resource,
            "request": request_entry,
        })

    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "meta": {
            "profile": [bundle_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalProvideDocumentBundle"],
        },
        "type": "transaction",
        "timestamp": _now_iso(),
        "entry": bundle_entries,
    }


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
        payload_raw = _base64.urlsafe_b64decode(parts[1] + "==")
        # Re-serialise header with sorted keys so order differences become
        # visible even if the caller used different dict key ordering.
        header_sorted = json.dumps(header_json, sort_keys=True, ensure_ascii=False)
        logger.info("%s JWS DUMP header_json_sorted=%s", source, header_sorted)
        logger.info("%s JWS DUMP header_b64url=%s", source, parts[0])
        logger.info("%s JWS DUMP payload_b64url_len=%d", source, len(parts[1]))
        logger.info("%s JWS DUMP payload_b64url=%s", source, parts[1])
        logger.info("%s JWS DUMP payload_decoded_len=%d", source, len(payload_raw))
        # Payload is (or should be) a FHIR Bundle JSON. Log the decoded form
        # too so we can eyeball canonicalisation differences.
        try:
            payload_json = json.loads(payload_raw)
            logger.info(
                "%s JWS DUMP payload_json_sorted=%s",
                source, json.dumps(payload_json, sort_keys=True, ensure_ascii=False),
            )
        except Exception:
            logger.info("%s JWS DUMP payload_utf8=%s", source, payload_raw.decode("utf-8", errors="replace"))
        logger.info("%s JWS DUMP sig_b64url=%s", source, parts[2])
    except Exception as _err:
        logger.warning("%s JWS DUMP failed to decode: %s", source, _err)


async def _resolve_signing_method() -> str:
    """Resolve the active signing method for the current request.

    Order:
      1. Per-user `User.cezih_signing_method` (if column is non-NULL)
      2. System fallback `settings.CEZIH_SIGNING_METHOD`
      3. Hard default "extsigner" (the working path)
    """
    from sqlalchemy import select

    from app.config import settings
    from app.models.user import User
    from app.services.cezih.client import current_db_session, current_user_id

    user_id = current_user_id.get()
    db = current_db_session.get()
    if user_id and db is not None:
        try:
            method = await db.scalar(
                select(User.cezih_signing_method).where(User.id == user_id)
            )
            if method:
                return method
        except Exception as e:  # noqa: BLE001 — never let signing pref lookup break the request
            logger.warning("Failed to resolve per-user signing method: %s", e)

    return settings.CEZIH_SIGNING_METHOD or "extsigner"


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

    # Add signature placeholder (extsigner may need it in the structure)
    bundle["signature"] = {
        "type": [
            {
                "system": SIGNATURE_TYPE_SYSTEM,
                "code": SIGNATURE_TYPE_CODE,
            },
        ],
        "when": _now_iso(),
        "who": practitioner_ref(practitioner_id),
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
        "who": practitioner_ref(practitioner_id),
        "data": "",
    }
    bundle["signature"] = sig_elem

    # Use compact JSON (same as extsigner path) instead of JCS.
    # Extsigner uses json.dumps(ensure_ascii=False, separators=(",",":"))
    # and CEZIH's extsigner API signs those exact bytes. CEZIH verification
    # expects the same serialization form.
    bundle_json_bytes = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    logger.info("Compact JSON payload: %d bytes", len(bundle_json_bytes))

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

            # Build x5c cert chain for the JOSE header (intermediate + root).
            # Reads DER cert files from CEZIH_SMARTCARD_CERT_CHAIN_PATHS, base64-encodes each.
            extra_certs: list[str] | None = None
            chain_paths_str = getattr(_settings, "CEZIH_SMARTCARD_CERT_CHAIN_PATHS", "") or ""
            if chain_paths_str:
                import pathlib as _pathlib
                chain_paths = [p.strip() for p in chain_paths_str.split(",") if p.strip()]
                loaded: list[str] = []
                for path in chain_paths:
                    try:
                        der = _pathlib.Path(path).read_bytes()
                        loaded.append(_base64.b64encode(der).decode("ascii"))
                    except Exception as _ce:
                        logger.warning("Could not load chain cert %s: %s", path, _ce)
                if loaded:
                    extra_certs = loaded
                    logger.info("SMARTCARD x5c chain: %d extra cert(s) loaded from paths", len(loaded))

            result = await agent_manager.sign_jws(
                tenant_id,
                data_base64=data_b64,
                extra_certs=extra_certs,
                timeout=30.0,
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


# --- Encounter Resource Builders (TC12-14) ---


# CEZIH Croatian CodeSystems (NOT standard HL7 v3-ActCode)
CS_NACIN_PRIJEMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"
CS_VRSTA_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"
CS_TIP_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"

NACIN_PRIJEMA_MAP = {
    "1": "Hitni prijem",
    "2": "Uputnica PZZ",
    "3": "Premještaj iz druge ustanove",
    "4": "Nastavno liječenje",
    "5": "Premještaj unutar ustanove",
    "6": "Ostalo",
    "7": "Poziv na raniji termin",
    "8": "Telemedicina",
    "9": "Interna uputnica",
    "10": "Program+",
}

VRSTA_POSJETE_MAP = {
    "1": "Pacijent prisutan",
    "2": "Pacijent udaljeno prisutan",
    "3": "Pacijent nije prisutan",
}

TIP_POSJETE_MAP = {
    "1": "Posjeta LOM",
    "2": "Posjeta SKZZ",
    "3": "Hospitalizacija",
}

# FHIR Profile URLs for Encounter messages (meta.profile)
_PROFILE_BASE = "http://fhir.cezih.hr/specifikacije/StructureDefinition"
PROFILE_ENCOUNTER = f"{_PROFILE_BASE}/hr-encounter"
PROFILE_ENCOUNTER_MSG_HEADER = f"{_PROFILE_BASE}/hr-encounter-management-message-header"

ENCOUNTER_EVENT_PROFILE_MAP = {
    "1.1": f"{_PROFILE_BASE}/hr-create-encounter-message",
    "1.2": f"{_PROFILE_BASE}/hr-update-encounter-message",
    "1.3": f"{_PROFILE_BASE}/hr-close-encounter-message",
    "1.4": f"{_PROFILE_BASE}/hr-cancel-encounter-message",
    "1.5": f"{_PROFILE_BASE}/hr-reopen-encounter-message",
}

VISIT_ACTION_MAP: dict[str, dict[str, str]] = {
    "close": {"code": "1.3", "status": "finished"},
    "storno": {"code": "1.4", "status": "entered-in-error"},
    "reopen": {"code": "1.5", "status": "in-progress"},
}


def build_encounter_create(
    *,
    patient_mbo: str,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit creation (event code 1.1).

    Uses CEZIH Croatian CodeSystems:
      - Encounter.class: nacin-prijema (method of admission)
    """
    # Match official CEZIH example — field order matches spec
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "subject": patient_ref(patient_mbo),
        "type": [],
    }
    if vrsta_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
        })
    if tip_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
        })
    if not encounter["type"]:
        del encounter["type"]
    if practitioner_id:
        encounter["participant"] = [{
            "individual": practitioner_ref(practitioner_id),
        }]
    encounter["period"] = {"start": _now_iso()}
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    return encounter


def build_encounter_update(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    additional_practitioner_id: str | None = None,
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit update (event code 1.2).

    CEZIH example includes: extension, identifier, class, type, subject, participant,
    period, diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "type": [],
        "subject": patient_ref(patient_mbo),
        "period": {"start": period_start if period_start else _now_iso()},
    }
    if vrsta_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
        })
    if tip_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
        })
    if not encounter["type"]:
        del encounter["type"]
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if practitioner_id:
        participants = [{"individual": practitioner_ref(practitioner_id)}]
        if additional_practitioner_id and additional_practitioner_id != practitioner_id:
            participants.append({"individual": practitioner_ref(additional_practitioner_id)})
        encounter["participant"] = participants
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    return encounter


def build_encounter_close(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit close (event code 1.3).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}

    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "finished",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "period": period,
        "serviceProvider": org_ref(org_code) if org_code else {},
    }
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    if not org_code:
        encounter.pop("serviceProvider", None)
    return encounter


def build_encounter_cancel(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit cancellation/storno (event code 1.4).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "entered-in-error",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}
    encounter["period"] = period
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    return encounter


def build_encounter_reopen(
    *,
    encounter_id: str,
    nacin_prijema: str = "6",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit reopen (event code 1.5).

    Per CEZIH official example: identifier, status, class, serviceProvider only.
    No subject, participant, period, or id fields.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    return encounter


# --- Condition Resource Builders ---


def build_condition_create(
    *,
    patient_mbo: str,
    icd_code: str,
    icd_display: str = "",
    onset_date: str,
    practitioner_id: str,
    verification_status: str = "unconfirmed",
    local_case_id: str | None = None,
    note_text: str | None = None,
) -> dict[str, Any]:
    """Build Condition for create case (message code 2.1).

    Local identifier only — CEZIH assigns global identifier.
    """
    local_id = local_case_id or str(uuid.uuid4())

    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_LOCAL, "value": local_id}],
        "verificationStatus": {
            "coding": [{"system": CS_CONDITION_VER_STATUS, "code": verification_status}],
        },
        "code": {
            "coding": [{"system": CS_ICD10_HR, "code": icd_code, "display": icd_display}],
        },
        "subject": patient_ref(patient_mbo),
        "onsetDateTime": onset_date,
        "asserter": practitioner_ref(practitioner_id),
    }

    if note_text:
        condition["note"] = [
            {
                "extension": [
                    {
                        "url": EXT_ANNOTATION_TYPE,
                        "valueCoding": {"system": CS_ANNOTATION_TYPE, "code": "4"},
                    },
                ],
                "text": note_text,
            },
        ]

    return condition


def build_condition_status_update(
    *,
    case_identifier: str,
    patient_mbo: str,
    clinical_status: str | None = None,
    abatement_date: str | None = None,
) -> dict[str, Any]:
    """Build Condition for case status update (codes 2.3-2.5, 2.7).

    Field requirements per CEZIH `hr-health-issue-resolve-message|0.1` profile
    plus FHIR R4 invariant `con-4` (if abated, clinicalStatus ∈ inactive/
    resolved/remission):

    - 2.3 Remisija: abatementDateTime + clinicalStatus=remission
    - 2.4 Relaps:   clinicalStatus=relapse only (no abatement — relapse is
      a return to active; abatement would violate con-4)
    - 2.5 Resolve:  abatementDateTime + clinicalStatus=resolved
    - 2.7 Reopen:   minimal — no abatement, no clinicalStatus
    """
    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_GLOBAL, "value": case_identifier}],
        "subject": patient_ref(patient_mbo),
    }

    if clinical_status:
        condition["clinicalStatus"] = {
            "coding": [{"system": CS_CONDITION_CLINICAL, "code": clinical_status}],
        }

    if abatement_date:
        condition["abatementDateTime"] = abatement_date

    return condition


def build_condition_data_update(
    *,
    case_identifier: str,
    patient_mbo: str,
    current_clinical_status: str | None = None,
    verification_status: str | None = None,
    icd_code: str | None = None,
    icd_display: str | None = None,
    onset_date: str | None = None,
    abatement_date: str | None = None,
    practitioner_id: str | None = None,
    severity_code: str | None = None,
    severity_display: str | None = None,
    body_site_code: str | None = None,
    body_site_display: str | None = None,
    note_text: str | None = None,
) -> dict[str, Any]:
    """Build Condition for case DATA update (message code 2.6).

    Updates metadata fields WITHOUT changing clinicalStatus.
    Profile says: "clinicalStatus se ne može mijenjati kroz poruku izmjene podataka o slučaju.
    Zbog sukladnosti sa FHIR standardom potrebno je poslati vrijednost trenutnog stanja."
    """
    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_GLOBAL, "value": case_identifier}],
        "subject": patient_ref(patient_mbo),
    }

    # Must echo current clinicalStatus (cannot change it via data update)
    if current_clinical_status:
        condition["clinicalStatus"] = {
            "coding": [{"system": CS_CONDITION_CLINICAL, "code": current_clinical_status}],
        }

    if verification_status:
        condition["verificationStatus"] = {
            "coding": [{"system": CS_CONDITION_VER_STATUS, "code": verification_status}],
        }

    if icd_code:
        condition["code"] = {
            "coding": [{"system": CS_ICD10_HR, "code": icd_code, **({"display": icd_display} if icd_display else {})}],
        }

    if onset_date:
        condition["onsetDateTime"] = onset_date

    if abatement_date:
        condition["abatementDateTime"] = abatement_date

    if practitioner_id:
        condition["asserter"] = practitioner_ref(practitioner_id)

    if severity_code:
        condition["severity"] = {
            "coding": [{"system": "http://snomed.info/sct", "code": severity_code,
                        **({"display": severity_display} if severity_display else {})}],
        }

    if body_site_code:
        condition["bodySite"] = [{
            "coding": [{"system": "http://snomed.info/sct", "code": body_site_code,
                        **({"display": body_site_display} if body_site_display else {})}],
        }]

    if note_text:
        condition["note"] = [{
            "extension": [{
                "url": EXT_ANNOTATION_TYPE,
                "valueCoding": {"system": CS_ANNOTATION_TYPE, "code": "4"},
            }],
            "text": note_text,
        }]

    return condition


# --- Mapping: case action -> message code + clinical status ---

# Delete (2.7) is deliberately NOT wired per product rule — see CLAUDE.md.
# For "mistaken entry" UX: 2.6 Data update with verificationStatus=entered-in-error.
#
# Event codes per Simplifier cezih.hr.condition-management/0.2.1:
#   2.1=Create, 2.2=Create recurrence, 2.3=Remission, 2.4=Resolve,
#   2.5=Relapse, 2.6=Data update, 2.7=Delete (NOT shipped),
#   2.8=Reopen after delete (unreachable), 2.9=Reopen after resolve
CASE_ACTION_MAP: dict[str, dict[str, str | None]] = {
    "create": {"code": "2.1", "clinical_status": None},
    "create_recurring": {"code": "2.2", "clinical_status": None},
    "remission": {"code": "2.3", "clinical_status": "remission"},
    "resolve": {"code": "2.4", "clinical_status": "resolved"},
    "relapse": {"code": "2.5", "clinical_status": "relapse"},
    "update_data": {"code": "2.6", "clinical_status": None},  # Data-only update, no status change
    "reopen": {"code": "2.9", "clinical_status": "active"},
}


# --- Per-event CEZIH profile rules for case status-update messages ---
#
# CEZIH validates each $process-message event code against a DIFFERENT
# StructureDefinition profile (Simplifier cezih.hr.condition-management/0.2.1).
#
# Fields:
#   cs        — include Condition.clinicalStatus
#   cs_value  — code to send when cs=True (e.g. "resolved")
#   abatement — include Condition.abatementDateTime (set to now())
CASE_EVENT_PROFILE: dict[str, dict[str, Any]] = {
    "2.3": {"cs": False, "abatement": False, "cs_value": None},  # Remisija — minimal
    "2.4": {"cs": True,  "abatement": True,  "cs_value": "resolved"},  # Resolve — cs=resolved + abatementDateTime REQUIRED
    "2.5": {"cs": False, "abatement": False, "cs_value": None},  # Relapse — minimal
    "2.9": {"cs": False, "abatement": False, "cs_value": None},  # Reopen after resolve — minimal
    # 2.2 Ponavljajući routes through build_condition_create (hr-create-health-issue-recurrence-message)
    # — handled in service.py update_case, not via this table.
}


# --- Parse response ---

# Croatian user-friendly messages for known CEZIH error codes and patterns.
# Keys are either exact CEZIH error codes (from OperationOutcome.details.coding[0].code)
# or substrings of the English diagnostics text for pattern matches.
_CEZIH_ERROR_MESSAGES_HR: dict[str, str] = {
    "ERR_HEALTH_ISSUE_2004": (
        "CEZIH ne dopušta ovu tranziciju stanja. Provjerite je li slučaj u "
        "ispravnom stanju za ovu akciju (Zatvori — aktivni/potvrđeni, "
        "Relaps — u remisiji, Ponovno otvori — zatvoreni slučaj)."
    ),
    "ERR_DS_1002": (
        "Digitalni potpis ili struktura poruke nije prošla validaciju. "
        "Provjerite da je pametna kartica ispravna i obratite se podršci."
    ),
    "ERR_DOM_10057": (
        "CEZIH ne prihvaća traženi status dokumenta. "
        "Dokument se može otkazati samo kroz zamjenu (replace)."
    ),
    "ERR_EHE_1099": (
        "CEZIH odbija korišteni profil poruke. Koristite standardni "
        "profil umjesto privatnog (npr. HRExternalMinimal)."
    ),
}

_CEZIH_DIAGNOSTIC_PATTERNS_HR: dict[str, str] = {
    "must be 'resolved'": (
        "CEZIH traži status 'Zatvoren' umjesto trenutnog. "
        "Provjerite slijed akcija (neke tranzicije nisu podržane u test okruženju)."
    ),
}


def _translate_cezih_error(error_code: str | None, diagnostics: str | None) -> str:
    """Translate a raw CEZIH error into a Croatian user-friendly message."""
    if error_code and error_code in _CEZIH_ERROR_MESSAGES_HR:
        return _CEZIH_ERROR_MESSAGES_HR[error_code]
    if diagnostics:
        for pattern, hr_msg in _CEZIH_DIAGNOSTIC_PATTERNS_HR.items():
            if pattern in diagnostics:
                return hr_msg
        return diagnostics
    if error_code:
        return f"CEZIH greška ({error_code}). Provjerite log servera za detalje."
    return "Nepoznata CEZIH greška. Provjerite log servera."


def parse_message_response(response_body: dict[str, Any]) -> dict[str, Any]:
    """Parse a CEZIH $process-message response Bundle.

    Returns dict with: success, response_code, identifier (if assigned), error_message.
    error_message is translated to Croatian when the code or diagnostic matches a
    known pattern; otherwise falls back to the raw CEZIH diagnostic.
    """
    result: dict[str, Any] = {
        "success": False,
        "response_code": None,
        "identifier": None,
        "error_message": None,
        "raw": response_body,
    }

    entries = response_body.get("entry", [])
    if not entries:
        result["error_message"] = "CEZIH nije vratio valjan odgovor (prazan Bundle)."
        return result

    header = entries[0].get("resource", {})
    resp_info = header.get("response", {})
    result["response_code"] = resp_info.get("code")
    result["success"] = resp_info.get("code") == "ok"

    # Check for OperationOutcome in second entry
    if len(entries) > 1:
        second = entries[1].get("resource", {})
        if second.get("resourceType") == "OperationOutcome":
            issues = second.get("issue", [])
            for issue in issues:
                if issue.get("severity") in ("error", "fatal"):
                    details = issue.get("details", {}).get("coding", [{}])[0]
                    error_code = details.get("code")
                    diagnostics = issue.get("diagnostics")
                    issue_code = issue.get("code")
                    logger.warning(
                        "CEZIH ERROR DETAIL: code=%s issue_code=%s diagnostics=%s details=%s",
                        error_code, issue_code, diagnostics,
                        json.dumps(details, ensure_ascii=False)[:500],
                    )
                    result["error_message"] = _translate_cezih_error(error_code, diagnostics)
                    result["success"] = False
                    break

        # Check for returned resource with identifier (e.g. CEZIH-assigned visit/case ID)
        rt = second.get("resourceType")
        if rt == "Condition":
            identifiers = second.get("identifier", [])
            for ident in identifiers:
                sys = ident.get("system", "")
                if sys == ID_CASE_GLOBAL:
                    result["identifier"] = ident.get("value")
                    break

    return result
