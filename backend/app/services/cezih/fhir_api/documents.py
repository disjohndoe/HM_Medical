"""CEZIH clinical document service — ITI-65/67/68 MHD document submission/search/retrieval."""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from app.constants import get_cezih_document_coding
from app.services.cezih.builders.bundles import build_iti65_transaction_bundle
from app.services.cezih.builders.clinical_document_bundle import build_clinical_document_bundle
from app.services.cezih.builders.common import (
    ID_CASE_GLOBAL,
    ID_ENCOUNTER,
    ID_ORG,
    ID_PRACTITIONER,
    _now_iso,
)
from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError
from app.services.cezih.fhir_api.identifiers import _require_identifier_system, _require_identifier_value
from app.services.cezih.signing import sign_document_bundle

logger = logging.getLogger(__name__)


async def _build_document_bundle(
    fhir_client: CezihFhirClient,
    patient_data: dict,
    record_data: dict,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    relates_to: dict | None = None,
    use_external_profile: bool = False,
    doc_status: str = "current",
) -> tuple[dict, str]:
    """Build a complete ITI-65 transaction bundle for document submission/replace.

    Returns (bundle_dict, doc_ref_id_placeholder).
    Shared by send_enalaz (TC18) and replace_document (TC19).
    """
    logger.info(
        "ITI-65 build: patient_system=%s encounter_id=%r case_id=%r",
        patient_data.get("identifier_system"),
        encounter_id,
        case_id,
    )

    doc_uuid = str(uuid.uuid4())
    coding = get_cezih_document_coding(record_data.get("tip", "nalaz"))
    patient_display = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}".strip()

    # Generate document OID via CEZIH identifier registry
    oid_result = await fhir_client.post(
        "identifier-registry-services/api/v1/oid/generateOIDBatch",
        json_body={
            "oidType": {
                "system": "http://ent.hr/fhir/CodeSystem/ehe-oid-types",
                "code": "1",
            },
            "quantity": 1,
        },
    )
    logger.info("OID generation response: %s", oid_result)
    oids = oid_result.get("oid") or oid_result.get("oids") or []
    if not oids:
        raise CezihError("OID generation returned empty result", detail=str(oid_result))
    doc_oid = oids[0]
    logger.info("Generated document OID: %s", doc_oid)

    # Build inner FHIR Document Bundle (HRDocument profile) per
    # cezih.hr.klinicki-dokumenti#0.3 IG. HZZO certification rejected plain
    # text/PDF Binary on 2026-05-04 - clinical content must be a signed
    # Bundle.type=document with Composition + supporting resources.
    inner_bundle, attester_practitioner_url = build_clinical_document_bundle(
        patient_data=patient_data,
        record_data=record_data,
        practitioner_id=practitioner_id or "",
        practitioner_name=practitioner_name,
        org_code=org_code,
        org_name=record_data.get("org_name", "") or f"Ustanova {org_code}",
        encounter_id=encounter_id,
        case_id=case_id,
        document_oid=doc_oid,
        document_type_code=coding["code"],
        document_type_display=coding["display"],
    )
    signed_inner_bundle = await sign_document_bundle(inner_bundle, attester_practitioner_url)
    inner_json_bytes = json.dumps(
        signed_inner_bundle, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    clinical_b64 = base64.b64encode(inner_json_bytes).decode("ascii")
    logger.info(
        "Inner Document Bundle: signed signature.data=%d chars, json=%d bytes, base64=%d chars",
        len(signed_inner_bundle.get("signature", {}).get("data", "")),
        len(inner_json_bytes),
        len(clinical_b64),
    )

    _doc_ref_profile = (
        "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternaltMinimalDocumentReference"
        if use_external_profile
        else "http://fhir.cezih.hr/specifikacije/StructureDefinition/HR.MinimalDocumentReference"
    )
    doc_ref_dict: dict = {
        "resourceType": "DocumentReference",
        "meta": {
            "profile": [_doc_ref_profile],
        },
        "masterIdentifier": {
            "use": "usual",
            "system": "urn:ietf:rfc:3986",
            "value": f"urn:oid:{doc_oid}" if doc_oid else f"urn:uuid:{doc_uuid}",
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{doc_uuid}",
            }
        ],
        "status": doc_status,
        "type": {
            "coding": [
                {
                    "system": coding["system"],
                    "code": coding["code"],
                    "display": coding["display"],
                }
            ]
        },
        "subject": {
            "type": "Patient",
            "identifier": {
                "system": _require_identifier_system(patient_data),
                "value": _require_identifier_value(patient_data),
            },
            "display": patient_display,
        },
        "date": _now_iso(),
        "author": [],
    }

    # Author: practitioner (HZJZ ID) — CEZIHDR-004 requires display (name)
    if practitioner_id:
        author_practitioner: dict = {
            "type": "Practitioner",
            "identifier": {
                "system": ID_PRACTITIONER,
                "value": practitioner_id,
            },
        }
        if practitioner_name:
            author_practitioner["display"] = practitioner_name
        doc_ref_dict["author"].append(author_practitioner)

    # Author: organization (HZZO code)
    if org_code:
        doc_ref_dict["author"].append(
            {
                "type": "Organization",
                "identifier": {
                    "system": ID_ORG,
                    "value": org_code,
                },
            }
        )

    # Authenticator (CEZIHDR-001: odgovorna osoba) — display required (min:1)
    if practitioner_id:
        doc_ref_dict["authenticator"] = {
            "type": "Practitioner",
            "identifier": {
                "system": ID_PRACTITIONER,
                "value": practitioner_id,
            },
            "display": practitioner_name or practitioner_id,
        }

    # Custodian: organization — display required (min:1)
    if org_code:
        doc_ref_dict["custodian"] = {
            "identifier": {
                "system": ID_ORG,
                "value": org_code,
            },
            "display": f"Ustanova {org_code}",
        }

    # Context: encounter, case, period, practiceSetting (CEZIHDR-005/006/008/011)
    context: dict = {
        "period": {
            "start": record_data.get("created_at", _now_iso()),
            "end": _now_iso(),
        },
        "practiceSetting": {
            "coding": [
                {
                    "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/djelatnosti-zz",
                    "code": "1010000",
                    "display": "Opća/obiteljska medicina",
                }
            ]
        },
    }
    if encounter_id:
        context["encounter"] = [
            {
                "type": "Encounter",
                "identifier": {
                    "system": ID_ENCOUNTER,
                    "value": encounter_id,
                },
            }
        ]
    if case_id:
        context["related"] = [
            {
                "type": "Condition",
                "identifier": {
                    "system": ID_CASE_GLOBAL,
                    "value": case_id,
                },
            }
        ]
    doc_ref_dict["context"] = context

    # relatesTo for replace operations (TC19)
    if relates_to:
        doc_ref_dict["relatesTo"] = [relates_to]

    # Content: Binary resource holding the signed inner FHIR Document Bundle
    # (Bundle.type=document) as base64-encoded application/fhir+json. Per
    # IHE MHD inline data is forbidden on attachment (max=0); content lives
    # in a separate Binary resource referenced via urn:uuid URL.
    binary_uuid = str(uuid.uuid4())
    binary_resource: dict = {
        "resourceType": "Binary",
        "contentType": "application/json",
        "data": clinical_b64,
    }
    doc_ref_dict["content"] = [
        {
            "attachment": {
                "contentType": "application/fhir+json",
                "language": "hr-HR",
                "url": f"urn:uuid:{binary_uuid}",
            }
        }
    ]

    # Build IHE MHD ITI-65 transaction bundle
    entries = [doc_ref_dict]
    binary_resource["_uuid"] = binary_uuid
    entries.append(binary_resource)

    _bundle_profile = None
    _ss_profile = None
    if use_external_profile:
        _bundle_profile = (
            "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternalMinimalProvideDocumentBundle"
        )
        _ss_profile = "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternalMinimalSubmissionSet"

    bundle_dict = build_iti65_transaction_bundle(
        entries,
        sender_org_code=org_code,
        author_practitioner_id=practitioner_id,
        bundle_profile=_bundle_profile,
        submission_set_profile=_ss_profile,
    )

    return bundle_dict, doc_oid or doc_uuid


