from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.constants import get_cezih_document_coding
from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError
from app.services.cezih.message_builder import (
    SIGNATURE_TYPE_CODE,
    SIGNATURE_TYPE_SYSTEM,
    _now_iso,
    add_signature,
    build_condition_create,
    build_condition_data_update,
    build_condition_status_update,
    build_iti65_transaction_bundle,
    build_message_bundle,
    org_ref,
    parse_message_response,
    practitioner_ref,
)
from app.services.cezih.models import FHIRPatient

logger = logging.getLogger(__name__)

# CEZIH identifier systems
SYS_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"
SYS_OIB = "http://fhir.cezih.hr/specifikacije/identifikatori/oib"
SYS_PUTOVNICA = "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica"
SYS_EUROPSKA = "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica"
SYS_JEDINSTVENI = "http://fhir.cezih.hr/specifikacije/identifikatori/jedinstveni-identifikator-pacijenta"

_IDENTIFIER_SYSTEM_MAP = {
    "mbo": SYS_MBO,
    "putovnica": SYS_PUTOVNICA,
    "ehic": SYS_EUROPSKA,
}

_IDENTIFIER_LABEL_MAP = {
    SYS_MBO: "MBO",
    SYS_PUTOVNICA: "Putovnica",
    SYS_EUROPSKA: "EHIC",
    SYS_JEDINSTVENI: "CEZIH ID",
    SYS_OIB: "OIB",
}


async def search_patient_by_identifier(
    client: httpx.AsyncClient,
    identifier_system: str,
    value: str,
    tenant_id=None,
) -> dict:
    """Search CEZIH patient registry by identifier (MBO, passport, or EHIC).

    identifier_system must be one of: 'mbo', 'putovnica', 'ehic'.
    Uses ITI-78 PDQm — same transaction as fetch_patient_demographics / check_insurance.
    """
    system_uri = _IDENTIFIER_SYSTEM_MAP.get(identifier_system)
    if not system_uri:
        raise CezihError(f"Nepoznati tip identifikatora: {identifier_system}")

    fhir_client = CezihFhirClient(client, tenant_id=tenant_id)
    params = {"identifier": f"{system_uri}|{value}"}
    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params, timeout=10)

    if response.get("resourceType") != "Bundle":
        raise CezihError("Neočekivan format odgovora iz CEZIH-a")

    entries = response.get("entry", [])
    if not entries:
        id_label = {"mbo": "MBO", "putovnica": "putovnica", "ehic": "EHIC broj"}.get(identifier_system, identifier_system)
        raise CezihError(f"Pacijent s {id_label} '{value}' nije pronađen u CEZIH registru")

    if len(entries) > 1:
        logger.warning("PDQm patient search returned %d entries for %s|%s — using first", len(entries), identifier_system, value)

    raw_resource = entries[0].get("resource", {})
    logger.info("PDQm raw Patient resource (%s|%s): %.2000s", identifier_system, value, str(raw_resource))

    patient = FHIRPatient.model_validate(raw_resource)
    family, given = _extract_name(patient)

    # Prefer the internal CEZIH patient ID over the search identifier —
    # jedinstveni-identifikator-pacijenta is what subsequent FHIR operations use.
    cezih_id = ""
    for ident in patient.identifier:
        if ident.system == SYS_JEDINSTVENI and ident.value:
            cezih_id = ident.value
            break
    if not cezih_id:
        for ident in patient.identifier:
            if ident.value:
                cezih_id = ident.value
                break

    # Collect all identifiers with friendly labels
    identifikatori = []
    for ident in patient.identifier:
        if not ident.value:
            continue
        sys = ident.system or ""
        label = _IDENTIFIER_LABEL_MAP.get(sys) or (sys.rstrip("/").rsplit("/", 1)[-1] if sys else "ID")
        identifikatori.append({"system": sys, "value": ident.value, "label": label})

    # Address
    adresa = None
    if patient.address:
        addr = patient.address[0]
        lines = addr.get("line") or []
        adresa = {
            "ulica": lines[0] if lines else "",
            "grad": addr.get("city", ""),
            "postanski_broj": addr.get("postalCode", ""),
            "drzava": addr.get("country", ""),
        }

    # Telecom
    telefon = ""
    email = ""
    for tc in patient.telecom:
        if not telefon and tc.get("system") == "phone" and tc.get("value"):
            telefon = tc["value"]
        if not email and tc.get("system") == "email" and tc.get("value"):
            email = tc["value"]

    # hr-patient-last-contact extension
    zadnji_kontakt = ""
    HR_LAST_CONTACT = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-patient-last-contact"
    for ext in patient.extension:
        if ext.get("url") == HR_LAST_CONTACT:
            zadnji_kontakt = ext.get("valueDate") or ext.get("valueDateTime") or ""
            break

    spol_map = {"male": "M", "female": "Ž", "other": "Ostalo", "unknown": "Nepoznato"}
    spol = spol_map.get(patient.gender or "", "")

    return {
        "cezih_id": cezih_id,
        "ime": given,
        "prezime": family,
        "datum_rodjenja": patient.birthDate or "",
        "spol": spol,
        "identifier_system": identifier_system,
        "identifier_value": value,
        "active": patient.active,
        "datum_smrti": patient.deceasedDateTime or "",
        "zadnji_kontakt": zadnji_kontakt,
        "adresa": adresa,
        "telefon": telefon,
        "email": email,
        "identifikatori": identifikatori,
    }


async def fetch_patient_demographics(client: httpx.AsyncClient, mbo: str) -> dict:
    """Fetch patient demographics from CEZIH PDQm and return fields matching our Patient model."""
    fhir_client = CezihFhirClient(client)
    params = {"identifier": f"{SYS_MBO}|{mbo}"}
    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params, timeout=10)

    if response.get("resourceType") != "Bundle":
        raise CezihError("Neočekivan format odgovora iz CEZIH-a")

    entries = response.get("entry", [])
    if not entries:
        raise CezihError(f"Pacijent s MBO {mbo} nije pronađen u CEZIH registru")

    patient = FHIRPatient.model_validate(entries[0].get("resource", {}))
    family, given = _extract_name(patient)

    oib = ""
    for ident in patient.identifier:
        if ident.system and "OIB" in (ident.system or "").upper() and ident.value:
            oib = ident.value

    spol_map = {"male": "M", "female": "Z"}
    spol = spol_map.get(patient.gender or "", None)

    return {
        "mbo": mbo,
        "ime": given,
        "prezime": family,
        "datum_rodjenja": patient.birthDate or None,
        "oib": oib or None,
        "spol": spol,
    }


