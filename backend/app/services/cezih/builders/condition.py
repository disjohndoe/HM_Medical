"""FHIR Condition resource builders (CEZIH Case messages 2.1–2.7).

Contains condition builders and CASE_ACTION_MAP for case lifecycle operations.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.cezih.builders.common import (
    CS_ANNOTATION_TYPE,
    CS_CONDITION_CLINICAL,
    CS_CONDITION_VER_STATUS,
    CS_ICD10_HR,
    EXT_ANNOTATION_TYPE,
    ID_CASE_GLOBAL,
    ID_CASE_LOCAL,
    ID_MBO,
    _TZ_ZAGREB,
    _now_iso,
    patient_ref,
    practitioner_ref,
)

logger = logging.getLogger(__name__)


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


__all__ = [
    # Builders
    "build_condition_create",
    "build_condition_status_update",
    "build_condition_data_update",
    # Maps
    "CASE_ACTION_MAP",
    "CASE_EVENT_PROFILE",
]
