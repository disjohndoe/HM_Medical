from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError
from app.services.cezih.message_builder import (
    add_signature,
    build_condition_create,
    build_condition_data_update,
    build_condition_delete,
    build_condition_status_update,
    build_encounter_cancel,
    build_encounter_close,
    build_encounter_create,
    build_encounter_reopen,
    build_encounter_update,
    build_message_bundle,
    parse_message_response,
)
from app.services.cezih.models import (
    FHIRBundle,
    FHIRBundleEntry,
    FHIRCodeableConcept,
    FHIRCoding,
    FHIRDocumentReference,
    FHIRPatient,
    FHIRReference,
)

logger = logging.getLogger(__name__)

# CEZIH identifier systems
SYS_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/mbo"
SYS_OIB = "http://fhir.cezih.hr/specifikacije/identifikatori/oib"


async def check_insurance(client: httpx.AsyncClient, mbo: str) -> dict:
    """Patient demographics lookup by MBO (ITI-78 PDQm).

    GET /patient-registry-services/api/v1/Patient?identifier={SYS_MBO}|{mbo}
    """
    fhir_client = CezihFhirClient(client)
    params = {"identifier": f"{SYS_MBO}|{mbo}"}

    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params)

    if response.get("resourceType") == "Bundle":
        entries = response.get("entry", [])
        if not entries:
            return {
                "mbo": mbo,
                "ime": "",
                "prezime": "",
                "datum_rodjenja": "",
                "osiguravatelj": "",
                "status_osiguranja": "Nije pronađen",
                "broj_osiguranja": "",
            }

        patient = FHIRPatient.model_validate(entries[0].get("resource", {}))
        family, given = _extract_name(patient)

        # Extract insurance number from identifiers
        broj = ""
        osiguravatelj = "HZZO"  # Default for CEZIH-found patients
        for ident in patient.identifier:
            if ident.system and "osiguranje" in ident.system.lower() and ident.value:
                broj = ident.value

        return {
            "mbo": mbo,
            "ime": given,
            "prezime": family,
            "datum_rodjenja": patient.birthDate or "",
            "osiguravatelj": osiguravatelj,
            "status_osiguranja": "Aktivan",
            "broj_osiguranja": broj,
        }

    # Unexpected response format
    logger.warning("CEZIH insurance check: unexpected response type: %s", response.get("resourceType"))
    raise CezihError("Unexpected CEZIH response format for patient lookup")


async def send_enalaz(
    client: httpx.AsyncClient,
    patient_data: dict,
    record_data: dict,
    uputnica_id: str | None = None,
) -> dict:
    """Send clinical document / finding (ITI-65 MHD).

    POST /doc-mhd-svc/api/v1/iti-65-service
    """
    fhir_client = CezihFhirClient(client)

    # Build DocumentReference for the finding
    doc_ref = FHIRDocumentReference(
        status="current",
        type=FHIRCodeableConcept(
            coding=[FHIRCoding(
                system="http://fhir.cezih.hr/specifikacije/vrste-dokumenata",
                code=record_data.get("tip", "nalaz"),
                display=record_data.get("tip_display", "Nalaz"),
            )]
        ),
        subject=FHIRReference(
            reference=f"Patient/{patient_data.get('mbo', '')}",
            display=f"{patient_data.get('ime', '')} {patient_data.get('prezime', '')}",
        ),
        date=datetime.now(UTC).isoformat(),
    )

    # Wrap in a Bundle (ITI-65 expects a Bundle)
    bundle = FHIRBundle(
        type="document",
        timestamp=datetime.now(UTC).isoformat(),
        entry=[FHIRBundleEntry(resource=doc_ref.model_dump(by_alias=True))],
    )

    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle.model_dump(by_alias=True),
    )

    # Extract reference ID from response
    ref_id = ""
    if response.get("resourceType") == "DocumentReference":
        ref_id = response.get("id", "")
    elif response.get("resourceType") == "Bundle":
        entries = response.get("entry", [])
        if entries:
            resource = entries[0].get("resource", {})
            ref_id = resource.get("id", "")

    if not ref_id:
        ref_id = f"FHIR-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    return {
        "success": True,
        "reference_id": ref_id,
        "sent_at": datetime.now(UTC).isoformat(),
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
    if status_filter:
        params["status"] = status_filter

    response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)

    items = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            doc_ref = entry.get("resource", {})
            items.append({
                "id": doc_ref.get("id", ""),
                "datum_izdavanja": doc_ref.get("date", ""),
                "izdavatelj": _extract_reference_display(doc_ref.get("context", {}).get("source", {})),
                "svrha": _extract_codeable_text(doc_ref.get("type")),
                "specijalist": _extract_reference_display(doc_ref.get("context", {}).get("encounter", {})),
                "status": _map_fhir_status(doc_ref.get("status", "current")),
                "type": _extract_codeable_text(doc_ref.get("type")),
            })

    return items


