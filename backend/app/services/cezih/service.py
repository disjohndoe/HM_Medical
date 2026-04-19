from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime

import httpx

from app.constants import get_cezih_document_coding
from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError, CezihFhirError
from app.services.cezih.message_builder import (
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

# Re-export from new packages for back-compat during refactor
from app.services.cezih.fhir_api.condition import *     # noqa: F401,F403
from app.services.cezih.fhir_api.documents import *     # noqa: F401,F403
from app.services.cezih.fhir_api.encounter import *     # noqa: F401,F403
from app.services.cezih.fhir_api.identifiers import *   # noqa: F401,F403
from app.services.cezih.fhir_api.pmir import *          # noqa: F401,F403
from app.services.cezih.fhir_api.patient import *       # noqa: F401,F403


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

    Returns concepts with _tier field indicating which method succeeded:
    - 'expand': ValueSet/$expand (FHIR standard)
    - 'lookup': CodeSystem/$lookup (exact match)
    - 'inline': inline concept extraction (fallback)
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
    logger.info("CodeSystem lookup '%s' -> url=%s", system_name, cs_url)

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
                        "_tier": "expand",
                    })
                if concepts:
                    logger.info("CodeSystem '%s': query='%s' -> tier=expand (results=%d)", system_name, query, len(concepts))
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
                    logger.info("CodeSystem '%s': query='%s' -> tier=lookup (exact match)", system_name, query)
                    return [{"code": code_val or query, "display": display_val, "system": cs_url, "_tier": "lookup"}]
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
                    "_tier": "inline",
                })
    logger.info("CodeSystem '%s': query='%s' -> tier=inline (results=%d)", system_name, query, len(results))
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

    used_fallback = False
    try:
        response = await fhir_client.get("terminology-services/api/v1/ValueSet/$expand", params=params)
    except Exception as e:
        logger.warning("ValueSet $expand failed for %s: %s, falling back to plain search", url, e)
        used_fallback = True
        response = await fhir_client.get("terminology-services/api/v1/ValueSet", params=params)

    concepts = []
    # Try expansion first (standard path)
    expansion = response.get("expansion", {})
    if expansion:
        for contains in expansion.get("contains", []):
            concepts.append({
                "code": contains.get("code", ""),
                "display": contains.get("display", ""),
                "system": contains.get("system", ""),
            })
    else:
        # Fallback: extract from Bundle.entry
        for entry in response.get("entry", []):
            resource = entry.get("resource", {})
            if resource.get("resourceType") == "Concept":
                concepts.append({
                    "code": resource.get("code", ""),
                    "display": resource.get("display", ""),
                    "system": resource.get("system", ""),
                })

    return {
        "url": url,
        "concepts": concepts,
        "total": len(concepts),
        "_method": "$expand" if not used_fallback else "search (fallback)",
    }


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
