"""CEZIH Encounter (visit) service — QEDm (TC14)."""

from __future__ import annotations

import logging

from app.services.cezih.client import CezihFhirClient

logger = logging.getLogger(__name__)


async def list_visits(
    client,
    system_uri: str,
    value: str,
) -> list[dict]:
    """List encounters/visits for a patient (QEDm Encounter query).

    GET /ihe-qedm-services/api/v1/Encounter?patient.identifier={system_uri}|{value}
    """
    fhir_client = CezihFhirClient(client)
    patient_mbo = value  # kept as dict-key for back-compat with UI/mirror rows
    params = {
        "patient.identifier": f"{system_uri}|{value}",
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
            visits.append(
                {
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
                }
            )
    return visits


__all__ = ["list_visits"]