async def retrieve_euputnice(client: httpx.AsyncClient) -> list[dict]:
    """Retrieve e-Uputnice from CEZIH (ITI-67 DocumentReference search).

    GET /doc-mhd-svc/api/v1/DocumentReference?type=uputnica
    Convenience wrapper around search_documents for backward compatibility.
    """
    fhir_client = CezihFhirClient(client)
    params = {
        "type": "http://fhir.cezih.hr/specifikacije/vrste-dokumenata|uputnica",
    }

    response = await fhir_client.get("doc-mhd-svc/api/v1/DocumentReference", params=params)

    items = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            doc_ref = entry.get("resource", {})
            items.append({
                "id": doc_ref.get("id", ""),
                "datum_izdavanja": doc_ref.get("date", ""),
                "izdavatelj": _extract_reference_display(doc_ref.get("context", {}).get("source", {})),
                "svrha": _extract_codeable_text(doc_ref.get("type")),
                "specijalist": _extract_reference_display(doc_ref.get("context", {}).get("encounter", {})),
                "status": _map_fhir_status(doc_ref.get("status", "current")),
            })

    return items


async def send_erecept(
    client: httpx.AsyncClient,
    patient_data: dict,
    lijekovi: list[dict],
) -> dict:
    """Send e-prescription (stub — not in 22 test cases yet)."""
    logger.warning("CEZIH e-Recept: real API not yet implemented, returning stub")
    import os
    return {
        "success": True,
        "recept_id": f"FHIR-ER-{os.urandom(4).hex()}",
    }


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


async def lookup_oid(client: httpx.AsyncClient, oid: str) -> dict:
    """Look up OID in CEZIH identifier registry (TC6).

    Official endpoint: identifier-registry-services/api/v1/oid/generateOIDBatch (port 9443).
    """
    fhir_client = CezihFhirClient(client)
    response = await fhir_client.post(
        "identifier-registry-services/api/v1/oid/generateOIDBatch",
        json_body={"oid": oid},
    )
    return {
        "oid": oid,
        "name": response.get("name", ""),
        "responsible_org": response.get("responsibleOrg", ""),
        "status": response.get("status", ""),
    }


# ============================================================
# TC7: Code System Query ITI-96 (generalized)
# ============================================================


async def query_code_system(
    client: httpx.AsyncClient, system_name: str, query: str, count: int = 20,
) -> list[dict]:
    """Query a CEZIH code system (ITI-96 SVCM)."""
    fhir_client = CezihFhirClient(client)
    params = {"name": system_name, "filter": query, "_count": str(count)}
    response = await fhir_client.get("terminology-services/api/v1/CodeSystem", params=params)

    results = []
    if response.get("resourceType") == "Bundle":
        for entry in response.get("entry", []):
            cs = entry.get("resource", {})
            for concept in cs.get("concept", []):
                results.append({
                    "code": concept.get("code", ""),
                    "display": concept.get("display", ""),
                    "system": cs.get("url", system_name),
                })
    return results


# ============================================================
# TC8: Value Set Expand ITI-95
# ============================================================


async def expand_value_set(
    client: httpx.AsyncClient, url: str, filter_text: str | None = None,
) -> dict:
    """Expand a CEZIH value set (ITI-95 SVCM)."""
    fhir_client = CezihFhirClient(client)
    params: dict = {"url": url}
    if filter_text:
        params["filter"] = filter_text
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


