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


async def add_signature(
    bundle: dict[str, Any],
    practitioner_id: str,
    sign_fn: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Add a digital signature to the Bundle per CEZIH JWS format.

    Two signing methods (controlled by CEZIH_SIGNING_METHOD):
    - "smartcard": Agent signs locally via NCrypt + AKD smart card
    - "extsigner": CEZIH signs remotely via Certilia (user approves on phone)

    For smartcard:
      signature.data = base64(JWS_compact) — double base64 for HAPI compatibility.

    For extsigner:
      Send full bundle to extsigner API → CEZIH signs with Certilia cloud cert.
      Response contains the signed document (signature already embedded by CEZIH).
    """
    import base64 as _base64
    from app.config import settings

    signing_method = settings.CEZIH_SIGNING_METHOD

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
        f"Extsigner returned unexpected response format. "
        f"Keys: {list(response.keys())}. Check backend logs."
    )


async def _add_signature_smartcard(
    bundle: dict[str, Any],
    practitioner_id: str,
    sign_fn: Any = None,
) -> dict[str, Any]:
    """Sign bundle via agent's smart card (NCrypt JWS signing).

    Signing payload includes the signature element with data="" (empty).
    This matches the pattern used for working encounter/case signatures.
    """
    import base64 as _base64
    from app.services.agent_connection_manager import agent_manager
    from app.services.cezih.client import current_tenant_id

    # Add signature structure with data="" placeholder before serializing.
    # The JWS payload includes this placeholder (same as encounters).
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

    # Serialize bundle to compact JSON (includes signature with data="").
    bundle_json_bytes = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    if sign_fn:
        # Test hook — custom sign function
        result = await sign_fn(bundle_json_bytes)
        jws_base64 = result.get("jws_base64", "")
    else:
        # Production: use agent's JWS signing (builds JOSE header with x5c + signs)
        tenant_id = current_tenant_id.get()
        data_b64 = _base64.b64encode(bundle_json_bytes).decode("ascii")

        result = await agent_manager.sign_jws(
            tenant_id,
            data_base64=data_b64,
            timeout=30.0,
        )

        if "error" in result:
            from app.services.cezih.exceptions import CezihSigningError
            raise CezihSigningError(f"Agent JWS signing failed: {result['error']}")

        jws_base64 = result.get("jws_base64", "")
        if not jws_base64:
            from app.services.cezih.exceptions import CezihSigningError
            raise CezihSigningError("Agent returned empty JWS signature")

        logger.info("JWS signature: kid=%s, alg=%s, data=%d chars",
                     result.get("kid", "?"), result.get("algorithm", "?"), len(jws_base64))

    # Replace the empty data placeholder with the actual JWS signature.
    # Agent returns base64(JWS_compact) — "double base64" for FHIR base64Binary.
    logger.info("JWS double-b64: %d chars", len(jws_base64))
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


def build_condition_delete(
    *,
    case_identifier: str,
    patient_mbo: str,
) -> dict[str, Any]:
    """Build minimal Condition for delete case (message code 2.8)."""
    return {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_GLOBAL, "value": case_identifier}],
        "subject": patient_ref(patient_mbo),
    }


# --- Mapping: case action -> message code + clinical status ---

CASE_ACTION_MAP: dict[str, dict[str, str | None]] = {
    "create": {"code": "2.1", "clinical_status": None},
    "create_recurring": {"code": "2.2", "clinical_status": None},
    "remission": {"code": "2.3", "clinical_status": "remission"},
    "relapse": {"code": "2.4", "clinical_status": "relapse"},
    "resolve": {"code": "2.5", "clinical_status": "resolved"},
    "update_data": {"code": "2.6", "clinical_status": None},  # Data-only update, no status change
    "reopen": {"code": "2.7", "clinical_status": "active"},
    "delete": {"code": "2.8", "clinical_status": None},
}


# --- Per-event CEZIH profile rules for case status-update messages ---
#
# CEZIH validates each $process-message event code against a DIFFERENT
# StructureDefinition profile. This table encodes the payload shape each
# profile requires. See docs/CEZIH/findings/case-lifecycle-profile-matrix.md
# for live-testing evidence.
#
# CEZIH test env has SWAPPED the 2.4/2.5 profile routing (verified 2026-04-16):
#   Event 2.4 (Relaps)  validates against hr-health-issue-resolve-message  → demands cs=resolved + abatement
#   Event 2.5 (Resolve) validates against hr-health-issue-relapse-message  → forbids cs, forbids abatement
# So the shipping table below sends a "resolve-shaped" payload for 2.4 and
# MINIMAL payload for 2.5. Both verified working against live test env.
#
# Fields:
#   cs        — include Condition.clinicalStatus
#   cs_value  — code to send when cs=True (e.g. "resolved", "active")
#   abatement — include Condition.abatementDateTime (set to now())
CASE_EVENT_PROFILE: dict[str, dict[str, Any]] = {
    "2.3": {"cs": False, "abatement": False, "cs_value": None},  # Remisija — VERIFIED 2026-04-16
    "2.4": {"cs": True,  "abatement": True,  "cs_value": "resolved"},  # Relaps — VERIFIED 2026-04-16 (test-env swap)
    "2.5": {"cs": False, "abatement": False, "cs_value": None},  # Resolve — MINIMAL per test-env swap
    "2.7": {"cs": False, "abatement": False, "cs_value": None},  # Reopen — untested probe value
    # 2.2 Ponavljajući routes through build_condition_create (hr-create-health-issue-recurrence-message)
    # — handled in service.py update_case, not via this table.
}

# 2026-04-16: set to False per user decision — prefer working Relaps button
# over honest failure. CEZIH test env routes 2.4 to the resolve-message
# profile, so we send cs=resolved + abatementDateTime. CEZIH returns 200
# and stores the case as resolved; FE surfaces it as "Zatvoren". Accept
# this as the cost of shipping a working button until HZZO fixes routing.
# Flip to True once HZZO documents the real relapse profile URL.
CEZIH_RELAPSE_SEMANTIC_CORRECT = False


# --- Parse response ---


def parse_message_response(response_body: dict[str, Any]) -> dict[str, Any]:
    """Parse a CEZIH $process-message response Bundle.

    Returns dict with: success, response_code, identifier (if assigned), error_message.
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
        result["error_message"] = "Empty response bundle"
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
                    error_code = details.get("code", "unknown")
                    result["error_message"] = (
                        issue.get("diagnostics") or f"Error code: {error_code}"
                    )
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
