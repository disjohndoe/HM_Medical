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

from app.constants import CEZIH_DOCUMENT_TYPE_SYSTEM, get_cezih_document_coding
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
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    org_name: str = "",
    relates_to: dict | None = None,
    use_external_profile: bool = False,
    doc_status: str = "current",
    nacin_prijema: str = "6",
    procedures: list[dict] | None = None,
    attachments: list[dict] | None = None,
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
        org_name=org_name or f"Ustanova {org_code}",
        encounter_id=encounter_id,
        case_id=case_id,
        document_oid=doc_oid,
        document_type_code=coding["code"],
        document_type_display=coding["display"],
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        nacin_prijema=nacin_prijema,
        procedures=procedures,
        attachments=attachments,
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
        "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternalMinimalDocumentReference"
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
            ],
            "text": coding["display"],
        },
        "category": [
            {
                "coding": [
                    {
                        "system": coding["system"],
                        "code": coding["code"],
                        "display": coding["display"],
                    }
                ]
            }
        ],
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

    # Author: organization (HZZO code) — display required per canonical examples
    if org_code:
        doc_ref_dict["author"].append(
            {
                "type": "Organization",
                "identifier": {
                    "system": ID_ORG,
                    "value": org_code,
                },
                "display": org_name or f"Ustanova {org_code}",
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

    # Custodian: organization — type + display required per canonical examples
    if org_code:
        doc_ref_dict["custodian"] = {
            "type": "Organization",
            "identifier": {
                "system": ID_ORG,
                "value": org_code,
            },
            "display": org_name or f"Ustanova {org_code}",
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
                    "code": djelatnost_code,
                    "display": djelatnost_display,
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
        "contentType": "application/fhir+json",
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


def build_cancel_bundle(
    *,
    patient_data: dict,
    record_data: dict,
    original_document_oid: str,
    djelatnost_code: str,
    djelatnost_display: str,
    practitioner_id: str | None = None,
    practitioner_name: str = "",
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    org_name: str = "",
) -> dict:
    """Build a canonical HRCancelDocumentBundle (2-entry ITI-65 cancel).

    Matches the Klinicki Dokumenti IG: SubmissionSet + DocumentReference
    with status=entered-in-error and masterIdentifier=original doc OID.
    No Binary, no signing, no OID generation, no relatesTo.
    """
    oid_value = (
        original_document_oid
        if original_document_oid.startswith("urn:oid:")
        else f"urn:oid:{original_document_oid}"
    )
    coding = get_cezih_document_coding(record_data.get("tip", "nalaz"))
    patient_display = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}".strip()
    doc_uuid = str(uuid.uuid4())

    # Shape matches 2026-05-13 verified-green cascade cancel (commit 3b7e6bf).
    # CEZIH applies HRMinimalProvideDocumentBundle by default at iti-65-service
    # (Bundle.entry slicing is CLOSED), so the DocumentReference must carry
    # the same fields a regular submission carries (category, practiceSetting)
    # to match the Documents slice. The previous attempt to mirror the canonical
    # Bundle-ITI-65-Cancel.json IG sample (no category, no practiceSetting,
    # no profile assertion) was rejected with Validation_VAL_Profile_NotSlice.
    doc_ref_dict: dict = {
        "resourceType": "DocumentReference",
        "meta": {
            "profile": [
                "http://fhir.cezih.hr/specifikacije/StructureDefinition/HR.MinimalDocumentReference"
            ],
        },
        "masterIdentifier": {
            "use": "usual",
            "system": "urn:ietf:rfc:3986",
            "value": oid_value,
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{doc_uuid}",
            }
        ],
        "status": "entered-in-error",
        "type": {
            "coding": [
                {
                    "system": coding["system"],
                    "code": coding["code"],
                    "display": coding["display"],
                }
            ],
            "text": coding["display"],
        },
        "category": [
            {
                "coding": [
                    {
                        "system": coding["system"],
                        "code": coding["code"],
                        "display": coding["display"],
                    }
                ]
            }
        ],
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

    if org_code:
        doc_ref_dict["author"].append(
            {
                "type": "Organization",
                "identifier": {
                    "system": ID_ORG,
                    "value": org_code,
                },
                "display": org_name or f"Ustanova {org_code}",
            }
        )

    if practitioner_id:
        doc_ref_dict["authenticator"] = {
            "type": "Practitioner",
            "identifier": {
                "system": ID_PRACTITIONER,
                "value": practitioner_id,
            },
            "display": practitioner_name or practitioner_id,
        }

    if org_code:
        doc_ref_dict["custodian"] = {
            "type": "Organization",
            "identifier": {
                "system": ID_ORG,
                "value": org_code,
            },
            "display": org_name or f"Ustanova {org_code}",
        }

    # Cancel context mirrors the regular submission (encounter, case, period,
    # practiceSetting) so the DocumentReference matches the Documents slice
    # of HRMinimalProvideDocumentBundle. djelatnost is sourced from the
    # caller-resolved tenant/user override.
    context: dict = {
        "period": {
            "start": record_data.get("created_at", _now_iso()),
            "end": _now_iso(),
        },
        "practiceSetting": {
            "coding": [
                {
                    "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/djelatnosti-zz",
                    "code": djelatnost_code,
                    "display": djelatnost_display,
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

    # Placeholder content - matches canonical Bundle-ITI-65-Cancel.json from cezih.hr.klinicki-dokumenti v0.3.
    # HRCancelDocumentBundle forbids the Documents slice (Bundle.entry:Documents max=0), so this
    # attachment.url is an intentional dangling urn:uuid with no Binary entry backing it.
    content_uuid = str(uuid.uuid4())
    doc_ref_dict["content"] = [
        {
            "attachment": {
                "contentType": "application/fhir+json",
                "language": "hr",
                "url": f"urn:uuid:{content_uuid}",
            }
        }
    ]

    doc_ref_dict["_uuid"] = doc_uuid

    bundle_dict = build_iti65_transaction_bundle(
        [doc_ref_dict],
        sender_org_code=org_code,
        author_practitioner_id=practitioner_id,
    )

    return bundle_dict


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
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    practitioner_id: str | None = None,
    org_code: str = "",
    source_oid: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    org_name: str = "",
    procedures: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Send clinical document / finding (ITI-65 MHD)."""
    fhir_client = CezihFhirClient(client)

    # Outer ITI-65 transaction bundle (HRMinimalProvideDocumentBundle) is NOT
    # signed - signing happens on the inner HRDocument Bundle inside the Binary.
    bundle_dict, doc_oid = await _build_document_bundle(
        fhir_client,
        patient_data,
        record_data,
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
        org_name=org_name,
        procedures=procedures,
        attachments=attachments,
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
        "current": "Otvoreni",
        "superseded": "Zatvoreni",
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
        # CEZIH stores types in HRTipDokumenta (CEZIH_DOCUMENT_TYPE_SYSTEM)
        # with codes 011-013 for privatnici, not under "vrste-dokumenata" with
        # mnemonic strings. The UI passes the alias "nalaz" (per
        # CEZIH_DOCUMENT_TYPE_MAP) which on the wire must expand to 011 +
        # 012 - the two clinical-finding privatnik codes. Comma-separated
        # values give an OR over the type token.
        if document_type == "nalaz":
            params["type"] = ",".join(
                f"{CEZIH_DOCUMENT_TYPE_SYSTEM}|{c}" for c in ("011", "012")
            )
        else:
            params["type"] = f"{CEZIH_DOCUMENT_TYPE_SYSTEM}|{document_type}"
    if date_from:
        params["date"] = f"ge{date_from}"
    if date_to:
        params["date"] = params.get("date", "") + f"&date=le{date_to}" if "date" in params else f"le{date_to}"
    # CEZIH requires status parameter — default to "current" if not specified
    params["status"] = status_filter or "current"
    # Ask for a single large page up front. CEZIH HAPI's own Bundle.link[rel=next]
    # is currently broken for searches without a type filter (returns HTTP 400
    # with empty body when followed), so we cannot paginate via collect_all_pages
    # without regressing section 5 / Pretraga. _count=200 covers any realistic
    # outpatient document count for one patient + status combo.
    # TODO(cezih): follow up with HZZO on next-link bug, then restore paging.
    params["_count"] = 200

    try:
        response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)
    except Exception as exc:
        logger.error("Document search failed: %s", exc)
        raise CezihError(f"Pretraga dokumenata nije uspjela: {exc}") from exc

    items = []
    if response.get("resourceType") == "Bundle":
        if any((link or {}).get("relation") == "next" for link in response.get("link") or []):
            logger.warning(
                "CEZIH document search returned a next link but pagination is "
                "disabled due to upstream HAPI bug; results may be truncated "
                "at %d entries.",
                len(response.get("entry") or []),
            )
        for entry in (response.get("entry") or []):
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


async def list_active_documents_on_encounter(
    client: httpx.AsyncClient,
    *,
    encounter_id: str,
    patient_system: str,
    patient_value: str,
) -> list[dict]:
    """Every `status=current` DocumentReference CEZIH still ties to this Encounter.

    CEZIH — not our local mirror — is the source of truth for what blocks a visit
    storno (msg 1.4 → ERR_ENCOUNTER_2001). Our `medical_records` mirror loses refs
    in normal use: a doctor edit (amend) creates a NEW `current` doc and repoints
    the row to it, but if the row is edited again, re-linked to another case, or the
    new ref is otherwise not captured, the earlier amended doc stays `current` on the
    Encounter while no local row points at it (orphan). The storno cascade must cancel
    EVERY current doc on the Encounter regardless of type or local visibility, so we
    ask CEZIH directly (ITI-67) and match `context.encounter`.

    Only `status=current` docs are returned — those are the cancellable blockers.
    `superseded` predecessors (legacy ITI-65 replace) are deliberately excluded: CEZIH
    refuses to cancel them (ERR_DOM_10035), so they are a separate, un-remediable
    deadlock handled upstream, not something to attempt here.

    Returns `[{reference_id, oid, tip, case_id}]` in CEZIH order.
    """
    if not encounter_id:
        return []
    fhir_client = CezihFhirClient(client)
    try:
        response = await fhir_client.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={
                "patient.identifier": f"{patient_system}|{patient_value}",
                "status": "current",
                "_count": 200,
            },
        )
    except Exception as exc:
        # A storno preflight that cannot reach CEZIH must NOT silently proceed as if
        # no docs block it (that would leave orphans and let the 1.4 fail). Surface it.
        logger.error("Encounter-doc lookup failed for %s: %s", encounter_id, exc)
        raise CezihError(
            f"Provjera nalaza vezanih uz posjet nije uspjela: {exc}"
        ) from exc

    out: list[dict] = []
    if not isinstance(response, dict) or response.get("resourceType") != "Bundle":
        return out
    for entry in response.get("entry") or []:
        doc_ref = entry.get("resource") or {}
        if doc_ref.get("resourceType") != "DocumentReference":
            continue
        ctx = doc_ref.get("context") or {}
        enc_values = [
            (e.get("identifier") or {}).get("value")
            for e in (ctx.get("encounter") or [])
        ]
        if encounter_id not in enc_values:
            continue
        case_id = ""
        for rel in ctx.get("related") or []:
            val = (rel.get("identifier") or {}).get("value")
            if val:
                case_id = val
                break
        out.append(
            {
                "reference_id": doc_ref.get("id", ""),
                "oid": _extract_oid_from_docref(doc_ref),
                "tip": _extract_codeable_text(doc_ref.get("type")),
                "case_id": case_id,
            }
        )
    return out


async def replace_document(
    client: httpx.AsyncClient,
    original_reference_id: str,
    patient_data: dict,
    record_data: dict,
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    original_document_oid: str = "",
    org_name: str = "",
    procedures: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Replace a clinical document (TC19, ITI-65 transaction bundle with relatesTo).

    relatesTo.target uses logical identifier reference with the original document's OID.
    CEZIH resolves relatesTo by OID (masterIdentifier), NOT by server-assigned numeric ID.
    """
    fhir_client = CezihFhirClient(client)

    # Resolve the LIVE current head before building relatesTo. Replacing against
    # a stored OID that CEZIH has already superseded (or against an
    # entered-in-error doc) returns ERR_DOM_10035 - the same failure class the
    # cancel path now guards against. Never trust a stored OID without a live
    # check (2026-05-20 provjera stale-OID failure).
    identifier_value = _require_identifier_value(patient_data)
    identifier_system = _require_identifier_system(patient_data)
    live = await _resolve_live_document_head(
        fhir_client, original_reference_id, identifier_system, identifier_value
    )

    if live["state"] == "entered-in-error":
        raise CezihError(
            f"e-Nalaz {original_reference_id} je storniran na CEZIH-u i ne može se "
            "uređivati. Osvježite prikaz."
        )
    if live["state"] == "superseded" and not live.get("oid"):
        raise CezihError(
            f"e-Nalaz {original_reference_id} je zamijenjen novijom verzijom, a "
            "CEZIH nije vratio trenutnu verziju. Osvježite prikaz i uredite "
            "aktualni e-Nalaz iz liste."
        )

    # Replace against the live current head when resolved. On state=unknown the
    # live search could not confirm the head (CEZIH unreachable, or the doc was
    # not matchable by id) - keep the caller ref + stored OID and let the
    # ITI-67 lookup below resolve it, rather than blocking a legitimate edit.
    if live.get("reference_id"):
        original_reference_id = live["reference_id"]
    original_document_oid = live.get("oid") or original_document_oid

    # Fallback ITI-67 lookup only if the live read somehow yielded no OID.
    if not original_document_oid:
        original_document_oid = await _lookup_document_oid(
            fhir_client,
            original_reference_id,
            identifier_value,
            identifier_system=identifier_system,
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
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
        org_name=org_name,
        relates_to=relates_to,
        use_external_profile=False,  # External profiles (v1.0.1) rejected by CEZIH test env with 415
        procedures=procedures,
        attachments=attachments,
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


async def amend_document(
    client: httpx.AsyncClient,
    original_reference_id: str,
    patient_data: dict,
    record_data: dict,
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    original_document_oid: str = "",
    org_name: str = "",
    procedures: list[dict] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    """Submit an *amended* clinical document (the "entered-in-error line" edit).

    The new document carries NO `relatesTo` at all (live-confirmed 2026-05-27:
    both `replaces` AND `appends` produce a `superseded` document on CEZIH —
    `replaces` supersedes the old, `appends` supersedes the *new* one — and any
    `superseded` doc deadlocks visit storno via ERR_ENCOUNTER_2001 ↔ ERR_DOM_10035).
    Instead the new doc is a standalone `status=current` document, still linked to
    the SAME visit + case via `context.encounter` + `context.related` (that linkage,
    not relatesTo, is what CEZIH/eKarton requires — verified in the 2026-05-11
    rejection-items sweep). The caller then cancels the old doc to `entered-in-error`.
    End state: old=`entered-in-error`, new=`current` + case-linked, NO `superseded`
    → patient keeps a visible active nalaz (the 2026-05-20 exam-fail condition) AND
    the visit stornos cleanly. The doc-to-doc correction link is kept LOCAL-only
    (audit/`cezih_amended_from_oid`), never on the wire.

    The returned old_document_oid / old_reference_id are the LIVE-resolved head —
    the dispatcher cancels exactly that version, never a stale stored OID. Do NOT
    route TC19 here; replace_document (with relatesTo=replaces) stays intact for it.
    """
    fhir_client = CezihFhirClient(client)

    # Resolve the LIVE current head before building relatesTo — same stale-OID
    # guard as replace_document. We append to whatever CEZIH currently holds as
    # the head, never a value our DB has already moved past.
    identifier_value = _require_identifier_value(patient_data)
    identifier_system = _require_identifier_system(patient_data)
    live = await _resolve_live_document_head(
        fhir_client, original_reference_id, identifier_system, identifier_value
    )

    if live["state"] == "entered-in-error":
        raise CezihError(
            f"e-Nalaz {original_reference_id} je storniran na CEZIH-u i ne može se "
            "uređivati. Osvježite prikaz."
        )
    if live["state"] == "superseded" and not live.get("oid"):
        raise CezihError(
            f"e-Nalaz {original_reference_id} je zamijenjen novijom verzijom, a "
            "CEZIH nije vratio trenutnu verziju. Osvježite prikaz i uredite "
            "aktualni e-Nalaz iz liste."
        )

    if live.get("reference_id"):
        original_reference_id = live["reference_id"]
    original_document_oid = live.get("oid") or original_document_oid

    if not original_document_oid:
        original_document_oid = await _lookup_document_oid(
            fhir_client,
            original_reference_id,
            identifier_value,
            identifier_system=identifier_system,
        )

    # NO relatesTo on the wire. Both `replaces` and `appends` leave a `superseded`
    # document on CEZIH (live-confirmed), which deadlocks visit storno. The edited
    # doc goes out as a standalone `current` doc; its tie to the original is kept
    # local-only. The visit/case linkage is preserved separately via
    # context.encounter + context.related inside the bundle below.
    bundle_dict, new_oid = await _build_document_bundle(
        fhir_client,
        patient_data,
        record_data,
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        practitioner_id=practitioner_id,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        practitioner_name=practitioner_name,
        org_name=org_name,
        relates_to=None,
        use_external_profile=False,  # External profiles (v1.0.1) rejected by CEZIH test env with 415
        procedures=procedures,
        attachments=attachments,
    )

    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-A-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    return {
        "success": True,
        "new_reference_id": ref_id,
        "new_document_oid": new_oid,
        "old_reference_id": original_reference_id,
        "old_document_oid": original_document_oid,
    }


def _extract_oid_from_docref(doc_ref: dict) -> str:
    """Extract masterIdentifier OID from a DocumentReference resource.

    Tries content[].attachment.url (base64 data param) first, then
    masterIdentifier.value as a fallback.
    """
    for content in doc_ref.get("content", []):
        url = content.get("attachment", {}).get("url", "")
        if not url:
            continue
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        data_val = qs.get("data", [""])[0]
        if data_val:
            decoded = base64.b64decode(data_val).decode("utf-8", errors="replace")
            for part in decoded.split("&"):
                if part.startswith("documentUniqueId="):
                    uid = part.split("=", 1)[1]
                    if "|" in uid:
                        return uid.split("|", 1)[1]
    val = doc_ref.get("masterIdentifier", {}).get("value", "")
    if val.startswith("urn:oid:"):
        return val
    return ""


async def _lookup_document_oid(
    fhir_client: CezihFhirClient,
    reference_id: str,
    patient_mbo: str,
    identifier_system: str,
    version_id: str | None = None,
) -> str:
    """Look up a document's OID from CEZIH via ITI-67.

    Strategy:
      1. If version_id provided: vread `DocumentReference/{id}/_history/{vid}` -
         only path that returns superseded predecessor refs (plain read returns
         404 once CEZIH flips status out of `current`).
      2. Direct GET DocumentReference/{id} (read) - covers current refs.
      3. Fallback: patient-scoped search. CEZIH requires both `patient.identifier`
         AND `status`; use `status=current,superseded` to cover both lifecycle states.
    """
    if version_id:
        try:
            doc_ref = await fhir_client.get(
                f"doc-mhd-svc/api/v1/DocumentReference/{reference_id}/_history/{version_id}"
            )
            if isinstance(doc_ref, dict) and doc_ref.get("resourceType") == "DocumentReference":
                oid = _extract_oid_from_docref(doc_ref)
                if oid:
                    logger.info(
                        "TC20: Resolved OID for document %s/_history/%s via vread: %s",
                        reference_id, version_id, oid,
                    )
                    return oid
        except Exception as e:
            logger.warning(
                "TC20: vread DocumentReference/%s/_history/%s failed, falling back: %s",
                reference_id, version_id, e,
            )

    try:
        doc_ref = await fhir_client.get(f"doc-mhd-svc/api/v1/DocumentReference/{reference_id}")
        if isinstance(doc_ref, dict) and doc_ref.get("resourceType") == "DocumentReference":
            oid = _extract_oid_from_docref(doc_ref)
            if oid:
                logger.info("TC20: Resolved OID for document %s via direct GET: %s", reference_id, oid)
                return oid
    except Exception as e:
        logger.warning("TC20: Direct GET DocumentReference/%s failed, falling back to search: %s", reference_id, e)

    try:
        params = {
            "patient.identifier": f"{identifier_system}|{patient_mbo}",
            "status": "current,superseded",
        }
        response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)
        for entry in response.get("entry", []):
            doc_ref = entry.get("resource", {})
            if doc_ref.get("id") == reference_id:
                oid = _extract_oid_from_docref(doc_ref)
                if oid:
                    logger.info("TC20: Resolved OID for document %s via search: %s", reference_id, oid)
                    return oid
    except Exception as e:
        logger.warning("TC20: OID search lookup failed for document %s: %s", reference_id, e)

    return ""


def _normalize_oid(oid: str) -> str:
    """Strip a leading urn:oid: so OIDs from different sources compare equal."""
    if not oid:
        return ""
    return oid[len("urn:oid:") :] if oid.startswith("urn:oid:") else oid


async def _find_current_head(
    fhir_client: CezihFhirClient,
    predecessor_id: str,
    predecessor_oid: str,
    identifier_system: str,
    identifier_value: str,
) -> dict | None:
    """Walk forward from a superseded DocumentReference to the current head.

    A successor's `relatesTo[code=replaces].target` points back at its
    predecessor, either by literal `DocumentReference/{id}` reference or by OID
    identifier (system urn:ietf:rfc:3986, value urn:oid:...). We search the
    patient's `status=current` documents and return the one whose relatesTo
    target matches our predecessor. Conservative: only returns on an
    unambiguous single match, else None (caller surfaces a clear error rather
    than risk cancelling the wrong document).
    """
    try:
        resp = await fhir_client.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={
                "patient.identifier": f"{identifier_system}|{identifier_value}",
                "status": "current",
                "_count": 200,
            },
        )
    except Exception as e:
        logger.warning("cancel pre-check: current-docs search failed: %s", e)
        return None

    pred_oid_norm = _normalize_oid(predecessor_oid)
    matches: list[dict] = []
    for entry in resp.get("entry") or []:
        doc = entry.get("resource") or {}
        if doc.get("resourceType") != "DocumentReference":
            continue
        for rel in doc.get("relatesTo", []) or []:
            if rel.get("code") != "replaces":
                continue
            tgt = rel.get("target") or {}
            ref = tgt.get("reference") or ""
            ident_val = _normalize_oid((tgt.get("identifier") or {}).get("value") or "")
            if (predecessor_id and predecessor_id in ref) or (
                pred_oid_norm and ident_val == pred_oid_norm
            ):
                matches.append(
                    {"reference_id": doc.get("id", ""), "oid": _extract_oid_from_docref(doc)}
                )
                break

    if len(matches) == 1:
        logger.info(
            "cancel pre-check: resolved current head %s for superseded %s",
            matches[0]["reference_id"], predecessor_id,
        )
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            "cancel pre-check: %d current heads reference superseded %s - ambiguous, not auto-resolving",
            len(matches), predecessor_id,
        )
    return None


async def _resolve_live_document_head(
    fhir_client: CezihFhirClient,
    reference_id: str,
    identifier_system: str,
    identifier_value: str,
) -> dict:
    """Resolve the live state + current head of a clinical document before a
    storno/cancel OR a replace.

    Returns {"state": current|superseded|entered-in-error|unknown,
             "reference_id": <head id>, "oid": <head OID>}.

    CEZIH rejects writing against a non-current version with ERR_DOM_10035
    ("Target resource is not in valid status"), so both cancel and replace must
    target the current version (or no-op/refuse on entered-in-error).

    Resolution is via the patient-scoped ITI-67 search, NOT a direct
    `GET DocumentReference/{id}`: CEZIH's doc-mhd-svc returns 404 for the numeric
    reference ids we store (verified live 2026-05-27), so a GET-by-id never
    resolves and the doc is only reachable through a `patient.identifier` +
    `status` search (the same mechanism _lookup_document_oid tier-3 and
    _find_current_head use). On a genuine search failure OR when the document
    cannot be matched by id we return state=unknown; callers then degrade to the
    stored OID (the proven fallback) rather than block a legitimate operation.
    """
    # current + superseded in one search (this status filter is proven to work
    # for this patient scope; see _lookup_document_oid).
    try:
        resp = await fhir_client.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={
                "patient.identifier": f"{identifier_system}|{identifier_value}",
                "status": "current,superseded",
                "_count": 200,
            },
        )
    except Exception as e:
        logger.warning(
            "live-doc pre-check: current/superseded search failed (%s) - state=unknown",
            e,
        )
        return {"state": "unknown", "reference_id": reference_id, "oid": ""}

    target: dict | None = None
    for entry in resp.get("entry") or []:
        doc = entry.get("resource") or {}
        if doc.get("resourceType") != "DocumentReference":
            continue
        if doc.get("id", "") == reference_id:
            target = {
                "status": (doc.get("status") or "").lower(),
                "oid": _extract_oid_from_docref(doc),
            }
            break

    if target is not None:
        if target["status"] == "current":
            return {"state": "current", "reference_id": reference_id, "oid": target["oid"]}
        if target["status"] == "superseded":
            head = await _find_current_head(
                fhir_client, reference_id, target["oid"], identifier_system, identifier_value
            )
            if head and head.get("oid"):
                return {"state": "current", "reference_id": head["reference_id"], "oid": head["oid"]}
            return {"state": "superseded", "reference_id": reference_id, "oid": target["oid"]}

    # Not among current/superseded - it may already be storno'd. A separate
    # entered-in-error search lets the cancel path no-op idempotently.
    try:
        eie = await fhir_client.get(
            "doc-mhd-svc/api/v1/DocumentReference",
            params={
                "patient.identifier": f"{identifier_system}|{identifier_value}",
                "status": "entered-in-error",
                "_count": 200,
            },
        )
        for entry in eie.get("entry") or []:
            doc = entry.get("resource") or {}
            if doc.get("resourceType") == "DocumentReference" and doc.get("id", "") == reference_id:
                return {
                    "state": "entered-in-error",
                    "reference_id": reference_id,
                    "oid": _extract_oid_from_docref(doc),
                }
    except Exception as e:
        logger.warning("live-doc pre-check: entered-in-error search failed (%s)", e)

    # Reachable, but the document could not be matched by id in any live status.
    # We cannot assert the live head; degrade to the stored OID (callers handle
    # state=unknown by keeping the stored OID / ITI-67 lookup).
    logger.info(
        "live-doc pre-check: %s not matched in live search - degrading to stored OID",
        reference_id,
    )
    return {"state": "unknown", "reference_id": reference_id, "oid": ""}


async def cancel_document_canonical(
    client: httpx.AsyncClient,
    reference_id: str,
    patient_data: dict,
    record_data: dict,
    *,
    djelatnost_code: str,
    djelatnost_display: str,
    org_code: str = "",
    practitioner_id: str | None = None,
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    original_document_oid: str = "",
    version_id: str | None = None,
    org_name: str = "",
) -> dict:
    """Cancel/storno via canonical HRCancelDocumentBundle (2-entry, status=entered-in-error).

    The sole storno path. 2-entry HRCancelDocumentBundle, no OID generation on
    the bundle, no inner Document Bundle, no signing - the canonical Klinicki
    Dokumenti IG profile (the legacy replace-style cancel was removed).

    `version_id` is the history version for refs that CEZIH has already flipped
    out of `status=current` (i.e. predecessors after an ITI-65 replace) - vread
    is the only way to fetch them.
    """
    fhir_client = CezihFhirClient(client)

    # Resolve the LIVE document state from CEZIH before cancelling. Cancelling
    # against a stored OID that CEZIH has already superseded (post-replace) or
    # already flipped to entered-in-error returns ERR_DOM_10035 ("Target
    # resource is not in valid status") - the root cause of the 2026-05-20
    # provjera failure (patient #2, all e-Nalazi storno'd). See finding
    # docs/CEZIH/findings/2026-05-27-exam-fail-patient2-storno-stale-ref.md.
    identifier_value = _require_identifier_value(patient_data)
    identifier_system = _require_identifier_system(patient_data)
    live = await _resolve_live_document_head(
        fhir_client, reference_id, identifier_system, identifier_value
    )

    if live["state"] == "entered-in-error":
        # Already storno'd on CEZIH - idempotent no-op, no POST. Kills the
        # repeated ERR_DOM_10035 from re-storno attempts.
        logger.info(
            "TC20 canonical cancel: document %s already entered-in-error on CEZIH - no-op",
            reference_id,
        )
        return {
            "success": True,
            "reference_id": reference_id,
            "new_reference_id": live.get("reference_id") or reference_id,
            "new_document_oid": live.get("oid") or original_document_oid,
            "status": "entered-in-error",
            "already_cancelled": True,
        }

    if live["state"] == "superseded" and not live.get("oid"):
        raise CezihError(
            f"e-Nalaz {reference_id} je zamijenjen novijom verzijom, a CEZIH nije "
            "vratio trenutnu verziju za storno. Osvježite prikaz i stornirajte "
            "aktualni e-Nalaz iz liste."
        )

    # Prefer the live-resolved current OID. On state=unknown (CEZIH unreachable
    # or the doc not matchable by id in the live search) degrade to the stored
    # OID and then the ITI-67 lookup below - the proven resolution chain. The
    # stale-OID ERR_DOM_10035 from the 2026-05-20 provjera is prevented by the
    # search-based head resolution above (which walks superseded -> current),
    # not by blocking the storno when the live read is inconclusive.
    original_document_oid = live.get("oid") or original_document_oid
    if not original_document_oid:
        original_document_oid = await _lookup_document_oid(
            fhir_client,
            live.get("reference_id") or reference_id,
            identifier_value,
            identifier_system=identifier_system,
            version_id=version_id,
        )
    if not original_document_oid:
        raise CezihError(
            f"TC20 canonical cancel: nije moguće pronaći OID dokumenta {reference_id} u CEZIH-u "
            "(ITI-67 search nije vratio masterIdentifier). Storno se ne može poslati "
            "bez OID-a originalnog dokumenta."
        )

    logger.info(
        "TC20 canonical cancel: ref=%s oid=%s state=%s - using HRCancelDocumentBundle profile",
        reference_id, original_document_oid, live["state"],
    )

    bundle_dict = build_cancel_bundle(
        patient_data=patient_data,
        record_data=record_data,
        original_document_oid=original_document_oid,
        djelatnost_code=djelatnost_code,
        djelatnost_display=djelatnost_display,
        practitioner_id=practitioner_id,
        practitioner_name=practitioner_name,
        org_code=org_code,
        encounter_id=encounter_id,
        case_id=case_id,
        org_name=org_name,
    )

    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-CX-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    return {
        "success": True,
        "reference_id": reference_id,
        "new_reference_id": ref_id,
        "new_document_oid": original_document_oid,
        "status": "entered-in-error",
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
    "list_active_documents_on_encounter",
    "replace_document",
    "amend_document",
    "_lookup_document_oid",
    "build_cancel_bundle",
    "cancel_document_canonical",
    "retrieve_document",
]