async def check_insurance(client: httpx.AsyncClient, mbo: str) -> dict:
    """Patient demographics lookup by MBO (ITI-78 PDQm).

    GET /patient-registry-services/api/v1/Patient?identifier={SYS_MBO}|{mbo}
    """
    fhir_client = CezihFhirClient(client)
    params = {"identifier": f"{SYS_MBO}|{mbo}"}

    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params, timeout=10)

    if response.get("resourceType") == "Bundle":
        entries = response.get("entry", [])
        if not entries:
            return {
                "mbo": mbo,
                "ime": "",
                "prezime": "",
                "datum_rodjenja": "",
                "oib": "",
                "spol": "",
                "osiguravatelj": "",
                "status_osiguranja": "Nije pronađen",
            }

        patient = FHIRPatient.model_validate(entries[0].get("resource", {}))
        family, given = _extract_name(patient)

        # Extract OIB from identifiers
        oib = ""
        for ident in patient.identifier:
            if ident.system and ident.system.endswith("/OIB") and ident.value:
                oib = ident.value

        # Map FHIR gender to Croatian
        spol_map = {"male": "M", "female": "Ž", "other": "Ostalo", "unknown": "Nepoznato"}
        spol = spol_map.get(patient.gender or "", "")

        return {
            "mbo": mbo,
            "ime": given,
            "prezime": family,
            "datum_rodjenja": patient.birthDate or "",
            "oib": oib,
            "spol": spol,
            "osiguravatelj": "HZZO",
            "status_osiguranja": "Aktivan",
        }

    # Unexpected response format — log full response for debugging
    logger.warning("CEZIH insurance check: unexpected response type: %s — full response: %.500s",
                    response.get("resourceType"), str(response))
    raise CezihError("Unexpected CEZIH response format for patient lookup")


async def _build_document_bundle(
    fhir_client: "CezihFhirClient",
    patient_data: dict,
    record_data: dict,
    practitioner_id: str | None = None,
    org_code: str = "",
    encounter_id: str = "",
    case_id: str = "",
    practitioner_name: str = "",
    relates_to: dict | None = None,
    use_external_profile: bool = False,
) -> tuple[dict, str]:
    """Build a complete ITI-65 transaction bundle for document submission/replace.

    Returns (bundle_dict, doc_ref_id_placeholder).
    Shared by send_enalaz (TC18) and replace_document (TC19).
    """
    import base64
    import uuid as _uuid

    # Build clinical content text
    content_parts: list[str] = []
    if record_data.get("dijagnoza_mkb") or record_data.get("dijagnoza_tekst"):
        dx_parts = []
        if record_data.get("dijagnoza_mkb"):
            dx_parts.append(record_data["dijagnoza_mkb"])
        if record_data.get("dijagnoza_tekst"):
            dx_parts.append(record_data["dijagnoza_tekst"])
        content_parts.append("Dijagnoza: " + " — ".join(dx_parts))
    if record_data.get("sadrzaj"):
        content_parts.append(record_data["sadrzaj"])
    therapy = record_data.get("preporucena_terapija")
    if therapy:
        content_parts.append("\nPreporučena terapija:")
        for t in therapy:
            line = f"- {t.get('naziv', '')}"
            if t.get("jacina"):
                line += f" {t['jacina']}"
            if t.get("doziranje"):
                line += f", {t['doziranje']}"
            if t.get("napomena"):
                line += f". {t['napomena']}"
            content_parts.append(line)
        content_parts.append("(Preporuka specijalista — obiteljski liječnik izdaje e-Recept s RS oznakom)")

    clinical_text = "\n".join(content_parts)
    clinical_b64 = base64.b64encode(clinical_text.encode("utf-8")).decode("ascii") if clinical_text else None

    doc_uuid = str(_uuid.uuid4())
    coding = get_cezih_document_coding(record_data.get("tip", "nalaz"))
    patient_display = f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}".strip()

    # Generate document OID via CEZIH identifier registry
    doc_oid = ""
    try:
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
        if oids:
            doc_oid = oids[0]
            logger.info("Generated document OID: %s", doc_oid)
    except Exception as e:
        logger.warning("OID generation failed: %s", e)

    _doc_ref_profile = (
        "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternaltMinimalDocumentReference"
        if use_external_profile else
        "http://fhir.cezih.hr/specifikacije/StructureDefinition/HR.MinimalDocumentReference"
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
        "identifier": [{
            "use": "official",
            "system": "urn:ietf:rfc:3986",
            "value": f"urn:uuid:{doc_uuid}",
        }],
        "status": "current",
        "type": {
            "coding": [{
                "system": coding["system"],
                "code": coding["code"],
                "display": coding["display"],
            }]
        },
        "subject": {
            "type": "Patient",
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/MBO",
                "value": patient_data.get("mbo", ""),
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
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika",
                "value": practitioner_id,
            },
        }
        if practitioner_name:
            author_practitioner["display"] = practitioner_name
        doc_ref_dict["author"].append(author_practitioner)

    # Author: organization (HZZO code)
    if org_code:
        doc_ref_dict["author"].append({
            "type": "Organization",
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije",
                "value": org_code,
            },
        })

    # Authenticator (CEZIHDR-001: odgovorna osoba) — display required (min:1)
    if practitioner_id:
        doc_ref_dict["authenticator"] = {
            "type": "Practitioner",
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika",
                "value": practitioner_id,
            },
            "display": practitioner_name or practitioner_id,
        }

    # Custodian: organization — display required (min:1)
    if org_code:
        doc_ref_dict["custodian"] = {
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije",
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
            "coding": [{
                "system": "http://fhir.cezih.hr/specifikacije/CodeSystem/djelatnosti-zz",
                "code": "1010000",
                "display": "Opća/obiteljska medicina",
            }]
        },
    }
    if encounter_id:
        context["encounter"] = [{
            "type": "Encounter",
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-posjete",
                "value": encounter_id,
            },
        }]
    if case_id:
        context["related"] = [{
            "type": "Condition",
            "identifier": {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja",
                "value": case_id,
            },
        }]
    doc_ref_dict["context"] = context

    # relatesTo for replace operations (TC19)
    if relates_to:
        doc_ref_dict["relatesTo"] = [relates_to]

    # Content: Binary resource referenced via URL (inline data is forbidden, max=0)
    binary_uuid = str(_uuid.uuid4())
    if clinical_b64:
        binary_resource: dict = {
            "resourceType": "Binary",
            "contentType": "text/plain",
            "data": clinical_b64,
        }
    else:
        binary_resource = {
            "resourceType": "Binary",
            "contentType": "text/plain",
            "data": "",
        }
    doc_ref_dict["content"] = [{
        "attachment": {
            "contentType": "text/plain",
            "language": "hr-HR",
            "url": f"urn:uuid:{binary_uuid}",
        }
    }]

    # Build IHE MHD ITI-65 transaction bundle
    entries = [doc_ref_dict]
    binary_resource["_uuid"] = binary_uuid
    entries.append(binary_resource)

    _bundle_profile = None
    _ss_profile = None
    if use_external_profile:
        _bundle_profile = "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRExternalMinimalProvideDocumentBundle"
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

    bundle_dict, doc_oid = await _build_document_bundle(
        fhir_client, patient_data, record_data,
        practitioner_id=practitioner_id, org_code=org_code,
        encounter_id=encounter_id, case_id=case_id,
        practitioner_name=practitioner_name,
    )

    bundle_dict = await add_signature(bundle_dict, practitioner_id or "")

    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle_dict,
    )

    import json as _json_log
    logger.info("ITI-65 response: %s", _json_log.dumps(response, ensure_ascii=False, default=str)[:3000])

    ref_id = _extract_ref_id_from_response(response)
    if not ref_id:
        ref_id = f"FHIR-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    logger.info("Extracted document reference ID: %s", ref_id)

    signature_data = bundle_dict.get("signature", {})
    signature_base64 = signature_data.get("data", "") if signature_data else ""

    return {
        "success": True,
        "reference_id": ref_id,
        "document_oid": doc_oid,
        "sent_at": datetime.now(UTC).isoformat(),
        "signature_data": signature_base64,
        "signed_at": signature_data.get("when") if signature_data else None,
    }


