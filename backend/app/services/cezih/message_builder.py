# ruff: noqa: N815 — FHIR spec requires camelCase field names
"""FHIR message Bundle builder for CEZIH $process-message operations.

Builds Bundle type="message" with MessageHeader + resource + digital signature.
Used for Case Management (codes 2.x).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.services.cezih.exceptions import CezihError

logger = logging.getLogger(__name__)

# --- Constants: CEZIH FHIR identifier systems ---

MESSAGE_TYPE_SYSTEM = "http://ent.hr/fhir/CodeSystem/ehe-message-types"

# Re-export for back-compat with existing imports.
from app.services.cezih.builders.common import *  # noqa: F401,F403
from app.services.cezih.response_parsing import (  # noqa: F401
    _CEZIH_DIAGNOSTIC_PATTERNS_HR,
    _CEZIH_ERROR_MESSAGES_HR,
    _translate_cezih_error,
    parse_message_response,
)
from app.services.cezih.signing import (  # noqa: F401
    SIGNATURE_TYPE_CODE,
    SIGNATURE_TYPE_SYSTEM,
    _add_signature_extsigner,
    _add_signature_smartcard,
    _debug_dump_jws,
    _resolve_signing_method,
    add_signature,
)


# --- Message Bundle Builder ---


async def build_message_bundle(
    event_code: str,
    resource: dict[str, Any],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    source_oid: str | None = None,
    profile_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='message' with MessageHeader and resource.

    Does NOT add signature — call add_signature() separately for real mode.
    profile_urls: optional {"bundle": url, "header": url, "resource": url} for meta.profile.
    """
    if not sender_org_code:
        raise CezihError(
            "Šifra zdravstvene ustanove (org_code) nije konfigurirana za ovog zakupca. "
            "Postavite je u Postavke > Organizacija."
        )
    if not source_oid:
        raise CezihError(
            "OID informacijskog sustava nije konfiguriran za ovog zakupca. "
            "Postavite ga u Postavke > Organizacija."
        )

    resource_uuid = str(uuid.uuid4())
    header_uuid = str(uuid.uuid4())

    message_header: dict[str, Any] = {
        "resourceType": "MessageHeader",
        "eventCoding": {
            "system": MESSAGE_TYPE_SYSTEM,
            "code": event_code,
        },
    }

    # Field order matches official CEZIH example: sender, author, source, focus
    if sender_org_code:
        message_header["sender"] = org_ref(sender_org_code)

    if author_practitioner_id:
        message_header["author"] = practitioner_ref(author_practitioner_id)

    message_header["source"] = {"endpoint": f"urn:oid:{source_oid}" if source_oid else "urn:oid:0.0.0.0"}
    message_header["focus"] = [{"reference": f"urn:uuid:{resource_uuid}"}]

    bundle: dict[str, Any] = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
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

    # Inject meta.profile if profile URLs are provided
    if profile_urls:
        if profile_urls.get("bundle"):
            bundle["meta"] = {"profile": [profile_urls["bundle"]]}
        if profile_urls.get("header"):
            message_header["meta"] = {"profile": [profile_urls["header"]]}
        if profile_urls.get("resource"):
            resource["meta"] = {"profile": [profile_urls["resource"]]}

    return bundle


