"""CEZIH Condition (case) service — FHIR Messaging + QEDm (TC15-17)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.services.cezih.client import CezihFhirClient
from app.services.cezih.exceptions import CezihError
from app.services.cezih.message_builder import (
    CASE_ACTION_MAP,
    CASE_EVENT_PROFILE,
    ID_MBO,
    add_signature,
    build_condition_create,
    build_condition_data_update,
    build_condition_status_update,
    build_message_bundle,
    parse_message_response,
)

logger = logging.getLogger(__name__)


async def _ensure_case_session(
    fhir_client: CezihFhirClient,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
) -> None:
    """Pre-flight GET before POST to health-issue-services.

    Per TC11 (docs/CEZIH/findings/TC11-PMIR-auth-blocker.md): CEZIH's gateway
    establishes session cookies per service-domain. A first POST on a cold
    domain gets redirected to Keycloak, which rejects the fhir+json body with
    415 and surfaces as ERR_DS_1002. A GET goes through the redirect cleanly
    (no body) and sets the cookie.

    Uses a valid Condition search (patient.identifier + _count=0) rather than
    a bare _count=0. QEDm requires the `patient` query param — without it the
    server returns 400 ("Missing mandatory parameter"). The 400 still warms
    the cookie but surfaces as noisy errors in logs/metrics. Since we always
    have the patient MBO at call time, we do a real 200-OK query instead.

    Extsigner users (certpubws.cezih.hr) need this before every case POST
    because their encounter-services cookie doesn't carry over to
    health-issue-services. Smartcard users (certws2.cezih.hr) are already
    warmed up by the agent on connect but the pre-flight is harmless either way.
    """
    try:
        await fhir_client.get(
            "ihe-qedm-services/api/v1/Condition",
            params={
                "patient.identifier": f"{identifier_system}|{patient_mbo}",
                "_count": "0",
            },
            timeout=10,
        )
        logger.info("Case: gateway session established via pre-flight GET")
    except CezihError as e:
        logger.warning("Case: pre-flight GET failed (%s), POST may also fail", str(e)[:100])


async def retrieve_cases(
    client,
    system_uri: str,
    value: str,
) -> list[dict]:
    """Retrieve existing cases for a patient (TC15, QEDm)."""
    fhir_client = CezihFhirClient(client)
    params = {
        "patient.identifier": f"{system_uri}|{value}",
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
            coding = (code.get("coding") or [{}])[0]
            clinical = cond.get("clinicalStatus", {})
            cl_coding = (clinical.get("coding") or [{}])[0]
            ver_status = cond.get("verificationStatus", {})
            ver_coding = (ver_status.get("coding") or [{}])[0]
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
    client,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    icd_code: str,
    icd_display: str,
    onset_date: str,
    verification_status: str = "confirmed",
    note_text: str | None = None,
    source_oid: str | None = None,
    *,
    identifier_system: str | None = None,
) -> dict:
    """Create a case via FHIR messaging (TC16, code 2.1).

    Default verificationStatus is "confirmed" because CEZIH's case state machine
    rejects 2.5 resolve (ERR_HEALTH_ISSUE_2004 "Not allowed to perform requested
    transition with current roles") on cases that are still "unconfirmed".
    Users can override via the 2.6 data-update flow.
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_create(
        patient_mbo=patient_mbo,
        identifier_system=identifier_system or ID_MBO,
        icd_code=icd_code, icd_display=icd_display,
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
    await _ensure_case_session(fhir_client, patient_mbo, identifier_system or ID_MBO)
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
    client,
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
    identifier_system: str | None = None,
) -> dict:
    """Create recurring case via FHIR messaging (code 2.2).

    Profile: hr-create-health-issue-recurrence-message|0.1
    Requires: ICD code + verificationStatus + onset[x], identifier FORBIDDEN
    (server assigns new global identifier).
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_create(
        patient_mbo=patient_mbo,
        identifier_system=identifier_system or ID_MBO,
        icd_code=icd_code, icd_display=icd_display,
        onset_date=onset_date, practitioner_id=practitioner_id,
        verification_status=verification_status, note_text=note_text,
    )
    local_case_id = condition["identifier"][0]["value"]
    # 2.2 profile: identifier max=0 (FORBIDDEN) — server assigns global ID
    condition.pop("identifier", None)
    bundle = await build_message_bundle(
        "2.2", condition,
        sender_org_code=org_code, author_practitioner_id=practitioner_id,
        source_oid=source_oid,
    )
    bundle = await add_signature(bundle, practitioner_id, http_client=client)
    await _ensure_case_session(fhir_client, patient_mbo, identifier_system or ID_MBO)
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
    client,
    case_identifier: str,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    action: str,
    source_oid: str | None = None,
    *,
    identifier_system: str | None = None,
) -> dict:
    """Update case status via FHIR messaging (TC17, codes 2.3-2.5, 2.9).

    2.2 (recurring) routes through create_recurring_case().
    2.6 (data update) routes through update_case_data().
    Delete (2.7) is NOT shipped — use 2.6 with verificationStatus=entered-in-error.
    """
    action_info = CASE_ACTION_MAP.get(action)
    if action_info is None:
        raise CezihError(f"Unknown case action: {action}")

    event_code = action_info["code"] or ""

    rules = CASE_EVENT_PROFILE.get(event_code)
    if rules is None:
        raise CezihError(f"No CASE_EVENT_PROFILE rules for event code {event_code}")

    condition = build_condition_status_update(
        case_identifier=case_identifier, patient_mbo=patient_mbo,
        identifier_system=identifier_system or ID_MBO,
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
    await _ensure_case_session(fhir_client, patient_mbo, identifier_system or ID_MBO)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or f"Failed to {action} case")
    return {"success": True, "action": action}


async def update_case_data(
    client,
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
    identifier_system: str | None = None,
) -> dict:
    """Update case metadata via FHIR messaging (code 2.6).

    Updates data fields WITHOUT changing clinicalStatus.
    """
    fhir_client = CezihFhirClient(client)
    condition = build_condition_data_update(
        case_identifier=case_identifier,
        patient_mbo=patient_mbo,
        identifier_system=identifier_system or ID_MBO,
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
    await _ensure_case_session(fhir_client, patient_mbo, identifier_system or ID_MBO)
    response = await fhir_client.process_message("health-issue-services/api/v1", bundle)
    result = parse_message_response(response)
    if not result["success"]:
        raise CezihError(result.get("error_message") or "Failed to update case data")
    return {"success": True}


__all__ = [
    "retrieve_cases",
    "create_case",
    "create_recurring_case",
    "update_case",
    "update_case_data",
]