def _extract_ref_id_from_response(response: dict) -> str:
    """Extract DocumentReference ID from an ITI-65 transaction response.

    FHIR transaction responses have entry[].response.location with the
    server-assigned resource URL (e.g. "DocumentReference/abc123").
    Also checks entry[].resource.id as fallback.
    """
    if response.get("resourceType") == "DocumentReference":
        return response.get("id", "")
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            # Transaction response: entry.response.location = "DocumentReference/ID"
            resp_entry = entry.get("response", {})
            location = resp_entry.get("location", "")
            if "DocumentReference" in location:
                # Extract ID from "DocumentReference/abc123" or full URL
                parts = location.rstrip("/").split("/")
                idx = next((i for i, p in enumerate(parts) if p == "DocumentReference"), -1)
                if idx >= 0 and idx + 1 < len(parts):
                    return parts[idx + 1]
            # Fallback: resource embedded in response
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "DocumentReference":
                return resource.get("id", "")
    return ""


async def send_enalaz(
    client: httpx.AsyncClient,
    patient_data: dict,
    record_data: dict,
    practitioner_id: str | None = None,
    org_code: str = "",
    source_oid: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
) -> dict:
    """Send clinical document / finding (ITI-65 MHD)."""
    fhir_client = CezihFhirClient(client)

    # Outer ITI-65 transaction bundle (HRMinimalProvideDocumentBundle) is NOT
    # signed - signing happens on the inner HRDocument Bundle inside the Binary.
    bundle_dict, doc_oid = await _build_document_bundle(
        fhir_client,
        patient_data,
        record_data,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
    )

    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    logger.info("ITI-65 response: %s", json.dumps(response, ensure_ascii=False, default=str)[:3000])

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    logger.info("Extracted document reference ID: %s", ref_id)

    return {
        "success": True,
        "reference_id": ref_id,
        "document_oid": doc_oid,
        "sent_at": datetime.now(UTC).isoformat(),
    }


