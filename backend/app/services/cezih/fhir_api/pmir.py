"""CEZIH PMIR (Foreigner Registration) service — ITI-93 (TC11)."""

from __future__ import annotations

import logging
import uuid

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError
from app.services.cezih.message_builder import (
    _now_iso,
    add_signature,
    org_ref,
    practitioner_ref,
)

logger = logging.getLogger(__name__)


async def register_foreigner(
    client,
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
    fhir_client = CezihFhirClient(client)
    # Use urn:uuid: for ALL fullUrls and references (like working encounters).
    # The official Simplifier example uses plain UUIDs, but CEZIH's HAPI server
    # resolves plain UUIDs as literal references (Bundle/{uuid}) instead of
    # matching fullUrl — causing "Reference_REF_CantResolve".
    patient_uuid = str(uuid.uuid4())
    inner_bundle_uuid = f"urn:uuid:{uuid.uuid4()}"
    header_uuid = f"urn:uuid:{uuid.uuid4()}"

    # Build Patient resource per HRRegisterPatient profile.
    # Field order and content matches the official Simplifier example exactly.
    # Profile constraints: identifier min=1 max=2 (rules=closed: putovnica + europska-kartica only),
    # name min=1 max=1, address min=1 max=1, address.country min=1.
    # birthDate and gender are standard FHIR Patient fields — include them when provided.
    identifiers = []
    if patient_data.get("broj_putovnice"):
        identifiers.append(
            {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/putovnica",
                "value": patient_data["broj_putovnice"],
            }
        )
    if patient_data.get("ehic_broj"):
        identifiers.append(
            {
                "system": "http://fhir.cezih.hr/specifikacije/identifikatori/europska-kartica",
                "value": patient_data["ehic_broj"],
            }
        )

    # address.country binding=required to ValueSet/drzave (ISO 3166-1 alpha-3).
    # Frontend may send alpha-2 (DE) — convert to alpha-3 (DEU).
    from app.services.cezih._country_codes import to_alpha3

    country = to_alpha3(patient_data.get("drzavljanstvo") or "")
    patient_resource: dict = {
        "resourceType": "Patient",
        "identifier": identifiers,
        "active": True,
        "name": [
            {
                "use": "official",
                "family": patient_data["prezime"],
                "given": [patient_data["ime"]],
            }
        ],
        "address": [{"country": country}],
    }
    if patient_data.get("datum_rodjenja"):
        patient_resource["birthDate"] = patient_data["datum_rodjenja"]
    _gender_map = {
        "M": "male",
        "Z": "female",
        "Ž": "female",
        "F": "female",
        "male": "male",
        "female": "female",
        "unknown": "unknown",
    }
    raw_spol = patient_data.get("spol") or ""
    fhir_gender = _gender_map.get(raw_spol)
    if fhir_gender:
        patient_resource["gender"] = fhir_gender

    # Inner Bundle (type=history).
    # NOTE: working encounters use NO meta.profile on individual resources.
    # CEZIH knows expected profiles from the StructureDefinition, not meta.profile.
    inner_bundle = {
        "resourceType": "Bundle",
        "type": "history",
        "entry": [
            {
                "fullUrl": f"urn:uuid:{patient_uuid}",
                "resource": patient_resource,
                "request": {"method": "POST", "url": "Patient"},
                "response": {"status": "201"},
            }
        ],
    }

    # MessageHeader — IHE PMIR profile, matching official example field order
    source_endpoint = (
        f"urn:oid:{source_oid}"
        if source_oid
        else f"urn:oid:{org_code}"
        if org_code
        else "urn:oid:2.16.840.1.113883.2.7"
    )
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
        "id": str(uuid.uuid4()),
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
    response: dict = await fhir_client.request("POST", ep, json_body=bundle)  # type: ignore[assignment]
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


__all__ = [
    "register_foreigner",
    "_extract_patient_id",
    "_extract_mbo_from_response",
    "_find_mbo_in_identifiers",
    "_extract_cezih_patient_identifier",
]