def build_iti65_transaction_bundle(
    entries: list[dict[str, Any]],
    *,
    sender_org_code: str | None = None,
    author_practitioner_id: str | None = None,
    bundle_profile: str | None = None,
    submission_set_profile: str | None = None,
) -> dict[str, Any]:
    """Build a FHIR Bundle type='transaction' for IHE MHD ITI-65 document submission.

    IHE MHD ITI-65 requires type="transaction" (NOT type="message").
    Each entry must have a `request` with method and url.
    Optionally includes a SubmissionSet (List) as the first entry.
    """
    # Build SubmissionSet (List) — required by IHE MHD ITI-65
    # HRMinimalSubmissionSet requires 2 identifiers: uniqueId + entryUUID
    submission_set_uuid = str(uuid.uuid4())
    unique_id = str(uuid.uuid4())
    submission_set: dict[str, Any] = {
        "resourceType": "List",
        "meta": {
            "profile": [submission_set_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalSubmissionSet"],
        },
        "identifier": [
            {
                "use": "official",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{unique_id}",
            },
            {
                "use": "usual",
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:uuid:{submission_set_uuid}",
            },
        ],
        "status": "current",
        "mode": "working",
        "code": {
            "coding": [{
                "system": "https://profiles.ihe.net/ITI/MHD/CodeSystem/MHDlistTypes",
                "code": "submissionset",
            }]
        },
        "date": _now_iso(),
    }
    # Copy subject from the first DocumentReference (mustSupport on SubmissionSet)
    if entries and entries[0].get("subject"):
        submission_set["subject"] = entries[0]["subject"]
    # List.source only accepts Practitioner/Patient/Device — NOT Organization
    if author_practitioner_id:
        submission_set["source"] = practitioner_ref(author_practitioner_id)
    # Extensions: sourceId (required, min:1) + ihe-authorOrg
    extensions: list[dict[str, Any]] = [
        {
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-sourceId",
            "valueIdentifier": {
                "system": "urn:ietf:rfc:3986",
                "value": f"urn:oid:{sender_org_code}" if sender_org_code else "urn:oid:2.16.840.1.113883.2.7",
            },
        },
    ]
    if sender_org_code:
        extensions.append({
            "url": "https://profiles.ihe.net/ITI/MHD/StructureDefinition/ihe-authorOrg",
            "valueReference": org_ref(sender_org_code),
        })
    submission_set["extension"] = extensions

    # Pre-assign UUIDs to entries without _uuid to ensure consistency
    for e in entries:
        if "_uuid" not in e:
            e["_uuid"] = str(uuid.uuid4())

    # SubmissionSet entry references only DocumentReference entries (NOT Binary)
    doc_ref_entries = [e for e in entries if e.get("resourceType") == "DocumentReference"]
    doc_ref_uuids = [e["_uuid"] for e in doc_ref_entries]
    all_uuids = [e["_uuid"] for e in entries]
    submission_set["entry"] = [
        {"item": {"reference": f"urn:uuid:{u}"}} for u in doc_ref_uuids
    ]

    bundle_entries: list[dict[str, Any]] = [
        {
            "fullUrl": f"urn:uuid:{submission_set_uuid}",
            "resource": submission_set,
            "request": {"method": "POST", "url": "List"},
        }
    ]

    for i, entry_resource in enumerate(entries):
        entry_uuid = all_uuids[i]
        # Remove internal _uuid marker if present
        resource = {k: v for k, v in entry_resource.items() if k != "_uuid"}
        resource_type = resource.get("resourceType", "DocumentReference")
        resource_id = resource.get("id")

        # Use PUT for existing resources (cancel/update), POST for new ones
        if resource_id:
            request_entry = {"method": "PUT", "url": f"{resource_type}/{resource_id}"}
            full_url = f"urn:uuid:{entry_uuid}"
        else:
            request_entry = {"method": "POST", "url": resource_type}
            full_url = f"urn:uuid:{entry_uuid}"

        bundle_entries.append({
            "fullUrl": full_url,
            "resource": resource,
            "request": request_entry,
        })

    return {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "meta": {
            "profile": [bundle_profile or "http://fhir.cezih.hr/specifikacije/StructureDefinition/HRMinimalProvideDocumentBundle"],
        },
        "type": "transaction",
        "timestamp": _now_iso(),
        "entry": bundle_entries,
    }


# --- Encounter Resource Builders (TC12-14) ---


# CEZIH Croatian CodeSystems (NOT standard HL7 v3-ActCode)
CS_NACIN_PRIJEMA = "http://fhir.cezih.hr/specifikacije/CodeSystem/nacin-prijema"
CS_VRSTA_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/vrsta-posjete"
CS_TIP_POSJETE = "http://fhir.cezih.hr/specifikacije/CodeSystem/hr-tip-posjete"

NACIN_PRIJEMA_MAP = {
    "1": "Hitni prijem",
    "2": "Uputnica PZZ",
    "3": "Premještaj iz druge ustanove",
    "4": "Nastavno liječenje",
    "5": "Premještaj unutar ustanove",
    "6": "Ostalo",
    "7": "Poziv na raniji termin",
    "8": "Telemedicina",
    "9": "Interna uputnica",
    "10": "Program+",
}

VRSTA_POSJETE_MAP = {
    "1": "Pacijent prisutan",
    "2": "Pacijent udaljeno prisutan",
    "3": "Pacijent nije prisutan",
}

TIP_POSJETE_MAP = {
    "1": "Posjeta LOM",
    "2": "Posjeta SKZZ",
    "3": "Hospitalizacija",
}

# FHIR Profile URLs for Encounter messages (meta.profile)
_PROFILE_BASE = "http://fhir.cezih.hr/specifikacije/StructureDefinition"
PROFILE_ENCOUNTER = f"{_PROFILE_BASE}/hr-encounter"
PROFILE_ENCOUNTER_MSG_HEADER = f"{_PROFILE_BASE}/hr-encounter-management-message-header"

ENCOUNTER_EVENT_PROFILE_MAP = {
    "1.1": f"{_PROFILE_BASE}/hr-create-encounter-message",
    "1.2": f"{_PROFILE_BASE}/hr-update-encounter-message",
    "1.3": f"{_PROFILE_BASE}/hr-close-encounter-message",
    "1.4": f"{_PROFILE_BASE}/hr-cancel-encounter-message",
    "1.5": f"{_PROFILE_BASE}/hr-reopen-encounter-message",
}

VISIT_ACTION_MAP: dict[str, dict[str, str]] = {
    "close": {"code": "1.3", "status": "finished"},
    "storno": {"code": "1.4", "status": "entered-in-error"},
    "reopen": {"code": "1.5", "status": "in-progress"},
}


def build_encounter_create(
    *,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit creation (event code 1.1).

    Uses CEZIH Croatian CodeSystems:
      - Encounter.class: nacin-prijema (method of admission)
    """
    # Match official CEZIH example — field order matches spec
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "subject": patient_ref(patient_mbo, identifier_system),
        "type": [],
    }
    if vrsta_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
        })
    if tip_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
        })
    if not encounter["type"]:
        del encounter["type"]
    if practitioner_id:
        encounter["participant"] = [{
            "individual": practitioner_ref(practitioner_id),
        }]
    encounter["period"] = {"start": _now_iso()}
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    return encounter


def build_encounter_update(
    *,
    encounter_id: str,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
    nacin_prijema: str = "6",
    vrsta_posjete: str = "1",
    tip_posjete: str = "1",
    reason: str | None = None,
    practitioner_id: str = "",
    additional_practitioner_id: str | None = None,
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit update (event code 1.2).

    CEZIH example includes: extension, identifier, class, type, subject, participant,
    period, diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "extension": [
            {
                "extension": [
                    {"url": "oznaka", "valueCoding": {"system": CS_SUDJELOVANJE_U_TROSKOVIMA, "code": "N"}},
                    {"url": "sifra-oslobodjenja", "valueCoding": {"system": CS_SIFRA_OSLOBODJENJA, "code": "55"}},
                ],
                "url": EXT_TROSKOVI_SUDJELovanje,
            },
        ],
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "type": [],
        "subject": patient_ref(patient_mbo, identifier_system),
        "period": {"start": period_start if period_start else _now_iso()},
    }
    if vrsta_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_VRSTA_POSJETE, "code": vrsta_posjete}],
        })
    if tip_posjete:
        encounter["type"].append({
            "coding": [{"system": CS_TIP_POSJETE, "code": tip_posjete}],
        })
    if not encounter["type"]:
        del encounter["type"]
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if practitioner_id:
        participants = [{"individual": practitioner_ref(practitioner_id)}]
        if additional_practitioner_id and additional_practitioner_id != practitioner_id:
            participants.append({"individual": practitioner_ref(additional_practitioner_id)})
        encounter["participant"] = participants
    if reason:
        encounter["reasonCode"] = [{"text": reason}]
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    return encounter


def build_encounter_close(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit close (event code 1.3).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}

    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "finished",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
        "period": period,
        "serviceProvider": org_ref(org_code) if org_code else {},
    }
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    if not org_code:
        encounter.pop("serviceProvider", None)
    return encounter


def build_encounter_cancel(
    *,
    encounter_id: str,
    patient_mbo: str,
    nacin_prijema: str = "6",
    reason: str | None = None,
    practitioner_id: str = "",
    org_code: str = "",
    diagnosis_case_id: str | None = None,
    period_start: str | None = None,
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit cancellation/storno (event code 1.4).

    CEZIH example includes: identifier, status, class, period (start+end),
    diagnosis, serviceProvider. See docs/CEZIH/Posjete/.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "entered-in-error",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    period: dict[str, str] = {"start": period_start or _now_iso(), "end": _now_iso()}
    encounter["period"] = period
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    if diagnosis_case_id:
        encounter["diagnosis"] = [{
            "condition": {
                "type": "Condition",
                "identifier": {"system": ID_CASE_REF, "value": diagnosis_case_id},
            },
        }]
    return encounter


def build_encounter_reopen(
    *,
    encounter_id: str,
    nacin_prijema: str = "6",
    org_code: str = "",
) -> dict[str, Any]:
    """Build FHIR Encounter resource for visit reopen (event code 1.5).

    Per CEZIH official example: identifier, status, class, serviceProvider only.
    No subject, participant, period, or id fields.
    """
    encounter: dict[str, Any] = {
        "resourceType": "Encounter",
        "identifier": [{"system": ID_ENCOUNTER, "value": encounter_id}],
        "status": "in-progress",
        "class": {
            "system": CS_NACIN_PRIJEMA,
            "code": nacin_prijema,
            "display": NACIN_PRIJEMA_MAP.get(nacin_prijema, nacin_prijema),
        },
    }
    if org_code:
        encounter["serviceProvider"] = org_ref(org_code)
    return encounter


# --- Condition Resource Builders ---


def build_condition_create(
    *,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
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

    # Convert date-only string to selected date + current time
    if onset_date and len(onset_date) == 10:  # Date-only "YYYY-MM-DD"
        now = datetime.now(_TZ_ZAGREB)
        onset_dt = datetime.combine(
            date.fromisoformat(onset_date),
            now.time(),
        ).replace(tzinfo=_TZ_ZAGREB)
    else:
        onset_dt = onset_date

    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_LOCAL, "value": local_id}],
        "verificationStatus": {
            "coding": [{"system": CS_CONDITION_VER_STATUS, "code": verification_status}],
        },
        "code": {
            "coding": [{"system": CS_ICD10_HR, "code": icd_code, "display": icd_display}],
        },
        "subject": patient_ref(patient_mbo, identifier_system),
        "onsetDateTime": onset_dt.isoformat() if isinstance(onset_dt, datetime) else onset_dt,
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
    identifier_system: str = ID_MBO,
    clinical_status: str | None = None,
    abatement_date: str | None = None,
) -> dict[str, Any]:
    """Build Condition for case status update (codes 2.3-2.5, 2.9).

    Per Simplifier cezih.hr.condition-management/0.2.1 profiles:

    - 2.3 Remisija: minimal (identifier + subject only)
    - 2.4 Resolve:  clinicalStatus=resolved + abatementDateTime REQUIRED
    - 2.5 Relapse:  minimal (identifier + subject only)
    - 2.9 Reopen:   minimal (identifier + subject only)
    """
    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "identifier": [{"system": ID_CASE_GLOBAL, "value": case_identifier}],
        "subject": patient_ref(patient_mbo, identifier_system),
    }

    if clinical_status:
        condition["clinicalStatus"] = {
            "coding": [{"system": CS_CONDITION_CLINICAL, "code": clinical_status}],
        }

    if abatement_date:
        if len(abatement_date) == 10:  # Date-only "YYYY-MM-DD"
            now = datetime.now(_TZ_ZAGREB)
            abatement_dt = datetime.combine(
                date.fromisoformat(abatement_date),
                now.time(),
            ).replace(tzinfo=_TZ_ZAGREB)
            condition["abatementDateTime"] = abatement_dt.isoformat()
        else:
            condition["abatementDateTime"] = abatement_date

    return condition


def build_condition_data_update(
    *,
    case_identifier: str,
    patient_mbo: str,
    identifier_system: str = ID_MBO,
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
        "subject": patient_ref(patient_mbo, identifier_system),
    }

    # Must echo current clinicalStatus (cannot change it via data update).
    # FHIR invariant con-5: clinicalStatus SHALL NOT be present if verificationStatus=entered-in-error.
    entered_in_error = verification_status == "entered-in-error"
    if current_clinical_status and not entered_in_error:
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
        if len(onset_date) == 10:  # Date-only "YYYY-MM-DD"
            now = datetime.now(_TZ_ZAGREB)
            onset_dt = datetime.combine(
                date.fromisoformat(onset_date),
                now.time(),
            ).replace(tzinfo=_TZ_ZAGREB)
            condition["onsetDateTime"] = onset_dt.isoformat()
        else:
            condition["onsetDateTime"] = onset_date

    # con-4: if abated, clinicalStatus must be inactive/resolved/remission.
    # Since entered-in-error drops clinicalStatus (con-5), abatement must also be dropped.
    if abatement_date and not entered_in_error:
        if len(abatement_date) == 10:  # Date-only "YYYY-MM-DD"
            now = datetime.now(_TZ_ZAGREB)
            abatement_dt = datetime.combine(
                date.fromisoformat(abatement_date),
                now.time(),
            ).replace(tzinfo=_TZ_ZAGREB)
            condition["abatementDateTime"] = abatement_dt.isoformat()
        else:
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


# --- Mapping: case action -> message code + clinical status ---

# Delete (2.7) is deliberately NOT wired per product rule — see CLAUDE.md.
# For "mistaken entry" UX: 2.6 Data update with verificationStatus=entered-in-error.
#
# Event codes per Simplifier cezih.hr.condition-management/0.2.1:
#   2.1=Create, 2.2=Create recurrence, 2.3=Remission, 2.4=Resolve,
#   2.5=Relapse, 2.6=Data update, 2.7=Delete (NOT shipped),
#   2.8=Reopen after delete (unreachable), 2.9=Reopen after resolve
# Action → event code only. Payload shape per event is in CASE_EVENT_PROFILE below.
CASE_ACTION_MAP: dict[str, dict[str, str]] = {
    "create": {"code": "2.1"},
    "create_recurring": {"code": "2.2"},
    "remission": {"code": "2.3"},
    "resolve": {"code": "2.4"},
    "relapse": {"code": "2.5"},
    "update_data": {"code": "2.6"},
    "reopen": {"code": "2.9"},
}


# --- Per-event CEZIH profile rules for case status-update messages ---
#
# CEZIH validates each $process-message event code against a DIFFERENT
# StructureDefinition profile (Simplifier cezih.hr.condition-management/0.2.1).
#
# Fields:
#   cs        — include Condition.clinicalStatus
#   cs_value  — code to send when cs=True (e.g. "resolved")
#   abatement — include Condition.abatementDateTime (set to now())
CASE_EVENT_PROFILE: dict[str, dict[str, Any]] = {
    "2.3": {"cs": False, "abatement": False, "cs_value": None},  # Remisija — minimal
    "2.4": {"cs": True,  "abatement": True,  "cs_value": "resolved"},  # Resolve — cs=resolved + abatementDateTime REQUIRED
    "2.5": {"cs": False, "abatement": False, "cs_value": None},  # Relapse — minimal
    "2.9": {"cs": False, "abatement": False, "cs_value": None},  # Reopen after resolve — minimal
    # 2.2 Ponavljajući routes through build_condition_create (hr-create-health-issue-recurrence-message)
    # — handled in service.py update_case, not via this table.
}