def _extract_codeable_text(concept: dict | None) -> str:
    """Extract display text from a FHIR CodeableConcept."""
    if not concept:
        return ""
    if concept.get("text"):
        return concept["text"]
    codings = concept.get("coding", [])
    if codings:
        return codings[0].get("display", codings[0].get("code", ""))
    return ""


def _extract_reference_display(ref: dict | str | None) -> str:
    """Extract display from a FHIR Reference or reference-like dict."""
    if not ref or isinstance(ref, str):
        return ""
    return ref.get("display", ref.get("reference", ""))


def _map_fhir_status(status: str) -> str:
    """Map FHIR DocumentReference status to our domain status."""
    mapping = {
        "current": "Otvorena",
        "superseded": "Zatvorena",
        "entered-in-error": "Pogreška",
    }
    return mapping.get(status, status)


async def search_documents(
    client: httpx.AsyncClient,
    *,
    patient_system: str | None = None,
    patient_value: str | None = None,
    document_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    """Search clinical documents (ITI-67 MHD — flexible parameters for TC21).

    Supports search by patient (system+value), document type, date range, status.
    """
    fhir_client = CezihFhirClient(client)
    params: dict = {}

    if patient_system and patient_value:
        params["patient.identifier"] = f"{patient_system}|{patient_value}"
    if document_type:
        params["type"] = f"http://fhir.cezih.hr/specifikacije/vrste-dokumenata|{document_type}"
    if date_from:
        params["date"] = f"ge{date_from}"
    if date_to:
        params["date"] = params.get("date", "") + f"&date=le{date_to}" if "date" in params else f"le{date_to}"
    # CEZIH requires status parameter — default to "current" if not specified
    params["status"] = status_filter or "current"

    try:
        response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)
    except Exception as exc:
        logger.error("Document search failed: %s", exc)
        raise CezihError(f"Pretraga dokumenata nije uspjela: {exc}") from exc

    items = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            doc_ref = entry.get("resource", {})
            try:
                author = ""
                for a in doc_ref.get("author", []):
                    author = a.get("display", "") or author
                # Extract content URL for ITI-68 retrieve
                content_url = ""
                for content in doc_ref.get("content", []):
                    att = content.get("attachment", {})
                    if att.get("url"):
                        content_url = att["url"]
                        break
                items.append(
                    {
                        "id": doc_ref.get("id", ""),
                        "datum_izdavanja": doc_ref.get("date", ""),
                        "izdavatelj": author or _extract_reference_display(doc_ref.get("custodian")),
                        "svrha": _extract_codeable_text(doc_ref.get("type")),
                        "specijalist": author,
                        "status": _map_fhir_status(doc_ref.get("status", "current")),
                        "type": _extract_codeable_text(doc_ref.get("type")),
                        "content_url": content_url,
                    }
                )
            except Exception as parse_exc:
                logger.warning("Skipping unparseable DocumentReference: %s", parse_exc)
                continue

    return items