async def register_foreigner(client: httpx.AsyncClient, patient_data: dict) -> dict:
    """Register a foreigner in CEZIH (PMIR)."""
    fhir_client = CezihFhirClient(client)
    patient_resource = {
        "resourceType": "Patient",
        "name": [{"family": patient_data["prezime"], "given": [patient_data["ime"]]}],
        "birthDate": patient_data["datum_rodjenja"],
        "gender": patient_data.get("spol", "unknown"),
        "identifier": [],
    }
    if patient_data.get("broj_putovnice"):
        patient_resource["identifier"].append({
            "system": "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica",
            "value": patient_data["broj_putovnice"],
        })
    if patient_data.get("ehic_broj"):
        patient_resource["identifier"].append({
            "system": "http://fhir.cezih.hr/specifikacije/identifikatori/EHIC",
            "value": patient_data["ehic_broj"],
        })

    # PMIR ITI-93: Official endpoint is /patient-registry-services/api/iti93
    response = await fhir_client.post(
        "patient-registry-services/api/iti93",
        json_body=patient_resource,
    )
    return {
        "success": True,
        "patient_id": response.get("id", ""),
        "mbo": _extract_mbo_from_response(response),
    }


def _extract_mbo_from_response(response: dict) -> str:
    for ident in response.get("identifier", []):
        if ident.get("system") and "MBO" in ident["system"].upper():
            return ident.get("value", "")
    return ""


# ============================================================
# TC12-14: Visit Management (FHIR Messaging)
# ============================================================