async def search_documents(
    client: httpx.AsyncClient,
    *,
    patient_mbo: str | None = None,
    document_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    """Search clinical documents (ITI-67 MHD — flexible parameters for TC21).

    Supports search by patient, document type, date range, and status.
    """
    fhir_client = CezihFhirClient(client)
    params: dict = {}

    if patient_mbo:
        params["patient.identifier"] = f"http://fhir.cezih.hr/specifikacije/identifikatori/MBO|{patient_mbo}"
    if document_type:
        params["type"] = f"http://fhir.cezih.hr/specifikacije/vrste-dokumenata|{document_type}"
    if date_from:
        params["date"] = f"ge{date_from}"
    if date_to:
        params["date"] = params.get("date", "") + f"&date=le{date_to}" if "date" in params else f"le{date_to}"
    # CEZIH requires status parameter — default to "current" if not specified
    params["status"] = status_filter or "current"

    import logging
    _log = logging.getLogger(__name__)
    try:
        response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)
    except Exception as exc:
        _log.error("Document search failed: %s", exc)
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
                items.append({
                    "id": doc_ref.get("id", ""),
                    "datum_izdavanja": doc_ref.get("date", ""),
                    "izdavatelj": author or _extract_reference_display(doc_ref.get("custodian")),
                    "svrha": _extract_codeable_text(doc_ref.get("type")),
                    "specijalist": author,
                    "status": _map_fhir_status(doc_ref.get("status", "current")),
                    "type": _extract_codeable_text(doc_ref.get("type")),
                    "content_url": content_url,
                })
            except Exception as parse_exc:
                _log.warning("Skipping unparseable DocumentReference: %s", parse_exc)
                continue

    return items


async def send_erecept(
    client: httpx.AsyncClient,
    patient_data: dict,
    lijekovi: list[dict],
) -> dict:
    """Send e-prescription — not yet part of CEZIH unified private provider certification."""
    raise CezihError(
        "e-Recept API nije implementiran u CEZIH sustavu za privatne ordinacije."
    )


async def cancel_erecept(client: httpx.AsyncClient, recept_id: str) -> dict:
    """Cancel/storno an e-prescription — not yet part of CEZIH unified private provider certification."""
    raise CezihError(
        "Storno e-Recepta nije implementiran u CEZIH sustavu za privatne ordinacije."
    )


async def get_status(client: httpx.AsyncClient) -> dict:
    """Check CEZIH connectivity."""
    fhir_client = CezihFhirClient(client)
    connected = await fhir_client.health_check()
    return {
        "connected": connected,
        "mode": "real",
    }