async def replace_document(
    client: httpx.AsyncClient,
    original_reference_id: str,
    patient_data: dict,
    record_data: dict,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    original_document_oid: str = "",
) -> dict:
    """Replace a clinical document (TC19, ITI-65 transaction bundle with relatesTo).

    relatesTo.target uses logical identifier reference with the original document's OID.
    CEZIH resolves relatesTo by OID (masterIdentifier), NOT by server-assigned numeric ID.
    """
    fhir_client = CezihFhirClient(client)

    # Look up document OID from CEZIH if not provided
    if not original_document_oid and _require_identifier_value(patient_data):
        original_document_oid = await _lookup_document_oid(
            fhir_client,
            original_reference_id,
            _require_identifier_value(patient_data),
            identifier_system=_require_identifier_system(patient_data),
        )

    if original_document_oid:
        oid_value = (
            original_document_oid
            if original_document_oid.startswith("urn:oid:")
            else f"urn:oid:{original_document_oid}"
        )
        relates_to = {
            "code": "replaces",
            "target": {
                "type": "DocumentReference",
                "identifier": {
                    "system": "urn:ietf:rfc:3986",
                    "value": oid_value,
                },
            },
        }
    else:
        relates_to = {
            "code": "replaces",
            "target": {
                "reference": f"DocumentReference/{original_reference_id}",
            },
        }

    bundle_dict, new_oid = await _build_document_bundle(
        fhir_client,
        patient_data,
        record_data,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
        relates_to=relates_to,
        use_external_profile=False,  # External profiles (v1.0.1) rejected by CEZIH test env with 415
    )

    # Outer ITI-65 transaction is not signed; signing is on the inner Document Bundle.
    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-R-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    return {
        "success": True,
        "new_reference_id": ref_id,
        "new_document_oid": new_oid,
        "replaced_reference_id": original_reference_id,
    }


async def _lookup_document_oid(
    fhir_client: CezihFhirClient,
    reference_id: str,
    patient_mbo: str,
    identifier_system: str,
) -> str:
    """Look up a document's OID from CEZIH via ITI-67 search.

    CEZIH content_url contains base64-encoded data param with the OID:
    documentUniqueId=urn:ietf:rfc:3986|urn:oid:2.16.840.1.113883.2.7.50.2.1.XXXXXX
    """
    try:
        params = {
            "patient.identifier": f"{identifier_system}|{patient_mbo}",
            "status": "current",
        }
        response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)
        for entry in response.get("entry", []):
            doc_ref = entry.get("resource", {})
            if doc_ref.get("id") == reference_id:
                # Extract OID from content_url base64 data param
                for content in doc_ref.get("content", []):
                    url = content.get("attachment", {}).get("url", "")
                    if not url:
                        continue
                    parsed = urlparse(url)
                    qs = parse_qs(parsed.query)
                    data_val = qs.get("data", [""])[0]
                    if data_val:
                        decoded = base64.b64decode(data_val).decode("utf-8", errors="replace")
                        # Format: documentUniqueId=urn:ietf:rfc:3986|urn:oid:X.X.X&position=0
                        for part in decoded.split("&"):
                            if part.startswith("documentUniqueId="):
                                uid = part.split("=", 1)[1]
                                # Extract the urn:oid: part after the pipe
                                if "|" in uid:
                                    oid = uid.split("|", 1)[1]
                                    logger.info("TC20: Resolved OID for document %s: %s", reference_id, oid)
                                    return oid
                # Fallback: check masterIdentifier directly
                master_id = doc_ref.get("masterIdentifier", {})
                val = master_id.get("value", "")
                if val.startswith("urn:oid:"):
                    logger.info("TC20: Found OID from masterIdentifier for %s: %s", reference_id, val)
                    return val
    except Exception as e:
        logger.warning("TC20: OID lookup failed for document %s: %s", reference_id, e)

    return ""