async def create_visit(
    client: httpx.AsyncClient,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    admission_type_code: str = "9",
) -> dict:
    """Create a visit via FHIR messaging (TC12, code 1.1)."""
    fhir_client = CezihFhirClient(client)
    encounter = build_encounter_create(
        patient_mbo=patient_mbo, practitioner_id=practitioner_id,
        org_code=org_code, period_start=period_start,
        admission_type_code=admission_type_code,
    )
    bundle = await build_message_bundle(
        "1.1", encounter,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("encounter-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to create visit")
    return {"visit_id": result["identifier"] or "", "success": True}


async def update_visit(
    client: httpx.AsyncClient,
    visit_identifier: str,
    practitioner_id: str,
    org_code: str,
    **updates: str,
) -> dict:
    """Update a visit via FHIR messaging (TC13, code 1.2)."""
    fhir_client = CezihFhirClient(client)
    encounter = build_encounter_update(
        visit_identifier=visit_identifier,
        period_start=updates.get("period_start"),
        admission_type_code=updates.get("admission_type_code"),
        org_code=org_code,
        practitioner_id=practitioner_id,
    )
    bundle = await build_message_bundle(
        "1.2", encounter,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("encounter-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to update visit")
    return {"success": True}


async def close_visit(
    client: httpx.AsyncClient,
    visit_identifier: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    period_end: str,
    admission_type_code: str = "9",
    diagnosis_case_id: str | None = None,
) -> dict:
    """Close a visit via FHIR messaging (TC14, code 1.3)."""
    fhir_client = CezihFhirClient(client)
    encounter = build_encounter_close(
        visit_identifier=visit_identifier,
        period_start=period_start, period_end=period_end,
        admission_type_code=admission_type_code,
        org_code=org_code, diagnosis_case_id=diagnosis_case_id,
    )
    bundle = await build_message_bundle(
        "1.3", encounter,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("encounter-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to close visit")
    return {"success": True}


async def reopen_visit(
    client: httpx.AsyncClient,
    visit_identifier: str,
    practitioner_id: str,
    org_code: str,
    admission_type_code: str = "9",
) -> dict:
    """Reopen a closed visit via FHIR messaging (code 1.5)."""
    fhir_client = CezihFhirClient(client)
    encounter = build_encounter_reopen(
        visit_identifier=visit_identifier,
        admission_type_code=admission_type_code,
        org_code=org_code,
    )
    bundle = await build_message_bundle(
        "1.5", encounter,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("encounter-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to reopen visit")
    return {"success": True}


async def cancel_visit(
    client: httpx.AsyncClient,
    visit_identifier: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    period_end: str | None = None,
    admission_type_code: str = "9",
    diagnosis_case_id: str | None = None,
) -> dict:
    """Cancel/storno a visit via FHIR messaging (code 1.4)."""
    fhir_client = CezihFhirClient(client)
    encounter = build_encounter_cancel(
        visit_identifier=visit_identifier,
        period_start=period_start, period_end=period_end,
        admission_type_code=admission_type_code,
        org_code=org_code, diagnosis_case_id=diagnosis_case_id,
    )
    bundle = await build_message_bundle(
        "1.4", encounter,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    response = await fhir_client.process_message("encounter-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to cancel visit")
    return {"success": True}


# ============================================================
# TC15-17: Case Management (FHIR Messaging + QEDm)
# ============================================================


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
            cases.append({
                "case_id": case_id,
                "icd_code": coding.get("code", ""),
                "icd_display": coding.get("display", ""),
                "clinical_status": cl_coding.get("code", ""),
                "onset_date": cond.get("onsetDateTime", ""),
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
    verification_status: str = "unconfirmed",
    note_text: str | None = None,
) -> dict:
    """Create a case via FHIR messaging (TC16, code 2.1)."""
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


async def update_case(
    client: httpx.AsyncClient,
    case_identifier: str,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    action: str,
) -> dict:
    """Update a case via FHIR messaging (TC17, codes 2.2-2.8)."""
    from app.services.cezih.message_builder import CASE_ACTION_MAP

    action_info = CASE_ACTION_MAP.get(action)
    if action_info is None:
        raise CezihError(f"Unknown case action: {action}")

    event_code = action_info["code"] or ""
    clinical_status = action_info["clinical_status"]

    if action == "delete":
        condition = build_condition_delete(case_identifier=case_identifier, patient_mbo=patient_mbo)
    else:
        condition = build_condition_status_update(
            case_identifier=case_identifier, patient_mbo=patient_mbo,
            clinical_status=clinical_status,
        )

    fhir_client = CezihFhirClient(client)
    bundle = await build_message_bundle(
        event_code, condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
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
) -> dict:
    """Replace a clinical document (TC19, ITI-65 with relatesTo)."""
    fhir_client = CezihFhirClient(client)
    doc_ref = FHIRDocumentReference(
        status="current",
        type=FHIRCodeableConcept(
            coding=[FHIRCoding(
                system="http://fhir.cezih.hr/specifikacije/vrste-dokumenata",
                code=record_data.get("tip", "nalaz"),
            )]
        ),
        subject=FHIRReference(reference=f"Patient/{patient_data.get('mbo', '')}"),
        date=datetime.now(UTC).isoformat(),
    )
    doc_dict = doc_ref.model_dump(by_alias=True)
    doc_dict["relatesTo"] = [
        {"code": "replaces", "target": {"reference": f"DocumentReference/{original_reference_id}"}},
    ]
    bundle = FHIRBundle(
        type="document",
        timestamp=datetime.now(UTC).isoformat(),
        entry=[FHIRBundleEntry(resource=doc_dict)],
    )
    response = await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle.model_dump(by_alias=True),
    )
    ref_id = response.get("id", f"FHIR-R-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")
    return {"success": True, "new_reference_id": ref_id, "replaced_reference_id": original_reference_id}


# ============================================================
# TC20: Cancel Clinical Document
# ============================================================


async def cancel_document(client: httpx.AsyncClient, reference_id: str) -> dict:
    """Cancel/storno a clinical document (TC20, ITI-65 status update)."""
    fhir_client = CezihFhirClient(client)
    doc_ref = {
        "resourceType": "DocumentReference",
        "id": reference_id,
        "status": "entered-in-error",
    }
    bundle = FHIRBundle(
        type="document",
        timestamp=datetime.now(UTC).isoformat(),
        entry=[FHIRBundleEntry(resource=doc_ref)],
    )
    await fhir_client.post(
        "doc-mhd-svc/api/v1/iti-65-service",
        json_body=bundle.model_dump(by_alias=True),
    )
    return {"success": True, "reference_id": reference_id, "status": "entered-in-error"}


# ============================================================
# TC22: Retrieve Clinical Document (ITI-68)
# ============================================================


async def retrieve_document(client: httpx.AsyncClient, document_url: str) -> bytes:
    """Retrieve a clinical document binary content (TC22, ITI-68).

    Official endpoint: doc-mhd-svc/api/v1/iti-68-service?url={document_url}
    If document_url is a full URL, pass it as a query parameter to the ITI-68 service.
    """
    fhir_client = CezihFhirClient(client)
    # ITI-68: use the dedicated retrieve service endpoint
    response = await fhir_client.get(
        "doc-mhd-svc/api/v1/iti-68-service",
        params={"url": document_url},
    )
    content = response.get("data", b"") if isinstance(response, dict) else b""
    return content if isinstance(content, bytes) else content.encode("utf-8")