async def search_drugs(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search drugs via CEZIH CodeSystem (ITI-96).

    GET /terminology-services/api/v1/CodeSystem?name={query}
    """
    if not query or len(query) < 2:
        return []

    fhir_client = CezihFhirClient(client)
    params = {"name": query, "_count": "20"}

    response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)

    drugs = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            cs = entry.get("resource", {})
            drugs.append({
                "atk": cs.get("id", ""),
                "naziv": cs.get("name", ""),
                "oblik": "",
                "jacina": "",
            })

    return drugs


# --- Helpers ---


def _extract_name(patient: FHIRPatient) -> tuple[str, str]:
    """Extract family and given names from a FHIR Patient resource."""
    if not patient.name:
        return "", ""
    official = next((n for n in patient.name if n.use == "official"), patient.name[0])
    family = official.family or ""
    given = " ".join(official.given) if official.given else ""
    return family, given


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


# ============================================================
# TC6: OID Registry Lookup
# ============================================================


async def generate_oid(client: httpx.AsyncClient, quantity: int = 1) -> dict:
    """Generate OID(s) via CEZIH identifier registry (TC6).

    Uses the same generateOIDBatch call proven in send_enalaz (TC18).
    """
    fhir_client = CezihFhirClient(client)
    response = await fhir_client.post(
        "identifier-registry-services/api/v1/oid/generateOIDBatch",
        json_body={
            "oidType": {
                "system": "http://ent.hr/fhir/CodeSystem/ehe-oid-types",
                "code": "1",
            },
            "quantity": quantity,
        },
    )
    oids = response.get("oid") or response.get("oids") or []
    return {
        "generated_oid": oids[0] if oids else "",
        "oids": oids,
    }


# ============================================================
# TC7: Code System Query ITI-96 (generalized)
# ============================================================


async def query_code_system(
    client: httpx.AsyncClient, system_name: str, query: str, count: int = 20,
) -> list[dict]:
    """Query a CEZIH code system (ITI-96 SVCM).

    For large code systems (e.g. ICD-10) where concepts are not embedded
    inline, uses ValueSet/$expand with a filter to search.  Falls back to
    inline concept extraction for small code systems.
    """
    import logging
    logger = logging.getLogger(__name__)
    fhir_client = CezihFhirClient(client)

    # Step 1: Resolve the CodeSystem URL from the system name
    cs_url: str | None = None
    params: dict = {"url:contains": system_name, "_count": "1"}
    response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)
    if not response.get("entry"):
        params = {"name:contains": system_name, "_count": "1"}
        response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)
    if response.get("resourceType") == "Bundle" and response.get("entry"):
        cs_url = response["entry"][0].get("resource", {}).get("url")
    logger.info(f"CodeSystem lookup '{system_name}' -> url={cs_url}")

    # Step 2: Try ValueSet/$expand with filter (FHIR-standard for searching)
    if query and cs_url:
        for expand_url in [cs_url, cs_url.replace("/CodeSystem/", "/ValueSet/")]:
            try:
                expand_resp = await fhir_client.get(
                    "terminology-services/api/v1/ValueSet/$expand",
                    params={"url": expand_url, "filter": query, "_count": str(count)},
                )
                concepts = []
                for contains in expand_resp.get("expansion", {}).get("contains", []):
                    concepts.append({
                        "code": contains.get("code", ""),
                        "display": contains.get("display", ""),
                        "system": contains.get("system", cs_url),
                    })
                if concepts:
                    return concepts
            except Exception:
                continue

    # Step 3: Try CodeSystem/$lookup for exact code match
    if query and cs_url:
        try:
            lookup_resp = await fhir_client.get(
                "terminology-services/api/v1/CodeSystem/$lookup",
                params={"system": cs_url, "code": query},
            )
            if lookup_resp.get("resourceType") == "Parameters":
                code_val = display_val = ""
                for param in lookup_resp.get("parameter", []):
                    if param.get("name") == "display":
                        display_val = param.get("valueString", "")
                    if param.get("name") == "code":
                        code_val = param.get("valueString", query)
                if display_val:
                    return [{"code": code_val or query, "display": display_val, "system": cs_url}]
        except Exception:
            pass

    # Step 4: Fallback — extract inline concepts from the CodeSystem resource
    # (works for small code systems like nacin-prijema, vrsta-posjete)
    params = {"url:contains": system_name, "_count": str(count)}
    response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)
    if not response.get("entry"):
        params = {"name:contains": system_name, "_count": str(count)}
        response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)

    results = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            cs = entry.get("resource", {})
            for concept in cs.get("concept", []):
                code = concept.get("code", "")
                display = concept.get("display", "")
                if query and query.lower() not in code.lower() and query.lower() not in display.lower():
                    continue
                results.append({
                    "code": code,
                    "display": display,
                    "system": cs.get("url", system_name),
                })
    return results


# ============================================================
# TC8: Value Set Expand ITI-95
# ============================================================


async def expand_value_set(
    client: httpx.AsyncClient, url: str, filter_text: str | None = None,
) -> dict:
    """Expand a CEZIH value set (ITI-95 SVCM $expand)."""
    fhir_client = CezihFhirClient(client)
    params: dict = {"url": url, "_count": "100"}
    if filter_text:
        params["filter"] = filter_text
    # Try $expand first, fall back to plain search
    try:
        response = await fhir_client.get("terminology-services/api/v1/ValueSet/$expand", params=params)
    except Exception:
        response = await fhir_client.get("terminology-services/api/v1/ValueSet", params=params)

    concepts = []
    expansion = response.get("expansion", {})
    for contains in expansion.get("contains", []):
        concepts.append({
            "code": contains.get("code", ""),
            "display": contains.get("display", ""),
            "system": contains.get("system", ""),
        })
    return {"url": url, "concepts": concepts, "total": len(concepts)}


# ============================================================
# TC9: Subject Registry ITI-90 (mCSD)
# ============================================================


async def find_organizations(client: httpx.AsyncClient, name: str) -> list[dict]:
    """Search organizations in CEZIH registry (ITI-90 mCSD)."""
    fhir_client = CezihFhirClient(client)
    params = {"name": name, "_count": "20"}
    response = await fhir_client.get("mcsd/api/Organization", params=params)

    results = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            org = entry.get("resource", {})
            hzzo_code = ""
            for ident in org.get("identifier", []):
                if "HZZO" in (ident.get("system") or ""):
                    hzzo_code = ident.get("value", "")
            results.append({
                "id": org.get("id", ""),
                "name": org.get("name", ""),
                "hzzo_code": hzzo_code,
                "active": org.get("active", True),
            })
    return results


async def find_practitioners(client: httpx.AsyncClient, name: str) -> list[dict]:
    """Search practitioners in CEZIH registry (ITI-90 mCSD)."""
    fhir_client = CezihFhirClient(client)
    params = {"name": name, "_count": "20"}
    response = await fhir_client.get("mcsd/api/Practitioner", params=params)

    results = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            pract = entry.get("resource", {})
            hzjz_id = ""
            for ident in pract.get("identifier", []):
                if "HZJZ" in (ident.get("system") or ""):
                    hzjz_id = ident.get("value", "")
            name_parts = pract.get("name", [{}])[0] if pract.get("name") else {}
            results.append({
                "id": pract.get("id", ""),
                "family": name_parts.get("family", ""),
                "given": " ".join(name_parts.get("given", [])),
                "hzjz_id": hzjz_id,
                "active": pract.get("active", True),
            })
    return results


# ============================================================
# TC11: Foreigner Registration (PMIR)
# ============================================================


async def register_foreigner(
    client: httpx.AsyncClient,
    patient_data: dict,
    org_code: str = "",
    source_oid: str = "",
    practitioner_id: str = "",
) -> dict:
    """Register a foreigner in CEZIH (PMIR ITI-93).

    Built to match official Simplifier example (Bundle-register-patient-example.json)
    from cezih.hr.cezih-osnova v1.0.1 EXACTLY:
    - Outer Bundle: meta.profile=HRRegisterPatient, type=message, plain UUID fullUrls
    - MessageHeader: meta.profile=IHE.PMIR.MessageHeader, eventUri=patient-feed
    - Inner Bundle: meta.profile=IHE.PMIR.Bundle.History, type=history
    - Patient: urn:uuid: fullUrl, identifiers (putovnica+europska-kartica), address.country
    - Digital signature is REQUIRED (min=1) — NO placeholder fallback
    """
    import uuid as _uuid

    fhir_client = CezihFhirClient(client)
    # Use urn:uuid: for ALL fullUrls and references (like working encounters).
    # The official Simplifier example uses plain UUIDs, but CEZIH's HAPI server
    # resolves plain UUIDs as literal references (Bundle/{uuid}) instead of
    # matching fullUrl — causing "Reference_REF_CantResolve".
    patient_uuid = str(_uuid.uuid4())
    inner_bundle_uuid = f"urn:uuid:{_uuid.uuid4()}"
    header_uuid = f"urn:uuid:{_uuid.uuid4()}"

    # Build Patient resource per HRRegisterPatient profile.
    # Field order and content matches the official Simplifier example exactly.
    # Profile constraints: identifier min=1 max=2 (rules=closed: putovnica + europska-kartica only),
    # name min=1 max=1, address min=1 max=1, address.country min=1.
    # birthDate and gender are NOT in the official example — omit them.
    identifiers = []
    if patient_data.get("broj_putovnice"):
        identifiers.append({
            "system": "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica",
            "value": patient_data["broj_putovnice"],
        })
    if patient_data.get("ehic_broj"):
        identifiers.append({
            "system": "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica",
            "value": patient_data["ehic_broj"],
        })

    # address.country binding=required to ValueSet/drzave (ISO 3166-1 alpha-3).
    # Frontend may send alpha-2 (DE) — convert to alpha-3 (DEU).
    raw_country = (patient_data.get("drzavljanstvo") or "HRV").upper().strip()
    _ALPHA2_TO_ALPHA3 = {
        "AF": "AFG", "AL": "ALB", "DZ": "DZA", "AD": "AND", "AO": "AGO",
        "AR": "ARG", "AM": "ARM", "AU": "AUS", "AT": "AUT", "AZ": "AZE",
        "BA": "BIH", "BE": "BEL", "BG": "BGR", "BR": "BRA", "CA": "CAN",
        "CH": "CHE", "CN": "CHN", "CY": "CYP", "CZ": "CZE", "DE": "DEU",
        "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA",
        "GB": "GBR", "GE": "GEO", "GR": "GRC", "HR": "HRV", "HU": "HUN",
        "IE": "IRL", "IL": "ISR", "IN": "IND", "IS": "ISL", "IT": "ITA",
        "JP": "JPN", "KR": "KOR", "LT": "LTU", "LU": "LUX", "LV": "LVA",
        "ME": "MNE", "MK": "MKD", "MT": "MLT", "MX": "MEX", "NL": "NLD",
        "NO": "NOR", "NZ": "NZL", "PL": "POL", "PT": "PRT", "RO": "ROU",
        "RS": "SRB", "RU": "RUS", "SE": "SWE", "SI": "SVN", "SK": "SVK",
        "TR": "TUR", "UA": "UKR", "US": "USA", "XK": "XKX", "ZA": "ZAF",
    }
    country = _ALPHA2_TO_ALPHA3.get(raw_country, raw_country) if len(raw_country) == 2 else raw_country
    patient_resource: dict = {
        "resourceType": "Patient",
        "identifier": identifiers,
        "active": True,
        "name": [{
            "use": "official",
            "family": patient_data["prezime"],
            "given": [patient_data["ime"]],
        }],
        "address": [{"country": country}],
    }

    # Inner Bundle (type=history).
    # NOTE: working encounters use NO meta.profile on individual resources.
    # CEZIH knows expected profiles from the StructureDefinition, not meta.profile.
    inner_bundle = {
        "resourceType": "Bundle",
        "type": "history",
        "entry": [{
            "fullUrl": f"urn:uuid:{patient_uuid}",
            "resource": patient_resource,
            "request": {"method": "POST", "url": "Patient"},
            "response": {"status": "201"},
        }],
    }

    # MessageHeader — IHE PMIR profile, matching official example field order
    source_endpoint = f"urn:oid:{source_oid}" if source_oid else f"urn:oid:{org_code}" if org_code else "urn:oid:2.16.840.1.113883.2.7"
    message_header = {
        "resourceType": "MessageHeader",
        "eventUri": "urn:ihe:iti:pmir:2019:patient-feed",
        "destination": [{"endpoint": "http://cezih.hr/pmir"}],
        "sender": org_ref(org_code) if org_code else {"type": "Organization"},
        "author": practitioner_ref(practitioner_id) if practitioner_id else {"type": "Practitioner"},
        "source": {"endpoint": source_endpoint},
        "focus": [{"reference": inner_bundle_uuid}],
    }

    # Outer Bundle — HRRegisterPatient profile, plain UUID fullUrls (matching example)
    bundle: dict = {
        "resourceType": "Bundle",
        "id": str(_uuid.uuid4()),
        "meta": {
            "profile": ["http://fhir.cezih.hr/specifikacije/StructureDefinition/HRRegisterPatient"],
        },
        "type": "message",
        "timestamp": _now_iso(),
        "entry": [
            {"fullUrl": header_uuid, "resource": message_header},
            {"fullUrl": inner_bundle_uuid, "resource": inner_bundle},
        ],
    }

    # Digital signature — REQUIRED (min=1), no placeholder fallback
    # If signing fails, let the error propagate (same pattern as visit/case signing)
    bundle = await add_signature(bundle, practitioner_id, http_client=client)

    # Pre-flight GET: establish the gateway session cookie before POSTing.
    # Without a session cookie, POST requests get redirected to Keycloak auth.
    # Keycloak rejects POST with application/fhir+json body → 415.
    # A GET goes through the redirect cleanly (no body issue) and sets the cookie.
    try:
        await fhir_client.get(
            "patient-registry-services/api/v1/Patient",
            params={"_count": "0"},
            timeout=10,
        )
        logger.info("PMIR: gateway session established via pre-flight GET")
    except CezihError as e:
        logger.warning("PMIR: pre-flight GET failed (%s), POST may also fail", str(e)[:100])

    # Submit to PMIR ITI-93.
    # Confirmed endpoint from CEZIH URL list + internal example: /api/iti93
    ep = "patient-registry-services/api/iti93"
    logger.info("PMIR: POST %s", ep)
    response = await fhir_client.request("POST", ep, json_body=bundle)
    import json as _json_log
    logger.info("PMIR success on %s — response: %s", ep, _json_log.dumps(response, ensure_ascii=False)[:3000])
    patient_id = _extract_patient_id(response)
    mbo = _extract_mbo_from_response(response)
    cezih_patient_id = _extract_cezih_patient_identifier(response)
    logger.info("PMIR extracted: patient_id=%s, mbo=%s, cezih_id=%s", patient_id, mbo, cezih_patient_id)
    return {
        "success": True,
        "patient_id": patient_id,
        "mbo": mbo or cezih_patient_id,  # foreigners get unique ID instead of MBO
    }


def _extract_patient_id(response: dict) -> str:
    """Extract patient ID from a PMIR response (may be Bundle or Patient)."""
    if response.get("resourceType") == "Patient":
        return response.get("id", "")
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                return resource.get("id", "")
    return ""


def _extract_mbo_from_response(response: dict) -> str:
    """Extract MBO from a PMIR response (handles both Bundle and Patient)."""
    # Direct Patient resource
    if response.get("resourceType") == "Patient":
        return _find_mbo_in_identifiers(response.get("identifier", []))
    # Bundle response — search entries for Patient
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                return _find_mbo_in_identifiers(resource.get("identifier", []))
    return ""


def _find_mbo_in_identifiers(identifiers: list) -> str:
    for ident in identifiers:
        if ident.get("system") and "MBO" in ident["system"].upper():
            return ident.get("value", "")
    return ""


def _extract_cezih_patient_identifier(response: dict) -> str:
    """Extract CEZIH unique patient identifier from PMIR response.

    Foreigners don't get MBO — they get 'jedinstveni-identifikator-pacijenta'.
    """
    def _find_in_identifiers(identifiers: list) -> str:
        for ident in identifiers:
            sys = ident.get("system", "")
            if "jedinstveni-identifikator" in sys:
                return ident.get("value", "")
        return ""

    if response.get("resourceType") == "Patient":
        return _find_in_identifiers(response.get("identifier", []))
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Patient":
                return _find_in_identifiers(resource.get("identifier", []))
    return ""


# ============================================================
# TC15-17: Case Management (FHIR Messaging + QEDm)
# ============================================================


async def list_visits(client: httpx.AsyncClient, patient_mbo: str) -> list[dict]:
    """List encounters/visits for a patient (QEDm Encounter query).

    GET /ihe-qedm-services/api/v1/Encounter?patient.identifier={SYS_MBO}|{mbo}
    """
    fhir_client = CezihFhirClient(client)
    params = {
        "patient.identifier": f"http://fhir.cezih.hr/specifikacije/identifikatori/MBO|{patient_mbo}",
    }
    response = await fhir_client.get("ihe-qedm-services/api/v1/Encounter", params=params)

    visits: list[dict] = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            enc = entry.get("resource", {})
            visit_id = enc.get("id", "")
            for ident in enc.get("identifier", []):
                if "identifikator-posjete" in (ident.get("system") or ""):
                    visit_id = ident.get("value", visit_id)
            enc_class = enc.get("class", {})
            visit_type = enc_class.get("code", "") if isinstance(enc_class, dict) else ""
            visit_type_display = enc_class.get("display", "") if isinstance(enc_class, dict) else ""
            period = enc.get("period", {})
            reason_list = enc.get("reasonCode", [])
            reason_text = reason_list[0].get("text", "") if reason_list else ""
            # Extract Encounter.type slices (vrsta-posjete and hr-tip-posjete)
            vrsta_posjete = ""
            vrsta_posjete_display = ""
            tip_posjete = ""
            tip_posjete_display = ""
            enc_type_raw = enc.get("type", [])
            if enc_type_raw:
                logger.info("Visit %s Encounter.type raw: %s", visit_id, enc_type_raw)
            for type_entry in enc_type_raw:
                for coding_item in type_entry.get("coding", []):
                    sys = coding_item.get("system", "")
                    if "vrsta-posjete" in sys:
                        vrsta_posjete = coding_item.get("code", "")
                        vrsta_posjete_display = coding_item.get("display", "")
                    elif "hr-tip-posjete" in sys:
                        tip_posjete = coding_item.get("code", "")
                        tip_posjete_display = coding_item.get("display", "")
            # Extract serviceProvider org code
            sp = enc.get("serviceProvider", {})
            sp_ident = sp.get("identifier", {}) if isinstance(sp, dict) else {}
            sp_code = sp_ident.get("value", "") if isinstance(sp_ident, dict) else ""
            logger.info("Visit %s serviceProvider raw: %s → code: %r", visit_id, sp, sp_code)
            # Extract all participant practitioner IDs
            participants = enc.get("participant", [])
            practitioner_ids: list[str] = []
            for p in participants:
                indiv = p.get("individual", {})
                p_ident = indiv.get("identifier", {}) if isinstance(indiv, dict) else {}
                val = p_ident.get("value", "") if isinstance(p_ident, dict) else ""
                if val:
                    practitioner_ids.append(val)
            # Extract linked diagnosis/case IDs
            diagnosis_case_ids: list[str] = []
            for diag in enc.get("diagnosis", []):
                cond = diag.get("condition", {})
                d_ident = cond.get("identifier", {}) if isinstance(cond, dict) else {}
                val = d_ident.get("value", "") if isinstance(d_ident, dict) else ""
                if val:
                    diagnosis_case_ids.append(val)
            visits.append({
                "visit_id": visit_id,
                "patient_mbo": patient_mbo,
                "status": enc.get("status", ""),
                "visit_type": visit_type,
                "visit_type_display": visit_type_display,
                "vrsta_posjete": vrsta_posjete,
                "vrsta_posjete_display": vrsta_posjete_display,
                "tip_posjete": tip_posjete,
                "tip_posjete_display": tip_posjete_display,
                "reason": reason_text,
                "period_start": period.get("start"),
                "period_end": period.get("end"),
                "service_provider_code": sp_code or None,
                "practitioner_id": practitioner_ids[0] if practitioner_ids else None,
                "practitioner_ids": practitioner_ids,
                "diagnosis_case_ids": diagnosis_case_ids,
            })
    return visits


async def retrieve_cases(client: httpx.AsyncClient, patient_mbo: str) -> list[dict]:
    """Retrieve existing cases for a patient (TC15, QEDm)."""
    fhir_client = CezihFhirClient(client)
    params = {
        "patient.identifier": f"http://fhir.cezih.hr/specifikacije/identifikatori/MBO|{patient_mbo}",
    }
    response = await fhir_client.get("ihe-qedm-services/api/v1/Condition", params=params)

    cases = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            cond = entry.get("resource", {})
            case_id = ""
            for ident in cond.get("identifier", []):
                if "identifikator-slucaja" in (ident.get("system") or ""):
                    case_id = ident.get("value", "")
            code = cond.get("code", {})
            coding = code.get("coding", [{}])[0] if code.get("coding") else {}
            clinical = cond.get("clinicalStatus", {})
            cl_coding = clinical.get("coding", [{}])[0] if clinical.get("coding") else {}
            ver_status = cond.get("verificationStatus", {})
            ver_coding = ver_status.get("coding", [{}])[0] if ver_status.get("coding") else {}
            # Extract note from Condition.note[0].text
            notes = cond.get("note", [])
            note_text = notes[0].get("text", "") if notes else ""
            cases.append({
                "case_id": case_id,
                "icd_code": coding.get("code", ""),
                "icd_display": coding.get("display", ""),
                "clinical_status": cl_coding.get("code", ""),
                "verification_status": ver_coding.get("code") or None,
                "onset_date": cond.get("onsetDateTime", ""),
                "abatement_date": cond.get("abatementDateTime") or None,
                "note": note_text or None,
            })
    return cases


async def create_case(
    client: httpx.AsyncClient,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "confirmed",
    note_text: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Create a case via FHIR messaging (TC16, code 2.1).

    Default verificationStatus is "confirmed" because CEZIH's case state machine
    rejects 2.5 resolve (ERR_HEALTH_ISSUE_2004 "Not allowed to perform requested
    transition with current roles") on cases that are still "unconfirmed".
    Users can override via the 2.6 data-update flow.
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_create(
        patient_mbo=patient_mbo, icd_code=icd_code, icd_display=icd_display,
        onset_date=onset_date, practitioner_id=practitioner_id,
        verification_status=verification_status, note_text=note_text,
    )
    local_case_id = condition["identifier"][0]["value"]
    bundle = await build_message_bundle(
        "2.1", condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
        source_oid=source_oid,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to create case")
    return {
        "success": True,
        "local_case_id": local_case_id,
        "cezih_case_id": result["identifier"] or "",
    }


async def create_recurring_case(
    client: httpx.AsyncClient,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    *,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "confirmed",
    note_text: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Create recurring case via FHIR messaging (code 2.2).

    Profile: hr-create-health-issue-recurrence-message|0.1
    Requires: ICD code + verificationStatus + onset[x], identifier FORBIDDEN
    (server assigns new global identifier).
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_create(
        patient_mbo=patient_mbo, icd_code=icd_code, icd_display=icd_display,
        onset_date=onset_date, practitioner_id=practitioner_id,
        verification_status=verification_status, note_text=note_text,
    )
    local_case_id = condition["identifier"][0]["value"]
    bundle = await build_message_bundle(
        "2.2", condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
        source_oid=source_oid,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to create recurring case")
    return {
        "success": True,
        "local_case_id": local_case_id,
        "cezih_case_id": result["identifier"] or "",
    }


async def update_case(
    client: httpx.AsyncClient,
    case_identifier: str,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    action: str,
    source_oid: str | None = None,
) -> dict:
    """Update a case via FHIR messaging (TC17, codes 2.2-2.7).

    Note: 2.8 Delete is not supported — CEZIH rejects every delete
    transition. Use update_case_data with verification_status=
    `entered-in-error` to neutralize a mistaken entry.
    """
    from app.services.cezih.message_builder import (
        CASE_ACTION_MAP,
        CASE_EVENT_PROFILE,
    )

    action_info = CASE_ACTION_MAP.get(action)
    if action_info is None:
        raise CezihError(f"Unknown case action: {action}")

    event_code = action_info["code"] or ""

    if action == "create_recurring":
        # Event 2.2 uses hr-create-health-issue-recurrence-message profile:
        # identifier FORBIDDEN (server assigns), ICD + verificationStatus + onset REQUIRED.
        # Needs full build_condition_create routing — not yet implemented.
        raise CezihError(
            "Ponavljajući slučaj (2.2) zahtijeva implementaciju nove rute "
            "(hr-create-health-issue-recurrence-message). Pratit će u sljedećoj iteraciji."
        )
    else:
        # Per-event CEZIH profile rules live in CASE_EVENT_PROFILE (message_builder.py).
        # Each event code maps to a distinct FHIR StructureDefinition with its own
        # cardinality + slice rules — see docs/CEZIH/findings/case-lifecycle-profile-matrix.md.
        rules = CASE_EVENT_PROFILE.get(event_code)
        if rules is None:
            raise CezihError(f"No CASE_EVENT_PROFILE rules for event code {event_code}")
        condition = build_condition_status_update(
            case_identifier=case_identifier, patient_mbo=patient_mbo,
            clinical_status=rules["cs_value"] if rules["cs"] else None,
            abatement_date=(
                datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                if rules["abatement"] else None
            ),
        )

    fhir_client = CezihFhirClient(client)
    bundle = await build_message_bundle(
        event_code, condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
        source_oid=source_oid,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or f"Failed to {action} case")
    return {"success": True, "action": action}


async def update_case_data(
    client: httpx.AsyncClient,
    case_identifier: str,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    *,
    current_clinical_status: str | None = None,
    verification_status: str | None = None,
    icd_code: str | None = None,
    icd_display: str | None = None,
    onset_date: str | None = None,
    abatement_date: str | None = None,
    note_text: str | None = None,
    source_oid: str | None = None,
) -> dict:
    """Update case metadata via FHIR messaging (code 2.6).

    Updates data fields WITHOUT changing clinicalStatus.
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_data_update(
        case_identifier=case_identifier,
        patient_mbo=patient_mbo,
        current_clinical_status=current_clinical_status,
        verification_status=verification_status,
        icd_code=icd_code, icd_display=icd_display,
        onset_date=onset_date, abatement_date=abatement_date,
        practitioner_id=practitioner_id, note_text=note_text,
    )
    bundle = await build_message_bundle(
        "2.6", condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
        source_oid=source_oid,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to update case data")
    return {"success": True}


# ============================================================
# TC19: Replace Clinical Document
# ============================================================


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
    if not original_document_oid and patient_data.get("mbo"):
        original_document_oid = await _lookup_document_oid(
            fhir_client, original_reference_id, patient_data["mbo"],
        )

    if original_document_oid:
        oid_value = original_document_oid if original_document_oid.startswith("urn:oid:") else f"urn:oid:{original_document_oid}"
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
        fhir_client, patient_data, record_data,
        practitioner_id=practitioner_id, org_code=org_code,
        encounter_id=encounter_id, case_id=case_id,
        practitioner_name=practitioner_name,
        relates_to=relates_to,
        use_external_profile=False,  # External profiles (v1.0.1) rejected by CEZIH test env with 415
    )

    bundle_dict = await add_signature(bundle_dict, practitioner_id or "")

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


# ============================================================
# TC20: Cancel Clinical Document
# ============================================================


async def _lookup_document_oid(
    fhir_client: "CezihFhirClient",
    reference_id: str,
    patient_mbo: str,
) -> str:
    """Look up a document's OID from CEZIH via ITI-67 search.

    CEZIH content_url contains base64-encoded data param with the OID:
    documentUniqueId=urn:ietf:rfc:3986|urn:oid:2.16.840.1.113883.2.7.50.2.1.XXXXXX
    """
    import base64
    from urllib.parse import parse_qs, urlparse

    try:
        params = {
            "patient.identifier": f"{SYS_MBO}|{patient_mbo}",
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

    Strategy: ITI-65 transaction bundle (same as TC19 replace) but with
    status=entered-in-error. Posts a new DocumentReference that replaces the
    original with entered-in-error status — standard IHE MHD document deprecation.

    CEZIH resolves relatesTo.target by OID (masterIdentifier), NOT by server-assigned
    numeric ID. We look up the OID via ITI-67 search if not provided.
    """
    fhir_client = CezihFhirClient(client)

    # Look up document OID from CEZIH if not provided — CEZIH needs OID for relatesTo
    if not original_document_oid and patient_data.get("mbo"):
        original_document_oid = await _lookup_document_oid(
            fhir_client, reference_id, patient_data["mbo"],
        )

    # Build relatesTo with logical OID reference (CEZIH requires OID, not numeric ID)
    if original_document_oid:
        oid_value = original_document_oid if original_document_oid.startswith("urn:oid:") else f"urn:oid:{original_document_oid}"
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
        logger.warning("TC20: No OID found for document %s — falling back to literal reference", reference_id)
        relates_to = {
            "code": "replaces",
            "target": {
                "reference": f"DocumentReference/{reference_id}",
            },
        }

    bundle_dict, new_oid = await _build_document_bundle(
        fhir_client, patient_data, record_data,
        practitioner_id=practitioner_id, org_code=org_code,
        encounter_id=encounter_id, case_id=case_id,
        practitioner_name=practitioner_name,
        relates_to=relates_to,
        use_external_profile=False,
    )

    bundle_dict = await add_signature(bundle_dict, practitioner_id or "")

    # CEZIH rejects entered-in-error status in ITI-65 bundles (ERR_DOM_10057).
    # Cancel works as a "replace" — the new doc supersedes the original.

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
        "status": "entered-in-error",
    }


# ============================================================
# TC22: Retrieve Clinical Document (ITI-68)
# ============================================================


async def retrieve_document(client: httpx.AsyncClient, document_url: str) -> bytes:
    """Retrieve a clinical document binary content (TC22, ITI-68).

    If document_url is a full URL (starts with http), fetch it directly.
    Otherwise, use the ITI-68 service endpoint with the reference ID.
    """
    fhir_client = CezihFhirClient(client)

    if document_url.startswith("http"):
        # Full URL from DocumentReference.content.attachment.url — fetch directly
        # Strip the base URL prefix if it matches our CEZIH gateway path
        import re
        # Extract the path after the gateway prefix
        match = re.search(r"/services-router/gateway/(.+)", document_url)
        if match:
            # Relative path within CEZIH gateway
            path_with_query = match.group(1)
            # Split path and query
            if "?" in path_with_query:
                path, query_string = path_with_query.split("?", 1)
                from urllib.parse import parse_qs
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
        return response
    content = response.get("data", b"") if isinstance(response, dict) else b""
    return content if isinstance(content, bytes) else content.encode("utf-8")