async def cancel_document(
    client: httpx.AsyncClient,
    reference_id: str,
    patient_data: dict,
    record_data: dict,
    org_code: str = "",
    practitioner_id: str | None = None,
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    original_document_oid: str = "",
) -> dict:
    """Cancel/storno a clinical document (TC20).

    Storno is an ITI-65 transaction bundle with `relatesTo.code=replaces`
    pointing at the original document by OID (masterIdentifier). CEZIH
    resolves relatesTo by OID, not by server-assigned numeric ID.

    DocumentReference.status stays `current` (the default for `_build_document_bundle`).
    The Klinicki Dokumenti vodič suggests `entered-in-error`, but the live
    CEZIH test environment rejects that with `ERR_DOM_10057` (verified
    2026-04-13, see `docs/CEZIH/findings/TC20-cancel-document-blocker.md`)
    and HZZO's 2026-05-04 rejection email did not raise storno as an issue,
    so we keep the verified-green mechanism unchanged.
    """
    fhir_client = CezihFhirClient(client)

    # Look up document OID from CEZIH - relatesTo target needs OID, not numeric ID.
    if not original_document_oid:
        original_document_oid = await _lookup_document_oid(
            fhir_client,
            reference_id,
            _require_identifier_value(patient_data),
            identifier_system=_require_identifier_system(patient_data),
        )
    if not original_document_oid:
        raise CezihError(
            f"TC20 cancel: nije moguće pronaći OID dokumenta {reference_id} u CEZIH-u "
            "(ITI-67 search nije vratio masterIdentifier). Storno se ne može poslati "
            "bez OID-a originalnog dokumenta."
        )

    oid_value = (
        original_document_oid
        if original_document_oid.startswith("urn:oid:")
        else f"urn:oid:{original_document_oid}"
    )
    relates_to = {
        "code": "replaces",
        "target": {
            "type": "DocumentReference",
            "identifier": {
                "system": "urn:ietf:rfc:3986",
                "value": oid_value,
            },
        },
    }

    bundle_dict, new_oid = await _build_document_bundle(
        fhir_client,
        patient_data,
        record_data,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
        relates_to=relates_to,
        use_external_profile=False,
    )

    # Outer ITI-65 transaction is not signed (signing is on the inner Document Bundle).
    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-C-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    return {
        "success": True,
        "reference_id": reference_id,
        "new_reference_id": ref_id,
        "new_document_oid": new_oid,
        "status": "current",
    }


async def retrieve_document(client: httpx.AsyncClient, document_url: str) -> bytes:
    """Retrieve a clinical document binary content (TC22, ITI-68).

    If document_url is a full URL (starts with http), fetch it directly.
    Otherwise, use the ITI-68 service endpoint with the reference ID.
    """
    fhir_client = CezihFhirClient(client)

    if document_url.startswith("http"):
        # Full URL from DocumentReference.content.attachment.url — fetch directly
        # Strip the base URL prefix if it matches our CEZIH gateway path
        # Extract the path after the gateway prefix
        match = re.search(r"/services-router/gateway/(.+)", document_url)
        if match:
            # Relative path within CEZIH gateway
            path_with_query = match.group(1)
            # Split path and query
            if "?" in path_with_query:
                path, query_string = path_with_query.split("?", 1)
                params = {k: v[0] for k, v in parse_qs(query_string).items()}
            else:
                path = path_with_query
                params = {}
            response = await fhir_client.get(path, params=params, accept="*/*")
        else:
            response = await fhir_client.get(
                "doc-mhd-svc/api/v1/iti-68-service",
                params={"url": document_url},
                accept="*/*",
            )
    else:
        # Reference ID — look up DocumentReference first to get content_url (ITI-67 by ID)
        # CEZIH does not expose Binary/{id} directly; content URL is in DocumentReference.content
        content_url = ""
        try:
            doc_ref = await fhir_client.get(f"doc-mhd-svc/api/v1/DocumentReference/{document_url}")
            for content_entry in doc_ref.get("content", []):
                att = content_entry.get("attachment", {})
                if att.get("url"):
                    content_url = att["url"]
                    break
        except Exception as lookup_exc:
            logger.warning("DocumentReference lookup failed for %s: %s", document_url, lookup_exc)

        if content_url:
            # Recurse with the resolved full URL
            return await retrieve_document(client, content_url)

        # Last resort: try Binary/{id} directly
        response = await fhir_client.get(
            f"doc-mhd-svc/api/v1/Binary/{document_url}",
            accept="*/*",
        )

    if isinstance(response, bytes):
        size = len(response)
        is_pdf = response.startswith(b"%PDF")
        preview = response[:200] if size > 0 else b""
        logger.info(
            "retrieve_document returning bytes: %d bytes, is_pdf=%s, preview=%r",
            size,
            is_pdf,
            preview,
        )
        return response
    content = response.get("data", b"") if isinstance(response, dict) else b""
    final_content = content if isinstance(content, bytes) else content.encode("utf-8")
    size = len(final_content)
    is_pdf = final_content.startswith(b"%PDF")
    preview = final_content[:200] if size > 0 else b""
    logger.info(
        "retrieve_document returning extracted: %d bytes, is_pdf=%s, preview=%r",
        size,
        is_pdf,
        preview,
    )
    return final_content


__all__ = [
    "_build_document_bundle",
    "_extract_ref_id_from_response",
    "send_enalaz",
    "_extract_codeable_text",
    "_extract_reference_display",
    "_map_fhir_status",
    "search_documents",
    "replace_document",
    "_lookup_document_oid",
    "cancel_document",
    "retrieve_document",
]
