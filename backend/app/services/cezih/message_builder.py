# ruff: noqa: N815 — FHIR spec requires camelCase field names
"""FHIR message Bundle builder for CEZIH $process-message operations.

Builds Bundle type="message" with MessageHeader + resource + digital signature.
Used for Visit Management (codes 1.x) and Case Management (codes 2.x).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# --- Constants: CEZIH FHIR identifier systems ---

MESSAGE_TYPE_SYSTEM = "http://ent.hr/fhir/CodeSystem/ehe-message-types"
SIGNATURE_TYPE_SYSTEM = "urn:iso-astm:E1762-95:2013"
SIGNATURE_TYPE_CODE = "1.2.840.10065.1.12.1.1"  # Author's signature

ID_MBO = "http://fhir.cezih.hr/specifikacije/identifikatori/MBO"
ID_ORG = "http://fhir.cezih.hr/specifikacije/identifikatori/HZZO-sifra-zdravstvene-organizacije"
ID_PRACTITIONER = "http://fhir.cezih.hr/specifikacije/identifikatori/HZJZ-broj-zdravstvenog-djelatnika"
ID_VISIT = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-posjete"
ID_CASE_GLOBAL = "http://fhir.cezih.hr/specifikacije/identifikatori/identifikator-slucaja"
ID_CASE_LOCAL = "http://fhir.cezih.hr/specifikacije/identifikatori/lokalni-identifikator-slucaja"
ID_CASE_REF = "http://fhir.cezih.hr/specifikacije/identifikatori/slucaj"

CS_ADMISSION_TYPE = "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"
CS_ICD10_HR = "http://fhir.cezih.hr/specifikacije/CodeSystem/icd10-hr"
CS_COST_PARTICIPATION = "http://fhir.cezih.hr/specifikacije/CodeSystem/sudjelovanje-u-troskovima"
CS_COST_EXEMPTION = "http://fhir.cezih.hr/specifikacije/CodeSystem/sifra-oslobodjenja-od-sudjelovanja-u-troskovima"
CS_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/CodeSystem/annotation-type"
CS_CONDITION_VER_STATUS = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CS_CONDITION_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"

EXT_COST_PARTICIPATION = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-troskovi-sudjelovanje"
EXT_ANNOTATION_TYPE = "http://fhir.cezih.hr/specifikacije/StructureDefinition/hr-annotation-type"


# --- Helper: Logical references (identifier-based, no literal URL) ---


def patient_ref(mbo: str) -> dict[str, Any]:
    return {"type": "Patient", "identifier": {"system": ID_MBO, "value": mbo}}


def org_ref(org_code: str) -> dict[str, Any]:
    return {"type": "Organization", "identifier": {"system": ID_ORG, "value": org_code}}


def practitioner_ref(hzjz_id: str) -> dict[str, Any]:
    return {"type": "Practitioner", "identifier": {"system": ID_PRACTITIONER, "value": hzjz_id}}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# --- Message Bundle Builder ---


async def build_message_bundle(
    event_code: str,
    resource: dict[str, Any],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    source_oid: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='message' with MessageHeader and resource.

    Does NOT add signature — call add_signature() separately for real mode.
    """
    sender_org_code = sender_org_code or settings.CEZIH_ORG_CODE
    source_oid = source_oid or settings.CEZIH_OID

    resource_uuid = str(uuid.uuid4())
    header_uuid = str(uuid.uuid4())

    message_header: dict[str, Any] = {
        "resourceType": "MessageHeader",
        "eventCoding": {
            "system": MESSAGE_TYPE_SYSTEM,
            "code": event_code,
        },
        "source": {"endpoint": f"urn:oid:{source_oid}" if source_oid else "urn:oid:0.0.0.0"},
        "focus": [{"reference": f"urn:uuid:{resource_uuid}"}],
    }

    if sender_org_code:
        message_header["sender"] = org_ref(sender_org_code)

    if author_practitioner_id:
        message_header["author"] = practitioner_ref(author_practitioner_id)

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
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

    return bundle


