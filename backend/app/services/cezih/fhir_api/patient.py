"""CEZIH patient service — PDQm queries, insurance check, demographics."""

from __future__ import annotations

import logging
import time
import uuid

import httpx

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError, CezihFhirError
from app.services.cezih.fhir_api.identifiers import (
    _IDENTIFIER_LABEL_MAP,
    _IDENTIFIER_SYSTEM_MAP,
    SYS_JEDINSTVENI,
    SYS_MBO,
)
from app.services.cezih.models import FHIRPatient

logger = logging.getLogger(__name__)

# PDQm result cache — avoids redundant CEZIH calls when insurance check
# is followed by patient import (same query within TTL window).
_PDQM_CACHE: dict[str, tuple[dict, float]] = {}
_PDQM_CACHE_TTL = 300  # 5 minutes


async def search_patient_by_identifier(
    client: httpx.AsyncClient,
    identifier_system: str,
    value: str,
    tenant_id: uuid.UUID,
) -> dict:
    """Search CEZIH patient registry by identifier (MBO, OIB, passport, or EHIC).

    identifier_system must be one of: 'mbo', 'oib', 'putovnica', 'ehic'.
    Uses ITI-78 PDQm — same transaction as fetch_patient_demographics / check_insurance.
    Results are cached for 5 minutes so subsequent import skips the CEZIH call.
    """
    cache_key = f"{tenant_id}:{identifier_system}:{value}"
    cached = _PDQM_CACHE.get(cache_key)
    if cached and (time.time() - cached[1]) < _PDQM_CACHE_TTL:
        logger.info("PDQm cache hit for %s|%s (tenant=%s)", identifier_system, value, tenant_id)
        return cached[0]

    system_uri = _IDENTIFIER_SYSTEM_MAP.get(identifier_system)
    if not system_uri:
        raise CezihError(f"Nepoznati tip identifikatora: {identifier_system}")

    fhir_client = CezihFhirClient(client, tenant_id=tenant_id)
    params = {"identifier": f"{system_uri}|{value}"}
    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params, timeout=10)

    resource_type = response.get("resourceType")
    if resource_type == "OperationOutcome":
        issues = response.get("issue", [])
        diagnostics = "; ".join(
            issue.get("diagnostics") or issue.get("details", {}).get("text", "") for issue in issues
        )
        raise CezihFhirError(
            f"CEZIH greška: {diagnostics or 'Nepoznata greška'}",
            status_code=0,
            operation_outcome=response,
        )
    if resource_type != "Bundle":
        raise CezihError(f"Neočekivan format odgovora iz CEZIH-a (resourceType={resource_type})")

    entries = response.get("entry", [])
    if not entries:
        id_label = {"mbo": "MBO", "oib": "OIB", "putovnica": "putovnica", "ehic": "EHIC broj"}.get(
            identifier_system, identifier_system
        )
        raise CezihError(f"Pacijent s {id_label} '{value}' nije pronađen u CEZIH registru")

    if len(entries) > 1:
        logger.warning(
            "PDQm patient search returned %d entries for %s|%s — using first", len(entries), identifier_system, value
        )

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
            "ulica": ", ".join(lines) if lines else "",
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

    result = {
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

    _PDQM_CACHE[cache_key] = (result, time.time())
    # Lazy eviction of stale entries
    now = time.time()
    stale = [k for k, (_, ts) in _PDQM_CACHE.items() if now - ts > _PDQM_CACHE_TTL]
    for k in stale:
        del _PDQM_CACHE[k]

    return result


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


async def check_insurance(
    client: httpx.AsyncClient,
    system_uri: str,
    value: str,
) -> dict:
    """Patient demographics lookup (ITI-78 PDQm).

    GET /patient-registry-services/api/v1/Patient?identifier={system_uri}|{value}

    For Croatian insured patients pass (SYS_MBO, mbo). For foreigners use the
    jedinstveni-id / EHIC / putovnica identifier returned by the resolver.
    """
    fhir_client = CezihFhirClient(client)
    params = {"identifier": f"{system_uri}|{value}"}

    response = await fhir_client.get("patient-registry-services/api/v1/Patient", params=params, timeout=10)
    # The legacy "mbo" response key is kept for UI compatibility; it always
    # carries the identifier value that was queried, regardless of system.
    queried_value = value

    if response.get("resourceType") == "Bundle":
        entries = response.get("entry", [])
        if not entries:
            return {
                "mbo": queried_value,
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

        oib = ""
        for ident in patient.identifier:
            if ident.system and ident.system.endswith("/OIB") and ident.value:
                oib = ident.value

        spol_map = {"male": "M", "female": "Ž", "other": "Ostalo", "unknown": "Nepoznato"}
        spol = spol_map.get(patient.gender or "", "")

        status_osiguranja = "Aktivan"
        if patient.deceasedDateTime:
            status_osiguranja = "Preminuo"

        return {
            "mbo": queried_value,
            "ime": given,
            "prezime": family,
            "datum_rodjenja": patient.birthDate or "",
            "oib": oib,
            "spol": spol,
            "osiguravatelj": "HZZO" if status_osiguranja == "Aktivan" else "",
            "status_osiguranja": status_osiguranja,
            "datum_smrti": patient.deceasedDateTime or "",
        }

    # Unexpected response format — log full response for debugging
    logger.warning(
        "CEZIH insurance check: unexpected response type: %s — full response: %.500s",
        response.get("resourceType"),
        str(response),
    )
    raise CezihError("Unexpected CEZIH response format for patient lookup")


def _extract_name(patient: FHIRPatient) -> tuple[str, str]:
    """Extract family and given names from a FHIR Patient resource."""
    if not patient.name:
        return "", ""
    official = next((n for n in patient.name if n.use == "official"), patient.name[0])
    family = official.family or ""
    given = " ".join(official.given) if official.given else ""
    return family, given


__all__ = [
    "search_patient_by_identifier",
    "fetch_patient_demographics",
    "check_insurance",
    "_extract_name",
]