async def add_signature(
    bundle: dict[str, Any],
    practitioner_id: str,
    sign_fn: Any = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Add a digital signature to the Bundle.

    In mock mode, adds a fake signature. In real mode, calls the signing service.
    """
    from app.services.cezih_signing import sign_document

    # Serialize bundle without signature for hashing
    bundle_bytes = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8")

    if sign_fn:
        result = await sign_fn(bundle_bytes)
    elif http_client:
        result = await sign_document(http_client, bundle_bytes)
    else:
        # Mock fallback — base64 placeholder
        import base64
        result = {"signature": base64.b64encode(b"mock-signature-for-testing").decode()}

    signature_data = result.get("signature", "")

    bundle["signature"] = {
        "type": [
            {
                "system": SIGNATURE_TYPE_SYSTEM,
                "code": SIGNATURE_TYPE_CODE,
            },
        ],
        "when": _now_iso(),
        "who": practitioner_ref(practitioner_id),
        "data": signature_data,
    }

    return bundle


# --- Encounter Resource Builders ---


def build_encounter_create(
    *,
    patient_mbo: str,
    practitioner_id: str,
    org_code: str,
    period_start: str,
    admission_type_code: str = "9",
    admission_type_display: str | None = None,
    cost_participation_code: str | None = None,
    cost_exemption_code: str | None = None,
) -> dict[str, Any]:
    """Build Encounter for create visit (message code 1.1).

    NO identifier — CEZIH assigns one.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "status": "in-progress",
        "class": {
            "system": CS_ADMISSION_TYPE,
            "code": admission_type_code,
            **({"display": admission_type_display} if admission_type_display else {}),
        },
        "subject": patient_ref(patient_mbo),
        "participant": [
            {"individual": practitioner_ref(practitioner_id)},
        ],
        "period": {"start": period_start},
        "serviceProvider": org_ref(org_code),
    }

    if cost_participation_code:
        ext: dict[str, Any] = {
            "url": EXT_COST_PARTICIPATION,
            "extension": [
                {"url": "oznaka", "valueCoding": {"system": CS_COST_PARTICIPATION, "code": cost_participation_code}},
            ],
        }
        if cost_exemption_code:
            ext["extension"].append(
                {"url": "sifra-oslobodjenja", "valueCoding": {
                    "system": CS_COST_EXEMPTION, "code": cost_exemption_code,
                }},
            )
        encounter["extension"] = [ext]

    return encounter


def build_encounter_update(
    *,
    visit_identifier: str,
    period_start: str | None = None,
    admission_type_code: str | None = None,
    admission_type_display: str | None = None,
    org_code: str | None = None,
    practitioner_id: str | None = None,
) -> dict[str, Any]:
    """Build Encounter for update visit (message code 1.2).

    MUST have identifier from CEZIH.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_VISIT, "value": visit_identifier}],
        "status": "in-progress",
    }

    if admission_type_code:
        encounter["class"] = {
            "system": CS_ADMISSION_TYPE,
            "code": admission_type_code,
            **({"display": admission_type_display} if admission_type_display else {}),
        }

    if period_start:
        encounter["period"] = {"start": period_start}

    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)

    if practitioner_id:
        encounter["participant"] = [{"individual": practitioner_ref(practitioner_id)}]

    return encounter


def build_encounter_cancel(
    *,
    visit_identifier: str,
    period_start: str,
    period_end: str | None = None,
    admission_type_code: str = "9",
    admission_type_display: str | None = None,
    org_code: str | None = None,
    diagnosis_case_id: str | None = None,
) -> dict[str, Any]:
    """Build Encounter for cancel/storno visit (message code 1.4).

    MUST have identifier. Status=entered-in-error.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_VISIT, "value": visit_identifier}],
        "status": "entered-in-error",
        "class": {
            "system": CS_ADMISSION_TYPE,
            "code": admission_type_code,
            **({"display": admission_type_display} if admission_type_display else {}),
        },
        "period": {"start": period_start, **({"end": period_end} if period_end else {})},
    }

    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)

    if diagnosis_case_id:
        encounter["diagnosis"] = [
            {
                "condition": {
                    "type": "Condition",
                    "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
                },
            },
        ]

    return encounter


def build_encounter_reopen(
    *,
    visit_identifier: str,
    admission_type_code: str = "9",
    admission_type_display: str | None = None,
    org_code: str | None = None,
) -> dict[str, Any]:
    """Build Encounter for reopen visit (message code 1.5).

    Minimal payload: identifier + status=in-progress + class + serviceProvider.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_VISIT, "value": visit_identifier}],
        "status": "in-progress",
        "class": {
            "system": CS_ADMISSION_TYPE,
            "code": admission_type_code,
            **({"display": admission_type_display} if admission_type_display else {}),
        },
    }

    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)

    return encounter


def build_encounter_close(
    *,
    visit_identifier: str,
    period_start: str,
    period_end: str,
    admission_type_code: str = "9",
    admission_type_display: str | None = None,
    org_code: str | None = None,
    diagnosis_case_id: str | None = None,
) -> dict[str, Any]:
    """Build Encounter for close visit (message code 1.3).

    MUST have identifier. Status=finished. period.end required.
    Optional diagnosis referencing a case.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_VISIT, "value": visit_identifier}],
        "status": "finished",
        "class": {
            "system": CS_ADMISSION_TYPE,
            "code": admission_type_code,
            **({"display": admission_type_display} if admission_type_display else {}),
        },
        "period": {"start": period_start, "end": period_end},
    }

    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)

    if diagnosis_case_id:
        encounter["diagnosis"] = [
            {
                "condition": {
                    "type": "Condition",
                    "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
                },
            },
        ]

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
) -> dict[str, Any]:
    """Build Condition for case status update (codes 2.3-2.5, 2.7).

    Minimal payload — global identifier + subject + optional clinicalStatus.
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
        if rt in ("Encounter", "Condition"):
            identifiers = second.get("identifier", [])
            for ident in identifiers:
                sys = ident.get("system", "")
                if sys in (ID_VISIT, ID_CASE_GLOBAL):
                    result["identifier"] = ident.get("value")
                    break

    return result
